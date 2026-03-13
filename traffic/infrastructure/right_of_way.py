"""
infrastructure/right_of_way.py — Logica di precedenza (right-of-way).

Regole supportate (via TopologyConfig.row_yield_to):
    "right"    — precedenza a destra (regola italiana)
    "left"     — precedenza a sinistra (rotatoria)
    "oncoming" — solo chi gira a sinistra cede al traffico opposto

La probabilità di ignorare la precedenza dipende da:
    - profilo di personalità (ignore_row_prob)
    - frustrazione accumulata
    - distanza dall'incrocio
    - gap verso il veicolo con precedenza
    - anti-deadlock: se fermo da troppi step, forza il passaggio
"""
from __future__ import annotations
import random
from typing import Dict, List, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.config    import SimConfig
    from ..world.geometry import GridGeometry
    from ..agents.vehicle import Vehicle


# Mapping "mia direzione" → "direzione di chi ha precedenza"
# Regola "right" (precedenza a destra):
_YIELD_RIGHT: dict[Tuple[int,int], Tuple[int,int]] = {
    (0,  1): (-1, 0),   # → cede a ↑
    (-1, 0): (0, -1),   # ↑ cede a ←
    (0, -1): (1,  0),   # ← cede a ↓
    (1,  0): (0,  1),   # ↓ cede a →
}
# Regola "left" (rotatoria):
_YIELD_LEFT: dict[Tuple[int,int], Tuple[int,int]] = {
    (0,  1): (1,  0),   # → cede a ↓
    (1,  0): (0, -1),   # ↓ cede a ←
    (0, -1): (-1, 0),   # ← cede a ↑
    (-1, 0): (0,  1),   # ↑ cede a →
}

_DEADLOCK_BREAK_THRESHOLD = 25


