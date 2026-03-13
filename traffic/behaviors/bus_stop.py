"""
behaviors/bus_stop.py — Gestione fermate autobus.

Il bus si ferma sulla cella configurata per dwell_time step, poi riparte.

Implementazioni:
    BusStopBehavior — fermata reale per bus
    NullStopBehavior — no-op per veicoli non-bus (Null Object Pattern)
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from .interfaces import StopBehavior

if TYPE_CHECKING:
    from ..agents.vehicle     import Vehicle
    from ..simulation.context import SimContext


class BusStopBehavior(StopBehavior):
    """
    Comportamento fermata bus.

    Legge le fermate da context.cfg.bus_stops e controlla se la cella
    corrente del veicolo corrisponde a una di esse. Se sì, inizia
    il countdown di dwell_time step.
    """

    def check_stop(self, vehicle: "Vehicle", context: "SimContext") -> bool:
        # Se già in sosta, conta il timer
        if vehicle.bus_stop_timer > 0:
            vehicle.bus_stop_timer -= 1
            return True

        # Controlla se questa cella è una fermata
        for i, stop in enumerate(context.cfg.bus_stops):
            if vehicle.r == stop.row and vehicle.c == stop.col:
                if vehicle.next_stop_idx != i or vehicle.bus_stop_timer == 0:
                    vehicle.bus_stop_timer = stop.dwell_time
                    vehicle.next_stop_idx  = (i + 1) % max(1, len(context.cfg.bus_stops))
                    return True

        return False


class NullStopBehavior(StopBehavior):
    """
    Null Object: nessuna fermata programmata (usato da tutti i veicoli non-bus).
    Evita di dover verificare il tipo di veicolo nei behavior.
    """

    def check_stop(self, vehicle: "Vehicle", context: "SimContext") -> bool:
        return False
