"""
behaviors/mobil.py — MOBIL lane change model.

MOBIL = Minimizing Overall Braking Induced by Lane Changes.

Criterio:
    gain = (a_new_me - a_old_me) - p · ((a_new_fol_n - a_old_fol_n) + (a_new_fol_o - a_old_fol_o))
    gain >= threshold - right_bias → cambia corsia

Sicurezza: il nuovo follower non deve frenare oltre b_safe.
Bias verso destra: incentiva il "keep-right".
"""
from __future__ import annotations
import math
from typing import TYPE_CHECKING, Optional, Set

from .interfaces import LaneChangeBehavior
from .idm        import IDMBehavior

if TYPE_CHECKING:
    from ..agents.vehicle     import Vehicle
    from ..simulation.context import SimContext


class MOBILBehavior(LaneChangeBehavior):
    """
    MOBIL: cambio corsia cooperativo basato su guadagno di accelerazione IDM.

    Parametri (da SimConfig):
        mobil_politeness : peso dell'impatto sui vicini [0..1]
        mobil_threshold  : guadagno minimo per cambiare
        mobil_safe_decel : decelerazione massima tollerabile per il nuovo follower
        mobil_right_bias : bonus per spostarsi a destra (keep-right)
    """

    def evaluate(self, vehicle: "Vehicle", context: "SimContext") -> int:
        """
        Restituisce la direzione di cambio preferita:
            +1 = sorpasso (sinistra)
            -1 = tieni destra
             0 = resta
        """
        if vehicle.in_inter:
            return 0

        # Prova prima il sorpasso (sinistra), poi il "tieni destra"
        gain_left  = self._compute_gain(vehicle, +1, context)
        gain_right = self._compute_gain(vehicle, -1, context)

        cfg = context.cfg
        threshold  = cfg.mobil_threshold
        right_bias = cfg.mobil_right_bias

        # Preferisci destra se entrambi validi (keep-right rule)
        if gain_right >= threshold - right_bias:
            return -1
        if gain_left >= threshold:
            return +1
        return 0

    def execute(
        self, vehicle: "Vehicle", direction: int, context: "SimContext"
    ) -> bool:
        """
        Tenta il cambio corsia nella direzione indicata.
        Verifica la sicurezza del nuovo follower prima di procedere.
        """
        if vehicle.in_inter:
            return False

        target_r, target_c = self._target_cell(vehicle, direction)
        geo = context.geo

        if not geo.in_bounds(target_r, target_c):                               return False
        if not geo.valid_lane_cell(target_r, target_c, vehicle.dr, vehicle.dc): return False
        if (target_r, target_c) in context.occ:                                  return False
        if (target_r, target_c) in context.obs_set:                              return False

        # Verifica sicurezza nuovo follower
        if not self._is_safe_for_new_follower(vehicle, direction, target_r, target_c, context):
            return False

        # Esegui il cambio
        context.occ.pop((vehicle.r, vehicle.c), None)
        vehicle.r, vehicle.c = target_r, target_c
        vehicle.li = geo.lane_index(target_r, target_c, vehicle.dr, vehicle.dc)
        context.occ[(vehicle.r, vehicle.c)] = vehicle
        vehicle.frus = max(0, vehicle.frus - 2)
        return True

    # ─────────────────────────────────────────────────────────────────
    # Calcolo guadagno MOBIL
    # ─────────────────────────────────────────────────────────────────

    def _compute_gain(self, vehicle: "Vehicle", direction: int, context: "SimContext") -> float:
        """
        Calcola il guadagno MOBIL per un cambio nella direzione indicata.
        Restituisce -inf se la cella target non è disponibile.
        """
        target_r, target_c = self._target_cell(vehicle, direction)
        geo = context.geo

        if not geo.in_bounds(target_r, target_c):                               return float('-inf')
        if not geo.valid_lane_cell(target_r, target_c, vehicle.dr, vehicle.dc): return float('-inf')
        if (target_r, target_c) in context.occ:                                  return float('-inf')
        if (target_r, target_c) in context.obs_set:                              return float('-inf')

        cfg = context.cfg
        gc  = context.gap_calc

        # Accelerazione nella corsia corrente
        gap_curr  = gc.gap_ahead(vehicle, context.occ, context.obs_set)
        vl_curr   = gc.leader_speed(vehicle, context.occ, context.obs_set, None, gap_curr)
        a_curr    = IDMBehavior._idm_accel(vehicle, float(gap_curr), vl_curr, cfg.idm_delta)

        # Accelerazione nella corsia target
        tmp_veh   = _VehicleProxy(vehicle, target_r, target_c)
        gap_new   = gc.gap_ahead(tmp_veh, context.occ, context.obs_set)
        vl_new    = gc.leader_speed(tmp_veh, context.occ, context.obs_set, None, gap_new)
        a_new_me  = IDMBehavior._idm_accel(vehicle, float(gap_new), vl_new, cfg.idm_delta)

        # Follower nella corsia target (nuovo follower)
        fol_n      = _find_follower(target_r, target_c, vehicle.dr, vehicle.dc, context.occ, cfg.max_speed + 3, geo)
        a_n_delta  = _follower_delta(fol_n, vehicle, target_r, target_c, context, cfg.idm_delta)

        # Follower nella corsia corrente (vecchio follower, guadagna gap)
        fol_o     = _find_follower(vehicle.r, vehicle.c, vehicle.dr, vehicle.dc, context.occ, cfg.max_speed + 3, geo)
        a_o_delta = _old_follower_delta(fol_o, vehicle, context, cfg.idm_delta)

        gain = (a_new_me - a_curr) - cfg.mobil_politeness * (a_n_delta + a_o_delta)
        return gain

    def _is_safe_for_new_follower(
        self, vehicle: "Vehicle", direction: int,
        target_r: int, target_c: int,
        context: "SimContext",
    ) -> bool:
        """Verifica che il nuovo follower possa frenare in sicurezza."""
        geo    = context.geo
        fol_n  = _find_follower(target_r, target_c, vehicle.dr, vehicle.dc,
                                context.occ, context.cfg.max_speed + 3, geo)
        if fol_n is None:
            return True

        rear_gap = _dist_cells(fol_n, target_r, target_c)
        a_n_new  = IDMBehavior._idm_accel(fol_n, float(max(0, rear_gap)),
                                           vehicle.v_float, context.cfg.idm_delta)
        return a_n_new >= -context.cfg.mobil_safe_decel

    # ─────────────────────────────────────────────────────────────────
    # Helper geometria
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _target_cell(vehicle: "Vehicle", direction: int):
        """Calcola la cella target per il cambio di corsia."""
        if vehicle.dc == 1:    return vehicle.r - direction, vehicle.c
        elif vehicle.dc == -1: return vehicle.r + direction, vehicle.c
        elif vehicle.dr == 1:  return vehicle.r, vehicle.c + direction
        else:                  return vehicle.r, vehicle.c - direction


