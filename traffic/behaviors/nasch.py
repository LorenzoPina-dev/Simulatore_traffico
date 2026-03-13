"""
behaviors/nasch.py — Nagel-Schreckenberg model (fallback a NaSch classico).

Usato quando use_idm=False. Modello cellulare discreto:
    1. Accelera di 1 se spd < ms
    2. Frena se gap < spd
    3. Dawdle con probabilità dw
"""
from __future__ import annotations
import random
from typing import TYPE_CHECKING, Set

from .interfaces import MovementBehavior

if TYPE_CHECKING:
    from ..agents.vehicle     import Vehicle
    from ..simulation.context import SimContext


class NaSchBehavior(MovementBehavior):
    """
    Nagel-Schreckenberg: modello cellulare discreto.
    Meno realistico di IDM ma computazionalmente più leggero.
    """

    def compute_velocity(
        self,
        vehicle: "Vehicle",
        context: "SimContext",
        extra_blocks: Set = None,
    ) -> float:
        extra  = extra_blocks or set()
        cfg    = context.cfg

        eff_max = min(vehicle.ms, cfg.max_speed)
        spd     = min(vehicle.spd + 1, eff_max)

        gap = context.gap_calc.gap_ahead(vehicle, context.occ, context.obs_set, extra)
        spd = min(spd, gap)

        eff_dw = min(vehicle.dw + vehicle.frus * cfg.frustration_dawdle_factor, 0.60)
        if not vehicle.in_inter and random.random() < eff_dw:
            spd = max(0, spd - 1)

        return float(spd)
