"""
infrastructure/gap_calculator.py — Servizio condiviso per il calcolo dei gap.

GapCalculator è un servizio stateless iniettato nel SimContext.
Evita di duplicare la logica di gap in IDM, NaSch, MOBIL, ecc.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Optional, Set, Tuple

if TYPE_CHECKING:
    from ..core.config  import SimConfig
    from ..world.geometry import GridGeometry


class GapCalculator:
    """
    Calcola il gap davanti/dietro e la velocità del leader.

    Tutti i metodi sono puri (nessun side effect) e operano su
    snapshot della mappa occupazione passati come parametri.
    """

    def __init__(self, cfg: "SimConfig", geo: "GridGeometry"):
        self._cfg = cfg
        self._geo = geo

    # ─────────────────────────────────────────────────────────────────
    # Gap ahead / rear — interfaccia con Vehicle
    # ─────────────────────────────────────────────────────────────────

    def gap_ahead(
        self,
        vehicle,
        occ:      Dict,
        obs_set:  Set,
        extra:    Optional[Set] = None,
        lookahead: int = 0,
    ) -> int:
        """Gap davanti al veicolo nella sua direzione di marcia."""
        return self.gap_ahead_at(
            vehicle.r, vehicle.c, vehicle.dr, vehicle.dc,
            occ, obs_set, extra, lookahead,
        )

    def gap_rear(
        self,
        vehicle,
        occ:       Dict,
        lookbehind: int = 0,
    ) -> int:
        """Gap dietro al veicolo (nella direzione opposta)."""
        return self.gap_rear_at(
            vehicle.r, vehicle.c, vehicle.dr, vehicle.dc,
            occ, lookbehind,
        )

    def leader_speed(
        self,
        vehicle,
        occ:      Dict,
        obs_set:  Set,
        extra:    Optional[Set] = None,
        gap:      Optional[int] = None,
    ) -> float:
        """Velocità del veicolo immediatamente davanti a vehicle."""
        g = gap if gap is not None else self.gap_ahead(vehicle, occ, obs_set, extra)
        return self._leader_speed_at(
            vehicle.r, vehicle.c, vehicle.dr, vehicle.dc,
            occ, obs_set, extra or set(), g,
        )

    # ─────────────────────────────────────────────────────────────────
    # Varianti "at" — accettano coordinate esplicite (usate da MOBIL)
    # ─────────────────────────────────────────────────────────────────

    def gap_ahead_at(
        self,
        r: int, c: int, dr: int, dc: int,
        occ:      Dict,
        obs_set:  Set,
        extra:    Optional[Set] = None,
        lookahead: int = 0,
    ) -> int:
        """Gap da una cella arbitraria nella direzione (dr, dc)."""
        if lookahead == 0:
            lookahead = self._cfg.max_speed + 4
        extra = extra or set()
        geo   = self._geo
        for d in range(1, lookahead + 1):
            nr = r + dr * d
            nc = c + dc * d
            if not geo.in_bounds(nr, nc): return lookahead
            if (nr, nc) in occ:           return d - 1
            if (nr, nc) in obs_set:       return d - 1
            if (nr, nc) in extra:         return d - 1
        return lookahead

    def gap_rear_at(
        self,
        r: int, c: int, dr: int, dc: int,
        occ:        Dict,
        lookbehind: int = 0,
    ) -> int:
        """Gap dietro da una cella arbitraria nella direzione (dr, dc)."""
        if lookbehind == 0:
            lookbehind = self._cfg.max_speed + 2
        geo = self._geo
        for d in range(1, lookbehind + 1):
            nr = r - dr * d
            nc = c - dc * d
            if not geo.in_bounds(nr, nc): return lookbehind
            if (nr, nc) in occ:           return d - 1
        return lookbehind

    # ─────────────────────────────────────────────────────────────────
    # Velocità del leader (usato da IDM)
    # ─────────────────────────────────────────────────────────────────

    def _leader_speed_at(
        self,
        r: int, c: int, dr: int, dc: int,
        occ:     Dict,
        obs_set: Set,
        extra:   Set,
        gap:     int,
    ) -> float:
        """
        Velocità del veicolo leader davanti a (r,c).
        Restituisce 0.0 se c'è una parete virtuale, v_max+2 se strada libera.
        """
        look = gap + 2
        geo  = self._geo
        v_free = float(self._cfg.max_speed + 2)
        for d in range(1, look + 1):
            nr = r + dr * d
            nc = c + dc * d
            if not geo.in_bounds(nr, nc): return v_free
            if (nr, nc) in extra:         return 0.0
            if (nr, nc) in obs_set:       return 0.0
            leader = occ.get((nr, nc))
            if leader is not None:        return leader.v_float
        return v_free