class RightOfWayChecker:
    """
    Valuta se un veicolo deve cedere la precedenza.

    API pubblica:
        should_yield(vehicle, occ, step) → bool
        yield_block_cell(vehicle)        → Set
        is_approaching(vehicle)          → bool
        oncoming_threat(vehicle, occ)    → bool
    """

    def __init__(self, cfg: "SimConfig", geo: "GridGeometry"):
        self._cfg = cfg
        self._geo = geo

    def _rule(self) -> str:
        rule = getattr(self._geo.topo, "row_yield_to", "oncoming")
        return rule if rule in ("right", "left", "oncoming") else "oncoming"

    # ── API ───────────────────────────────────────────────────────────

    def should_yield(self, vehicle: "Vehicle", occ: Dict, step: int) -> bool:
        """
        True se il veicolo deve cedere la precedenza questo step.
        Campionato una volta per step e memoizzato su vehicle._row_val.
        """
        if not self._cfg.row_enabled:          return False
        if vehicle.in_inter:                   return False
        if not self.is_approaching(vehicle):   return False
        if vehicle.t_stop >= _DEADLOCK_BREAK_THRESHOLD:
            vehicle._row_val = False; vehicle._row_step = step
            return False
        if vehicle.intent == "left":
            if self._threat_oncoming(vehicle, occ, self._cfg.row_oncoming_check):
                vehicle._row_val = True
                vehicle._row_step = step
                return True
        if self._rule() == "oncoming" and vehicle.intent != "left":
            return False

        if vehicle._row_step != step:
            vehicle._row_step = step
            threat = self.oncoming_threat(vehicle, occ)
            if not threat:
                vehicle._row_val = False
            else:
                gap   = self._gap_to_threat(vehicle, occ)
                p_ign = self._ignore_prob(vehicle, gap)
                vehicle._row_val = (random.random() >= p_ign)

        return vehicle._row_val

    def yield_block_cell(self, vehicle: "Vehicle") -> Set:
        """Prima cella di ingresso nell'incrocio (da bloccare mentre si cede)."""
        geo = self._geo
        if vehicle.dc == 1:   return {(vehicle.r, geo.ic0)}
        if vehicle.dc == -1:  return {(vehicle.r, geo.ic1)}
        if vehicle.dr == 1:   return {(geo.ir0, vehicle.c)}
        return {(geo.ir1, vehicle.c)}

    def is_approaching(self, vehicle: "Vehicle") -> bool:
        """True se il veicolo è entro row_lookahead celle dall'incrocio."""
        geo = self._geo
        lk  = self._cfg.row_lookahead
        if vehicle.dc == 1:   return geo.ic0 - lk <= vehicle.c < geo.ic0
        if vehicle.dc == -1:  return geo.ic1 < vehicle.c <= geo.ic1 + lk
        if vehicle.dr == 1:   return geo.ir0 - lk <= vehicle.r < geo.ir0
        return geo.ir1 < vehicle.r <= geo.ir1 + lk

    def oncoming_threat(self, vehicle: "Vehicle", occ: Dict) -> bool:
        """True se esiste un veicolo con precedenza nel percorso di conflitto."""
        rule = self._rule()
        chk  = self._cfg.row_oncoming_check
        if rule == "oncoming":
            return self._threat_oncoming(vehicle, occ, chk)
        pdr, pdc = (_YIELD_RIGHT if rule == "right" else _YIELD_LEFT).get(
            (vehicle.dr, vehicle.dc), (0, 0))
        return self._threat_from_direction(vehicle, occ, pdr, pdc, chk)

    # ── Implementazioni per regola ────────────────────────────────────

    def _threat_oncoming(self, vehicle: "Vehicle", occ: Dict, chk: int) -> bool:
        odr, odc = -vehicle.dr, -vehicle.dc
        for (r, c) in self._oncoming_cells(vehicle, chk):
            other = occ.get((r, c))
            if other and (other.dr, other.dc) == (odr, odc) and other.intent != "left":
                return True
        return False

    def _threat_from_direction(self, vehicle: "Vehicle", occ: Dict,
                                pdr: int, pdc: int, chk: int) -> bool:
        if (pdr, pdc) == (0, 0):
            return False
        cells = self._inter_cells_for(pdr, pdc) + self._approach_cells_for(pdr, pdc, chk)
        for (r, c) in cells:
            other = occ.get((r, c))
            if other and (other.dr, other.dc) == (pdr, pdc):
                if self._dist_to_inter(other) <= chk:
                    return True
        return False

    # ── Calcolo probabilità di ignorare ──────────────────────────────

    def _ignore_prob(self, vehicle: "Vehicle", threat_gap: int) -> float:
        geo = self._geo
        if vehicle.dc == 1:      dist = max(0, geo.ic0 - vehicle.c)
        elif vehicle.dc == -1:   dist = max(0, vehicle.c - geo.ic1)
        elif vehicle.dr == 1:    dist = max(0, geo.ir0 - vehicle.r)
        else:                    dist = max(0, vehicle.r - geo.ir1)

        max_dist = self._cfg.row_lookahead
        distance_bonus = 0.0
        if max_dist > 0 and dist > 0:
            distance_bonus = max(0, 1.0 - dist / max_dist) * self._cfg.row_distance_weight

        max_gap   = self._cfg.row_yield_gap * 2
        gap_penalty = 0.0
        if threat_gap < max_gap:
            gap_penalty = (1.0 - threat_gap / max_gap) * self._cfg.row_gap_weight

        p = vehicle.ir + vehicle.frus * self._cfg.row_frustration_factor + distance_bonus - gap_penalty
        return max(0.05, min(p, 0.95))

    def _gap_to_threat(self, vehicle: "Vehicle", occ: Dict) -> int:
        rule = self._rule()
        chk  = self._cfg.row_oncoming_check
        if rule == "oncoming":
            odr, odc = -vehicle.dr, -vehicle.dc
            min_g = float("inf")
            for (r, c) in self._oncoming_cells(vehicle, chk):
                other = occ.get((r, c))
                if other and (other.dr, other.dc) == (odr, odc) and other.intent != "left":
                    g = self._dist_to_inter(other) + self._dist_to_inter(vehicle)
                    min_g = min(min_g, g)
            return int(min_g) if min_g != float("inf") else chk + 1
        else:
            pdr, pdc = (_YIELD_RIGHT if rule == "right" else _YIELD_LEFT).get(
                (vehicle.dr, vehicle.dc), (0, 0))
            if (pdr, pdc) == (0, 0):
                return chk + 1
            cells = self._inter_cells_for(pdr, pdc) + self._approach_cells_for(pdr, pdc, chk)
            min_g = float("inf")
            for (r, c) in cells:
                other = occ.get((r, c))
                if other and (other.dr, other.dc) == (pdr, pdc):
                    g = self._dist_to_inter(other) + self._dist_to_inter(vehicle)
                    min_g = min(min_g, g)
            return int(min_g) if min_g != float("inf") else chk + 1

    # ── Celle da scansionare ──────────────────────────────────────────

    def _oncoming_cells(self, vehicle: "Vehicle", look: int) -> List[Tuple]:
        geo = self._geo
        cells: List[Tuple] = []
        if vehicle.dc == 1:
            for r in range(geo.ir0, geo.center_r):
                for c in range(geo.ic0, geo.ic1+1): cells.append((r, c))
                for c in range(geo.ic1+1, geo.ic1+1+look):
                    if geo.in_bounds(r, c): cells.append((r, c))
        elif vehicle.dc == -1:
            for r in range(geo.center_r, geo.ir1+1):
                for c in range(geo.ic0, geo.ic1+1): cells.append((r, c))
                for c in range(max(0, geo.ic0-look), geo.ic0):
                    if geo.in_bounds(r, c): cells.append((r, c))
        elif vehicle.dr == 1:
            for c in range(geo.center_c, geo.ic1+1):
                for r in range(geo.ir0, geo.ir1+1): cells.append((r, c))
                for r in range(geo.ir1+1, geo.ir1+1+look):
                    if geo.in_bounds(r, c): cells.append((r, c))
        else:
            for c in range(geo.ic0, geo.center_c):
                for r in range(geo.ir0, geo.ir1+1): cells.append((r, c))
                for r in range(max(0, geo.ir0-look), geo.ir0):
                    if geo.in_bounds(r, c): cells.append((r, c))
        return cells

    def _inter_cells_for(self, pdr: int, pdc: int) -> List[Tuple]:
        geo = self._geo
        cells: List[Tuple] = []
        if pdc == 1:
            for r in range(geo.center_r, geo.ir1+1):
                for c in range(geo.ic0, geo.ic1+1): cells.append((r, c))
        elif pdc == -1:
            for r in range(geo.ir0, geo.center_r):
                for c in range(geo.ic0, geo.ic1+1): cells.append((r, c))
        elif pdr == 1:
            for c in range(geo.ic0, geo.center_c):
                for r in range(geo.ir0, geo.ir1+1): cells.append((r, c))
        else:
            for c in range(geo.center_c, geo.ic1+1):
                for r in range(geo.ir0, geo.ir1+1): cells.append((r, c))
        return cells

    def _approach_cells_for(self, pdr: int, pdc: int, chk: int) -> List[Tuple]:
        geo = self._geo
        cells: List[Tuple] = []
        if pdc == 1:
            for r in range(geo.center_r, geo.ir1+1):
                for c in range(max(0, geo.ic0-chk), geo.ic0): cells.append((r, c))
        elif pdc == -1:
            for r in range(geo.ir0, geo.center_r):
                for c in range(geo.ic1+1, min(geo.size, geo.ic1+1+chk)): cells.append((r, c))
        elif pdr == 1:
            for c in range(geo.ic0, geo.center_c):
                for r in range(max(0, geo.ir0-chk), geo.ir0): cells.append((r, c))
        else:
            for c in range(geo.center_c, geo.ic1+1):
                for r in range(geo.ir1+1, min(geo.size, geo.ir1+1+chk)): cells.append((r, c))
        return cells

    def _dist_to_inter(self, vehicle: "Vehicle") -> int:
        geo = self._geo
        if vehicle.dc == 1:   return max(0, geo.ic0 - vehicle.c)
        if vehicle.dc == -1:  return max(0, vehicle.c - geo.ic1)
        if vehicle.dr == 1:   return max(0, geo.ir0 - vehicle.r)
        return max(0, vehicle.r - geo.ir1)

    def __repr__(self) -> str:
        return f"RightOfWayChecker(rule={self._rule()!r}, enabled={self._cfg.row_enabled})"
