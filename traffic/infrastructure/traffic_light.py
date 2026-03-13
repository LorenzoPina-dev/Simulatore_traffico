"""
infrastructure/traffic_light.py — Semaforo e politiche di ciclo.

Fasi: HG (H verde), HY (H giallo), VG (V verde), VY (V giallo), ALL (no semaforo).
Politiche: FIXED, ADAPTIVE, ALWAYS_GREEN_H/V, NO_LIGHT.
Emergency preemption: forza verde nella direzione dell'ambulanza.
"""
from __future__ import annotations
import random
from typing import TYPE_CHECKING, List, Set

from ..core.types import LightPolicy, VehicleType

if TYPE_CHECKING:
    from ..core.config    import SimConfig
    from ..world.geometry import GridGeometry
    from ..agents.vehicle import Vehicle


class TrafficLight:
    """
    Semaforo per un incrocio a +.

    Il semaforo gestisce il ciclo delle fasi e la preemption d'emergenza.
    Non contiene logica di precedenza (quella è in RightOfWayChecker).
    """

    def __init__(self, cfg: "SimConfig", geo: "GridGeometry"):
        self._policy       = cfg.light_policy
        self._green_h      = cfg.light_green_h
        self._green_v      = cfg.light_green_v
        self._yellow       = cfg.light_yellow
        self._min_g        = cfg.light_min_green
        self._max_g        = cfg.light_max_green
        self._check        = cfg.adaptive_check_interval
        self._geo          = geo
        self._preempt_dist = cfg.emergency_preempt_dist
        self._t            = 0
        self._phase        = self._initial_phase()

    def _initial_phase(self) -> str:
        if self._policy == LightPolicy.NO_LIGHT:       return "ALL"
        if self._policy == LightPolicy.ALWAYS_GREEN_H: return "HG"
        if self._policy == LightPolicy.ALWAYS_GREEN_V: return "VG"
        return "HG"

    # ── Ciclo ─────────────────────────────────────────────────────────

    def tick(self, cars: List["Vehicle"]):
        """Avanza il ciclo semaforico di uno step."""
        if self._policy in (LightPolicy.NO_LIGHT,
                            LightPolicy.ALWAYS_GREEN_H,
                            LightPolicy.ALWAYS_GREEN_V):
            return
        self._t += 1
        if self._policy == LightPolicy.FIXED:
            self._tick_fixed()
        elif self._policy == LightPolicy.ADAPTIVE:
            self._tick_adaptive(cars)

    def _tick_fixed(self):
        transitions = {
            "HG": (self._green_h, "HY"),
            "HY": (self._yellow,  "VG"),
            "VG": (self._green_v, "VY"),
            "VY": (self._yellow,  "HG"),
        }
        duration, next_phase = transitions.get(self._phase, (9999, self._phase))
        if self._t >= duration:
            self._phase = next_phase
            self._t     = 0

    def _tick_adaptive(self, cars: List["Vehicle"]):
        if self._phase in ("HY", "VY"):
            if self._t >= self._yellow:
                self._phase = "VG" if self._phase == "HY" else "HG"
                self._t     = 0
            return
        if self._t < self._min_g:
            return
        if self._t >= self._max_g:
            self._start_yellow()
            return
        if self._t % self._check == 0:
            h_q = self._count_queue(cars, horizontal=True)
            v_q = self._count_queue(cars, horizontal=False)
            if self._phase == "HG" and v_q > h_q * 1.5:
                self._start_yellow()
            elif self._phase == "VG" and h_q > v_q * 1.5:
                self._start_yellow()

    def _start_yellow(self):
        if self._phase == "HG":   self._phase = "HY"
        elif self._phase == "VG": self._phase = "VY"
        self._t = 0

    def _count_queue(self, cars: List["Vehicle"], horizontal: bool) -> int:
        geo = self._geo
        return sum(
            1 for c in cars
            if (c.dc != 0) == horizontal
            and not geo.in_intersection(c.r, c.c)
            and c.spd == 0
        )

    # ── Emergency preemption ──────────────────────────────────────────

    def emergency_preempt(self, cars: List["Vehicle"], geo: "GridGeometry"):
        """
        Se un veicolo di emergenza con sirena è vicino all'incrocio,
        forza il verde nella sua direzione di marcia.
        """
        if self._policy in (LightPolicy.NO_LIGHT,
                            LightPolicy.ALWAYS_GREEN_H,
                            LightPolicy.ALWAYS_GREEN_V):
            return

        for car in cars:
            if car.vtype != VehicleType.EMERGENCY or not car.siren:
                continue
            dist = self._dist_to_intersection(car, geo)
            if dist > self._preempt_dist:
                continue
            target = "HG" if car.dc != 0 else "VG"
            if self._phase != target:
                self._phase = target
                self._t     = 0
            break

    @staticmethod
    def _dist_to_intersection(car: "Vehicle", geo: "GridGeometry") -> int:
        if car.dc == 1:   return max(0, geo.ic0 - car.c)
        if car.dc == -1:  return max(0, car.c - geo.ic1)
        if car.dr == 1:   return max(0, geo.ir0 - car.r)
        return                   max(0, car.r - geo.ir1)

    # ── Stato ─────────────────────────────────────────────────────────

    def h_go(self) -> bool:
        return self._phase in ("HG", "HY", "ALL")

    def v_go(self) -> bool:
        return self._phase in ("VG", "VY", "ALL")

    def is_yellow(self) -> bool:
        return self._phase in ("HY", "VY")

    def go_for(self, vehicle: "Vehicle") -> bool:
        return self.h_go() if vehicle.dc != 0 else self.v_go()

    def phase_label(self) -> str:
        return {
            "HG": "H:VERDE   V:ROSSO",
            "HY": "H:GIALLO  V:ROSSO",
            "VG": "H:ROSSO   V:VERDE",
            "VY": "H:ROSSO   V:GIALLO",
            "ALL": "LIBERO (no semaforo)",
        }.get(self._phase, self._phase)

    def stop_line_colors(self) -> tuple:
        """Colori della stop line per il renderer (H, V)."""
        if self._phase == "HG":  return (9, 8)
        if self._phase == "VG":  return (8, 9)
        if self._phase == "ALL": return (9, 9)
        return (10, 10)

    def red_block_cells(self, vehicle: "Vehicle", step: int, geo: "GridGeometry") -> Set:
        """
        Celle virtuali bloccate dal semaforo per questo veicolo.
        I veicoli di emergenza con sirena ignorano sempre il semaforo.
        """
        if getattr(vehicle, "siren", False):
            return set()
        if self.go_for(vehicle):
            return set()

        # Campionamento memoizzato del "passa col rosso"
        if vehicle._rr_step != step:
            vehicle._rr_step = step
            vehicle._rr_val  = (random.random() < vehicle.rr)

        if vehicle._rr_val:
            return set()

        r, c = vehicle.r, vehicle.c
        if vehicle.dc == 1:   return {(r, geo.ic0 - 1)}
        if vehicle.dc == -1:  return {(r, geo.ic1 + 1)}
        if vehicle.dr == 1:   return {(geo.ir0 - 1, c)}
        return {(geo.ir1 + 1, c)}
