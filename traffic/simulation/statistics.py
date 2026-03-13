"""
simulation/statistics.py — Raccolta statistiche di simulazione.

SimStatistics raccoglie i contatori cumulativi e calcola le statistiche
aggregate da presentare al renderer e all'utente.
"""
from __future__ import annotations
from typing import Dict, List, TYPE_CHECKING

from ..core.types import VehicleType

if TYPE_CHECKING:
    from ..agents.vehicle import Vehicle


class SimStatistics:
    """Contatori cumulativi e statistiche istantanee."""

    def __init__(self):
        self.total_spawned        = 0
        self.total_accidents      = 0
        self.total_red_runners    = 0
        self.total_row_violations = 0   # veicoli che avevano minaccia e NON hanno ceduto
        self.total_row_yields     = 0   # veicoli che hanno correttamente ceduto
        self.total_slip_uses      = 0
        self.total_emergency      = 0   # veicoli di emergenza spawnati
        self.last_spawn_rate      = 0.0 # prob. spawn effettiva dell'ultimo step

    def snapshot(self, cars: List["Vehicle"], step: int, light_label: str) -> Dict:
        """Restituisce un dict con le statistiche correnti."""
        n = len(cars)
        avg_speed = sum(c.spd  for c in cars) / n if n else 0.0
        avg_frus  = sum(c.frus for c in cars) / n if n else 0.0

        waiting_row = sum(
            1 for c in cars
            if c._row_val and c._row_step == step
        )
        in_transit = sum(1 for c in cars if c.inter_path)

        by_type: Dict[str, int] = {vt.name: 0 for vt in VehicleType}
        for c in cars:
            by_type[c.vtype.name] += 1
        self.total_emergency = by_type.get("EMERGENCY", 0)  # snapshot corrente

        platoon_ids  = {c.platoon_id for c in cars if c.platoon_id != -1}
        num_platoons = len(platoon_ids)
        in_platoon   = sum(1 for c in cars if c.platoon_id != -1)

        return dict(
            step          = step,
            cars          = n,
            avg_speed     = avg_speed,
            avg_frus      = avg_frus,
            total_spawned = self.total_spawned,
            total_acc     = self.total_accidents,
            total_rr      = self.total_red_runners,
            total_row_vio = self.total_row_violations,
            total_row_yld = self.total_row_yields,
            waiting_row   = waiting_row,
            total_slip    = self.total_slip_uses,
            slip_active   = sum(1 for c in cars if c.slip_path),
            inter_transit = in_transit,
            light_phase   = light_label,
            by_type              = by_type,
            num_platoons         = num_platoons,
            in_platoon           = in_platoon,
            total_em             = by_type.get("EMERGENCY", 0),
            total_platoon_formed = num_platoons,
            # rapporto violazioni / (violazioni + yields) come metrica qualità ROW
            row_compliance_rate  = (
                round(self.total_row_yields /
                      max(1, self.total_row_yields + self.total_row_violations), 3)
            ),
            spawn_rate = self.last_spawn_rate,
        )
