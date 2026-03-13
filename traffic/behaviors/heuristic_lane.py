"""
behaviors/heuristic_lane.py — Cambio corsia euristico (fallback se use_mobil=False).

Logica semplice:
    - Se il gap davanti è scarso, prova a cambiare a sinistra (sorpasso)
    - Se il gap è buono e non sei già in corsia destra, torna a destra
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from .interfaces import LaneChangeBehavior

if TYPE_CHECKING:
    from ..agents.vehicle     import Vehicle
    from ..simulation.context import SimContext


class HeuristicLaneBehavior(LaneChangeBehavior):
    """
    Cambio corsia euristico: sorpassa se il gap è scarso,
    torna a destra se il gap lo consente.
    """

    def evaluate(self, vehicle: "Vehicle", context: "SimContext") -> int:
        if vehicle.in_inter:
            return 0
        gap = context.gap_calc.gap_ahead(vehicle, context.occ, context.obs_set)
        if gap < vehicle.ms:
            return +1   # prova sorpasso
        if vehicle.li > 0:
            return -1   # torna a destra
        return 0

    def execute(
        self, vehicle: "Vehicle", direction: int, context: "SimContext"
    ) -> bool:
        if vehicle.in_inter:
            return False

        target_r, target_c = self._target_cell(vehicle, direction)
        geo = context.geo

        if not geo.in_bounds(target_r, target_c):                               return False
        if not geo.valid_lane_cell(target_r, target_c, vehicle.dr, vehicle.dc): return False
        if (target_r, target_c) in context.occ:                                  return False
        if (target_r, target_c) in context.obs_set:                              return False

        gc       = context.gap_calc
        gap_fwd  = gc.gap_ahead_at(target_r, target_c, vehicle.dr, vehicle.dc, context.occ, context.obs_set)
        gap_rear = gc.gap_rear_at(target_r, target_c, vehicle.dr, vehicle.dc, context.occ)

        # Criterio minimo: gap avanti >= ms-1, gap dietro >= 1
        if gap_fwd < max(1, vehicle.ms - 1) or gap_rear < 1:
            return False

        context.occ.pop((vehicle.r, vehicle.c), None)
        vehicle.r, vehicle.c = target_r, target_c
        vehicle.li = geo.lane_index(target_r, target_c, vehicle.dr, vehicle.dc)
        context.occ[(vehicle.r, vehicle.c)] = vehicle
        vehicle.frus = max(0, vehicle.frus - 2)
        return True

    @staticmethod
    def _target_cell(vehicle: "Vehicle", direction: int):
        if vehicle.dc == 1:    return vehicle.r - direction, vehicle.c
        elif vehicle.dc == -1: return vehicle.r + direction, vehicle.c
        elif vehicle.dr == 1:  return vehicle.r, vehicle.c + direction
        else:                  return vehicle.r, vehicle.c - direction
