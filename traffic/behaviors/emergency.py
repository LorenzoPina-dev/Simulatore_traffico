"""
behaviors/emergency.py — Risposta ai veicoli di emergenza.

Implementazioni:
    EmergencyPullOverBehavior — cede il passo se emergenza nelle vicinanze
    NullPullOverBehavior       — no-op (Null Object Pattern)
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from .interfaces import PullOverBehavior
from ..core.types import VehicleType

if TYPE_CHECKING:
    from ..agents.vehicle     import Vehicle
    from ..simulation.context import SimContext


class EmergencyPullOverBehavior(PullOverBehavior):
    """
    Rileva emergenze in avvicinamento e segnala la necessità di cedere il passo.

    Cerca veicoli di emergenza con sirena entro emergency_pull_over_dist celle
    nella direzione di marcia del veicolo. Se trovato, segnala pull-over.
    """

    def should_pull_over(self, vehicle: "Vehicle", context: "SimContext") -> bool:
        if vehicle.vtype == VehicleType.EMERGENCY:
            return False    # i veicoli di emergenza non si spostano per altri

        dist_thresh = context.cfg.emergency_pull_over_dist
        if dist_thresh <= 0:
            return False

        geo = context.geo
        for look in range(1, dist_thresh + 1):
            nr = vehicle.r + vehicle.dr * look
            nc = vehicle.c + vehicle.dc * look
            if not geo.in_bounds(nr, nc):
                break
            other = context.occ_snap.get((nr, nc))
            if other is not None and other.vtype == VehicleType.EMERGENCY and other.siren:
                return True

        return False


class NullPullOverBehavior(PullOverBehavior):
    """Null Object: nessuna risposta alle emergenze."""

    def should_pull_over(self, vehicle: "Vehicle", context: "SimContext") -> bool:
        return False