# ─────────────────────────────────────────────────────────────────────
# Funzioni helper (modulo-level, non metodi)
# ─────────────────────────────────────────────────────────────────────

class _VehicleProxy:
    """Proxy leggero per simulare un veicolo in una posizione diversa."""
    def __init__(self, v, r, c):
        self.r = r; self.c = c
        self.dr = v.dr; self.dc = v.dc

def _find_follower(r, c, dr, dc, occ, lookbehind, geo) -> Optional["Vehicle"]:
    for d in range(1, lookbehind + 1):
        br = r - dr * d
        bc = c - dc * d
        if not geo.in_bounds(br, bc): return None
        v = occ.get((br, bc))
        if v is not None and (v.dr, v.dc) == (dr, dc):
            return v
    return None

def _dist_cells(from_veh, to_r, to_c) -> int:
    if from_veh.dc == 1:  return max(0, to_c - from_veh.c - 1)
    if from_veh.dc == -1: return max(0, from_veh.c - to_c - 1)
    if from_veh.dr == 1:  return max(0, to_r - from_veh.r - 1)
    return                       max(0, from_veh.r - to_r - 1)

def _follower_delta(fol, vehicle, target_r, target_c, context, delta) -> float:
    """Variazione di accelerazione del nuovo follower dopo il cambio."""
    if fol is None: return 0.0
    gc  = context.gap_calc
    cfg = context.cfg

    # Prima del cambio
    gap_old = gc.gap_ahead(fol, context.occ, context.obs_set)
    vl_old  = gc.leader_speed(fol, context.occ, context.obs_set, None, gap_old)
    a_old   = IDMBehavior._idm_accel(fol, float(gap_old), vl_old, delta)

    # Dopo il cambio: fol si trova dietro vehicle in target
    rear_gap = _dist_cells(fol, target_r, target_c)
    a_new    = IDMBehavior._idm_accel(fol, float(max(0, rear_gap)), vehicle.v_float, delta)
    return a_new - a_old

def _old_follower_delta(fol, vehicle, context, delta) -> float:
    """Variazione di accelerazione del vecchio follower: guadagna gap."""
    if fol is None: return 0.0
    gc  = context.gap_calc

    gap_old  = gc.gap_ahead(fol, context.occ, context.obs_set)
    vl_old   = gc.leader_speed(fol, context.occ, context.obs_set, None, gap_old)
    a_old    = IDMBehavior._idm_accel(fol, float(gap_old), vl_old, delta)
    # Dopo il cambio: gap aumenta di (vehicle.length + 1)
    gap_new  = gap_old + max(1, vehicle.length)
    a_new    = IDMBehavior._idm_accel(fol, float(gap_new), vl_old, delta)
    return a_new - a_old
