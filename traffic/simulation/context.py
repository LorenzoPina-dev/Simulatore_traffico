"""
simulation/context.py — SimContext: stato condiviso per step.

SimContext è un Value Object passato ai behavior ad ogni step.
Contiene tutti i riferimenti necessari ai behavior per prendere decisioni,
senza che i behavior debbano conoscere il SimEngine.

Immutabile dal punto di vista dei behavior (occ è mutabile come side-effect
controllato, ma la struttura del context non cambia durante uno step).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.config                    import SimConfig
    from ..world.geometry                 import GridGeometry
    from ..agents.vehicle                 import Vehicle
    from ..infrastructure.gap_calculator  import GapCalculator
    from ..infrastructure.ipr             import IntersectionPathReservation
    from ..infrastructure.traffic_light   import TrafficLight
    from ..infrastructure.right_of_way    import RightOfWayChecker


@dataclass
class SimContext:
    """
    Contesto condiviso per un singolo step di simulazione.

    Attributi:
        occ      : mappa posizione → veicolo (mutabile: i behavior aggiornano posizioni)
        obs_set  : insieme celle occupate da ostacoli (read-only durante lo step)
        occ_snap : snapshot immutabile di occ all'inizio dello step (per ROW, pull-over)
        step     : step corrente
        cfg      : configurazione simulazione (read-only)
        geo      : geometria della griglia (read-only)
        light    : semaforo (i behavior lo interrogano, non lo modificano)
        gap_calc : servizio di calcolo gap (stateless)
        ipr      : servizio prenotazione incrocio
        row_checker : checker precedenza
    """
    occ:       Dict[Tuple[int,int], "Vehicle"]
    obs_set:   Set[Tuple[int,int]]
    occ_snap:  Dict[Tuple[int,int], "Vehicle"]
    step:      int
    cfg:       "SimConfig"
    geo:       "GridGeometry"
    light:     "TrafficLight"
    gap_calc:  "GapCalculator"
    ipr:       "IntersectionPathReservation"
    row_checker: "RightOfWayChecker"
