"""
geometry.py — Geometria della griglia e funzioni spaziali.

GridGeometry calcola e memorizza tutti i bounds dell'incrocio
e fornisce metodi per query spaziali (in_intersection, lane_index, ecc.).
E' costruita a partire da SimConfig ed e' read-only dopo la costruzione.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import SimConfig


class GridGeometry:
    """
    Descrive la geometria della griglia: dimensioni, bounds dell'incrocio,
    mappature corsia->indice.

    Attributi calcolati:
        size    : lato della griglia
        center  : cella centrale (size // 2)
        half    : num_lanes (meta' larghezza di ogni asse)
        ir0, ir1: prima e ultima riga dell'incrocio
        ic0, ic1: prima e ultima colonna dell'incrocio
    """

    def __init__(self, cfg: "SimConfig"):
        self.size   = cfg.grid_size
        self.half   = cfg.num_lanes    # corsie per senso = meta' larghezza asse
        self.center = cfg.grid_size // 2

        # Bounds zona incrocio
        self.ir0 = self.center - self.half          # prima riga
        self.ir1 = self.center + self.half - 1      # ultima riga
        self.ic0 = self.center - self.half          # prima colonna
        self.ic1 = self.center + self.half - 1      # ultima colonna

    # ── Query spaziali ────────────────────────────────────────────────

    def in_intersection(self, r: int, c: int) -> bool:
        """True se la cella (r,c) e' dentro la zona a +."""
        return self.ir0 <= r <= self.ir1 and self.ic0 <= c <= self.ic1

    def on_road(self, r: int, c: int) -> bool:
        """True se la cella appartiene a uno qualsiasi dei due assi stradali."""
        on_h = self.ir0 <= r <= self.ir1
        on_v = self.ic0 <= c <= self.ic1
        return on_h or on_v

    def in_bounds(self, r: int, c: int) -> bool:
        """True se la cella e' dentro la griglia."""
        return 0 <= r < self.size and 0 <= c < self.size

    # ── Indice corsia ─────────────────────────────────────────────────

    def lane_index(self, r: int, c: int, dr: int, dc: int) -> int:
        """
        Calcola l'indice di corsia relativo alla direzione di marcia.

        Convenzione:
            0          = corsia destra  (svolta destra o dritto)
            num_lanes-1 = corsia sinistra (svolta sinistra o dritto)

        La "corsia destra" e' quella piu' vicina al bordo destro
        rispetto alla direzione di marcia:
            ->  la corsia piu' a SUD    (r massimo)
            <-  la corsia piu' a NORD   (r minimo)
            v   la corsia piu' a OVEST  (c minimo)
            ^   la corsia piu' a EST    (c massimo)
        """
        c_hi = self.center
        r_lo = self.center - self.half
        r_hi = self.center + self.half - 1
        c_lo = self.center - self.half

        if dc == 1:   return r_hi - r          # -> : lane 0 = riga piu' alta
        if dc == -1:  return r - r_lo          # <- : lane 0 = riga piu' bassa
        if dr == 1:   return c - c_hi          # v  : lane 0 = col centrale sinistra
        if dr == -1:  return (c_hi - 1) - c   # ^  : lane 0 = col centrale destra
        return 0

    # ── Punti di spawn ────────────────────────────────────────────────

    def spawn_entries(self):
        """
        Genera tutti i punti di ingresso ai bordi della griglia.

        Yields:
            (row, col, dr, dc, direction_label)
                dr, dc  : vettore direzione
                direction_label: 'east' | 'west' | 'south' | 'north'
        """
        # Corsie -> (EST): righe da center a ir1
        for r in range(self.center, self.ir1 + 1):
            yield (r, 0, 0, 1, "east")

        # Corsie <- (OVEST): righe da ir0 a center-1
        for r in range(self.ir0, self.center):
            yield (r, self.size - 1, 0, -1, "west")

        # Corsie v (SUD): colonne da center a ic1
        for c in range(self.center, self.ic1 + 1):
            yield (0, c, 1, 0, "south")

        # Corsie ^ (NORD): colonne da ic0 a center-1
        for c in range(self.ic0, self.center):
            yield (self.size - 1, c, -1, 0, "north")

    # ── Validita' corsia per direzione ────────────────────────────────

    def valid_lane_cell(self, r: int, c: int, dr: int, dc: int) -> bool:
        """
        True se la cella (r,c) e' una corsia valida per la direzione (dr,dc).
        Usato per verificare che un cambio corsia resti nella carreggiata corretta.
        """
        if dc == 1:   return self.center <= r <= self.ir1
        if dc == -1:  return self.ir0 <= r < self.center
        if dr == 1:   return self.center <= c <= self.ic1
        if dr == -1:  return self.ic0 <= c < self.center
        return False

    # ── Informazioni debug ────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"GridGeometry(size={self.size}, half={self.half}, "
            f"center={self.center}, "
            f"ir=[{self.ir0},{self.ir1}], ic=[{self.ic0},{self.ic1}])"
        )
