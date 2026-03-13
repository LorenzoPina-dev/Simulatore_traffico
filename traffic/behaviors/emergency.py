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

    Scansiona in tutte e 4 le direzioni entro emergency_pull_over_dist celle:
      - Davanti  : emergenza che arriva in senso contrario (testa a testa)
      - Dietro   : emergenza che si avvicina nella stessa corsia da dietro
      - Laterale : emergenza su una strada perpendicolare
    In questo modo il veicolo si sposta a destra e si ferma PRIMA che
    l'emergenza arrivi, lasciando libera la corsia centrale.
    I veicoli di emergenza stessi non attivano mai il pull-over.
    """

    def should_pull_over(self, vehicle: "Vehicle", context: "SimContext") -> bool:
        if vehicle.vtype == VehicleType.EMERGENCY:
            return False    # i veicoli di emergenza non si spostano per altri

        dist_thresh = context.cfg.emergency_pull_over_dist
        if dist_thresh <= 0:
            return False

        geo = context.geo
        # Scansione SOLO avanti e dietro lungo il proprio asse di marcia.
        # Questo evita che le auto nella corsia opposta (adiacente di 1 cella)
        # vengano erroneamente bloccate dalla sirena sull'altro lato della strada.
        for sign in (1, -1):
            for look in range(1, dist_thresh + 1):
                nr = vehicle.r + vehicle.dr * sign * look
                nc = vehicle.c + vehicle.dc * sign * look
                if not geo.in_bounds(nr, nc):
                    break
                other = context.occ_snap.get((nr, nc))
                if (other is not None
                        and other.vtype == VehicleType.EMERGENCY
                        and other.siren):
                    return True

        return False


class NullPullOverBehavior(PullOverBehavior):
    """Null Object: nessuna risposta alle emergenze."""

    def should_pull_over(self, vehicle: "Vehicle", context: "SimContext") -> bool:
        return False
