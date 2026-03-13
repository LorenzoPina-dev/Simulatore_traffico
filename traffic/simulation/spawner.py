"""
simulation/spawner.py — VehicleSpawner: spawn di nuovi veicoli ai bordi.

Responsabilità:
    - Iterare i punti di ingresso della griglia
    - Decidere stocasticamente se spawnare un veicolo
    - Creare il veicolo con la factory
    - Rispettare il density cap
"""
from __future__ import annotations
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.config    import SimConfig
    from ..world.geometry import GridGeometry
    from ..agents.vehicle import Vehicle
    from ..agents.factory import VehicleFactory


class VehicleSpawner:
    """Genera nuovi veicoli ai bordi della griglia."""

    def __init__(
        self,
        cfg:     "SimConfig",
        geo:     "GridGeometry",
        factory: "VehicleFactory",
    ):
        self._cfg     = cfg
        self._geo     = geo
        self._factory = factory

    def spawn(self, cars: List["Vehicle"], occ: Dict) -> int:
        """
        Tenta lo spawn per ogni entry point della griglia.
        Restituisce il numero di veicoli effettivamente spawnati.
        """
        cfg = self._cfg
        geo = self._geo

        # Density cap: non spawnare se troppe auto
        density_limit = cfg.density_cap * geo.size * geo.size * 0.1
        if len(cars) > density_limit:
            return 0

        spawned = 0
        import random
        for r, c, dr, dc, direction, forced_intent in geo.spawn_entries():
            if random.random() >= cfg.spawn_for(direction):
                continue
            if (r, c) in occ:
                continue

            vehicle = self._factory.create(r, c, dr, dc, geo)

            # Applica intent forzato (corsia dedicata o slip exclusive)
            if forced_intent is not None:
                vehicle.intent = forced_intent
            elif geo.is_slip_exclusive_lane(r, c, dr, dc):
                vehicle.intent = "right"

            cars.append(vehicle)
            occ[(r, c)] = vehicle
            spawned += 1

        return spawned
