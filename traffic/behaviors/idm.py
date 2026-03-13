"""
behaviors/idm.py — Intelligent Driver Model.

Formula IDM:
    a = a_max · [1 − (v/v₀)^δ − (s*(v,Δv)/s)²]
    s*(v,Δv) = s₀ + max(0, v·T + v·Δv / (2·√(a·b)))

Scala fisica: 1 cella ≈ 7 m, 1 step ≈ 1 s.

Dawdling: perturbazione stocastica su v_float per simulare
l'irregolarità del comportamento umano.
"""
from __future__ import annotations
import math
import random
from typing import TYPE_CHECKING, Set

from .interfaces import MovementBehavior

if TYPE_CHECKING:
    from ..agents.vehicle     import Vehicle
    from ..simulation.context import SimContext


class IDMBehavior(MovementBehavior):
    """
    Implementazione del Intelligent Driver Model.

    Produce accelerazione fluida e frenata anticipata proporzionale al gap.
    """

    def compute_velocity(
        self,
        vehicle:   "Vehicle",
        context:   "SimContext",
        extra_blocks: Set = None,
    ) -> float:
        """
        Calcola la nuova v_float secondo IDM.

        Parametri IDM letti dallo stato del veicolo:
            v_float, v_desired, idm_a, idm_b, idm_T, idm_s0

        Args:
            extra_blocks: celle virtuali bloccate (semaforo, ROW, IPR)
        """
        extra = extra_blocks or set()
        cfg   = context.cfg

        gap    = context.gap_calc.gap_ahead(vehicle, context.occ, context.obs_set, extra)
        v_lead = context.gap_calc.leader_speed(vehicle, context.occ, context.obs_set, extra, gap)

        s_gap = float(max(0, gap))
        if (not context.light.go_for(vehicle)
                and not vehicle.in_inter
                and not vehicle.inter_path
                and not vehicle.slip_path):
            acc = self._idm_accel_override(vehicle, s_gap, v_lead, cfg.idm_delta, s0=0.0, T=0.0)
        else:
            acc = self._idm_accel(vehicle, s_gap, v_lead, cfg.idm_delta)

        # Aggiorna la velocità continua
        new_v = max(0.0, vehicle.v_float + acc)
        new_v = min(new_v, min(vehicle.v_desired, float(cfg.max_speed)))

        # Dawdling: perturbazione stocastica proporzionale alla frustrazione
        eff_dw = vehicle.dw * (1.0 + vehicle.frus * cfg.frustration_dawdle_factor)
        if random.random() < eff_dw:
            new_v = max(0.0, new_v - random.uniform(0.1, 0.4))

        return new_v

    # ─────────────────────────────────────────────────────────────────
    # Formula IDM
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _idm_accel(vehicle: "Vehicle", gap: float, v_lead: float, delta: int) -> float:
        """
        a = a_max · [1 − (v/v₀)^δ − (s*(v,Δv)/s)²]
        s*(v,Δv) = s₀ + max(0, v·T + v·Δv / 2·√(a·b))
        """
        v     = vehicle.v_float
        v0    = vehicle.v_desired
        a_max = vehicle.idm_a
        b     = vehicle.idm_b
        T     = vehicle.idm_T
        s0    = float(vehicle.idm_s0)

        if v0 <= 0.0:
            return -a_max

        s   = max(0.001, gap)
        dv  = v - v_lead

        sqrt_ab = math.sqrt(max(1e-6, a_max * b))
        s_star  = s0 + max(0.0, v * T + v * dv / (2.0 * sqrt_ab))

        free_road   = (v / v0) ** delta if v0 > 0 else 1.0
        interaction = (s_star / s) ** 2

        acc = a_max * (1.0 - free_road - interaction)
        return max(-2.0 * b, min(acc, a_max))

    @staticmethod
    def _idm_accel_override(
        vehicle: "Vehicle", gap: float, v_lead: float, delta: int, s0: float, T: float
    ) -> float:
        v     = vehicle.v_float
        v0    = vehicle.v_desired
        a_max = vehicle.idm_a
        b     = vehicle.idm_b

        if v0 <= 0.0:
            return -a_max

        s   = max(0.001, gap)
        dv  = v - v_lead

        sqrt_ab = (a_max * b) ** 0.5 if a_max * b > 1e-6 else 1e-3
        s_star  = s0 + max(0.0, v * T + v * dv / (2.0 * sqrt_ab))

        free_road   = (v / v0) ** delta if v0 > 0 else 1.0
        interaction = (s_star / s) ** 2

        acc = a_max * (1.0 - free_road - interaction)
        return max(-2.0 * b, min(acc, a_max))
