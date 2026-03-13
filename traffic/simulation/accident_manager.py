"""
simulation/accident_manager.py — Gestione incidenti stocastici.

Responsabilità:
    - Generare incidenti casuali su veicoli vulnerabili
    - Rimuovere il veicolo e piazzare un Obstacle
    - Aggiornare occ e obs_set
"""
from __future__ import annotations
import random
from typing import Dict, List, Set, TYPE_CHECKING

from ..agents.obstacle import Obstacle

if TYPE_CHECKING:
    from ..core.config    import SimConfig
    from ..agents.vehicle import Vehicle
    from ..infrastructure.ipr import IntersectionPathReservation


class AccidentManager:
    """Genera e gestisce gli incidenti stocastici sulla griglia."""

    def __init__(self, cfg: "SimConfig", ipr: "IntersectionPathReservation"):
        self._cfg = cfg
        self._ipr = ipr

    def process(
        self,
        cars:    List["Vehicle"],
        occ:     Dict,
        obs_set: Set,
        obstacles: List[Obstacle],
    ) -> int:
        """
        Controlla ogni veicolo per un possibile incidente.
        Restituisce il numero di incidenti generati questo step.
        """
        cfg     = self._cfg
        to_remove: List["Vehicle"] = []
        new_accidents = 0

        for car in cars:
            # Veicoli in transito IPR o slip non possono incidentarsi
            if car.in_inter or car.inter_path or car.slip_path:
                continue
            if random.random() < cfg.accident_prob:
                dur = random.randint(cfg.accident_dur_min, cfg.accident_dur_max)
                obs = Obstacle(car.r, car.c, dur, "incidente")
                obstacles.append(obs)
                obs_set.add((car.r, car.c))
                occ.pop((car.r, car.c), None)
                self._ipr.release(car)
                to_remove.append(car)
                new_accidents += 1

        for car in to_remove:
            cars.remove(car)

        return new_accidents
