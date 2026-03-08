"""
geometry.py — Geometria della griglia e funzioni spaziali.

GridGeometry calcola e memorizza tutti i bounds dell'incrocio
a partire da SimConfig + TopologyConfig.

Slip lane trigger (bypass destra):
    Il trigger e' posizionato 2 celle PRIMA della stop line, cosi'
    il percorso bypass NON passa mai per la cella del semaforo rosso.
    Il path inizia con un "hook" perpendicolare che porta l'auto
    nella riga/colonna adiacente esterna (sotto/sopra/destra/sinistra
    del bordo stradale), poi ripiega per rientrare nel percorso L.

    SW (→→↓): trigger (ir1, ic0-3)
      hook: (ir1+1,ic0-3)→(ir1+1,ic0-2)→(ir1+1,ic0-1)
      L-leg: (ir1+2,ic0-1)…(ir1+N,ic0-1)   exit→(ir1+N,ic0) ↓

    NW (↓→←): trigger (ir0-3, ic0)
      hook: (ir0-3,ic0-1)→(ir0-2,ic0-1)→(ir0-1,ic0-1)
      L-leg: (ir0-1,ic0-2)…(ir0-1,ic0-N)   exit→(ir0,ic0-N) ←

    NE (←→↑): trigger (ir0, ic1+3)
      hook: (ir0-1,ic1+3)→(ir0-1,ic1+2)→(ir0-1,ic1+1)
      L-leg: (ir0-2,ic1+1)…(ir0-N,ic1+1)   exit→(ir0-N,ic1) ↑

    SE (↑→→): trigger (ir1+3, ic1)
      hook: (ir1+3,ic1+1)→(ir1+2,ic1+1)→(ir1+1,ic1+1)
      L-leg: (ir1+1,ic1+2)…(ir1+1,ic1+N)   exit→(ir1,ic1+N) →

Convenzione CODICE DELLA STRADA (guida a DESTRA):
    WEST segment  →  righe [center_r … ir1]
    EAST segment  ←  righe [ir0 … center_r-1]
    NORTH segment ↓  colonne [ic0 … center_c-1]
    SOUTH segment ↑  colonne [center_c … ic1]
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Iterator, Optional, Tuple, Dict, List, Set, NamedTuple

if TYPE_CHECKING:
    from .config   import SimConfig
    from .topology import TopologyConfig

# Celle prima della stop line in cui il trigger slip viene arretrato.
# 2 = trigger a ic0-3 (1 cella stop line + 2 offset).
_SLIP_PRETRIGGER = 2


class SlipEntry(NamedTuple):
    """
    Descrive un singolo slip lane (bypass fisico a L attorno a un angolo).

    Il percorso bypassa la stop line grazie a un "hook" iniziale
    perpendicolare che porta l'auto fuori dalla corsia principale
    prima di raggiungere la cella del semaforo.

    entry_r, entry_c   : cella trigger (2 celle prima della stop line)
    entry_dr, entry_dc : direzione in entrata
    exit_r,  exit_c    : prima cella sulla strada di uscita
    exit_dr, exit_dc   : direzione di uscita
    corner             : angolo ('SW'|'NW'|'NE'|'SE')
    path               : sequenza ordinata (r,c) - hook + L-leg + exit
    visual_cells       : celle bypass (path senza exit) da colorare
    """
    entry_r:      int
    entry_c:      int
    entry_dr:     int
    entry_dc:     int
    exit_r:       int
    exit_c:       int
    exit_dr:      int
    exit_dc:      int
    corner:       str
    path:         tuple
    visual_cells: tuple


class GridGeometry:
    """Geometria completa dell'incrocio, calcolata da SimConfig + TopologyConfig."""

    def __init__(self, cfg: "SimConfig"):
        from .topology import TopologyConfig, RoadSegment

        self.size = cfg.grid_size
        topo: TopologyConfig = cfg.topology
        self.topo = topo
        default_lanes = cfg.num_lanes

        grid_mid = cfg.grid_size // 2
        self.center_r = grid_mid + topo.center_row_offset
        self.center_c = grid_mid + topo.center_col_offset

        self.lanes_east  = topo.west.inbound(default_lanes)  if topo.west.enabled  else 0
        self.lanes_west  = topo.east.inbound(default_lanes)  if topo.east.enabled  else 0
        self.lanes_south = topo.north.inbound(default_lanes) if topo.north.enabled else 0
        self.lanes_north = topo.south.inbound(default_lanes) if topo.south.enabled else 0

        self.ir0 = self.center_r - self.lanes_west
        self.ir1 = self.center_r + self.lanes_east - 1
        self.ic0 = self.center_c - self.lanes_south
        self.ic1 = self.center_c + self.lanes_north - 1

        self.center = grid_mid
        self.half   = max(default_lanes,
                          self.lanes_east, self.lanes_west,
                          self.lanes_south, self.lanes_north)

        self._slip_entries: List[SlipEntry] = self._compute_slip_entries()
        self._slip_entry_map: Dict[Tuple, SlipEntry] = {
            (e.entry_r, e.entry_c, e.entry_dr, e.entry_dc): e
            for e in self._slip_entries
        }
        self._slip_visual_cells: Set[Tuple[int,int]] = {
            cell for e in self._slip_entries for cell in e.visual_cells
        }
        self._slip_path_cells: Set[Tuple[int,int]] = {
            cell for e in self._slip_entries for cell in e.path
        }

    # ── Query spaziali ────────────────────────────────────────────────

    def in_intersection(self, r: int, c: int) -> bool:
        return self.ir0 <= r <= self.ir1 and self.ic0 <= c <= self.ic1

    def on_road(self, r: int, c: int) -> bool:
        in_h_rows = self.ir0 <= r <= self.ir1
        in_v_cols = self.ic0 <= c <= self.ic1
        return in_h_rows or in_v_cols

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.size and 0 <= c < self.size

    # ── Indice corsia ─────────────────────────────────────────────────

    def lane_index(self, r: int, c: int, dr: int, dc: int) -> int:
        if dc == 1:   return self.ir1 - r
        if dc == -1:  return r - self.ir0
        if dr == 1:   return c - self.ic0
        if dr == -1:  return self.ic1 - c
        return 0

    def lanes_for_direction(self, dr: int, dc: int) -> int:
        if dc == 1:  return self.lanes_east
        if dc == -1: return self.lanes_west
        if dr == 1:  return self.lanes_south
        return self.lanes_north

    # ── Corsie dedicate ───────────────────────────────────────────────

    def forced_intent_at(self, r: int, c: int, dr: int, dc: int) -> Optional[str]:
        topo = self.topo
        if dc == 1:    seg = topo.west;  li = self.lane_index(r, c, dr, dc); total = self.lanes_east
        elif dc == -1: seg = topo.east;  li = self.lane_index(r, c, dr, dc); total = self.lanes_west
        elif dr == 1:  seg = topo.north; li = self.lane_index(r, c, dr, dc); total = self.lanes_south
        else:          seg = topo.south; li = self.lane_index(r, c, dr, dc); total = self.lanes_north
        return seg.forced_intent(li, total)

    def dedicated_road_cells(self) -> Dict[Tuple[int, int], str]:
        cells: Dict[Tuple[int, int], str] = {}
        topo  = self.topo

        if topo.west.enabled:
            total = self.lanes_east
            for r in range(self.center_r, self.ir1 + 1):
                li = self.ir1 - r
                fi = topo.west.forced_intent(li, total)
                if fi:
                    for c in range(0, self.ic0):
                        cells[(r, c)] = fi

        if topo.east.enabled:
            total = self.lanes_west
            for r in range(self.ir0, self.center_r):
                li = r - self.ir0
                fi = topo.east.forced_intent(li, total)
                if fi:
                    for c in range(self.ic1 + 1, self.size):
                        cells[(r, c)] = fi

        if topo.north.enabled:
            total = self.lanes_south
            for c in range(self.ic0, self.center_c):
                li = c - self.ic0
                fi = topo.north.forced_intent(li, total)
                if fi:
                    for r in range(0, self.ir0):
                        cells[(r, c)] = fi

        if topo.south.enabled:
            total = self.lanes_north
            for c in range(self.center_c, self.ic1 + 1):
                li = self.ic1 - c
                fi = topo.south.forced_intent(li, total)
                if fi:
                    for r in range(self.ir1 + 1, self.size):
                        cells[(r, c)] = fi

        return cells

    # ── Punti di spawn ────────────────────────────────────────────────

    def spawn_entries(self) -> Iterator[Tuple[int, int, int, int, str, Optional[str]]]:
        """
        Genera i punti di ingresso ai bordi della griglia.
        Le auto entrano sempre dalla corsia piu' a destra (lane 0).
        Le corsie dedicate vengono yieldate comunque.
        """
        topo = self.topo

        if topo.west.enabled:
            total = self.lanes_east
            r0 = self.ir1
            fi0 = topo.west.forced_intent(0, total)
            yield (r0, 0, 0, 1, "east", fi0)
            for r in range(self.center_r, self.ir1):
                li = self.ir1 - r
                fi = topo.west.forced_intent(li, total)
                if fi is not None:
                    yield (r, 0, 0, 1, "east", fi)

        if topo.east.enabled:
            total = self.lanes_west
            r0 = self.ir0
            fi0 = topo.east.forced_intent(0, total)
            yield (r0, self.size - 1, 0, -1, "west", fi0)
            for r in range(self.ir0 + 1, self.center_r):
                li = r - self.ir0
                fi = topo.east.forced_intent(li, total)
                if fi is not None:
                    yield (r, self.size - 1, 0, -1, "west", fi)

        if topo.north.enabled:
            total = self.lanes_south
            c0 = self.ic0
            fi0 = topo.north.forced_intent(0, total)
            yield (0, c0, 1, 0, "south", fi0)
            for c in range(self.ic0 + 1, self.center_c):
                li = c - self.ic0
                fi = topo.north.forced_intent(li, total)
                if fi is not None:
                    yield (0, c, 1, 0, "south", fi)

        if topo.south.enabled:
            total = self.lanes_north
            c0 = self.ic1
            fi0 = topo.south.forced_intent(0, total)
            yield (self.size - 1, c0, -1, 0, "north", fi0)
            for c in range(self.center_c, self.ic1):
                li = self.ic1 - c
                fi = topo.south.forced_intent(li, total)
                if fi is not None:
                    yield (self.size - 1, c, -1, 0, "north", fi)

    # ── Validita' corsia per direzione ────────────────────────────────

    def valid_lane_cell(self, r: int, c: int, dr: int, dc: int) -> bool:
        if dc == 1:   return self.center_r <= r <= self.ir1
        if dc == -1:  return self.ir0 <= r < self.center_r
        if dr == 1:   return self.ic0 <= c < self.center_c
        if dr == -1:  return self.center_c <= c <= self.ic1
        return False

    # ── Slip Lanes ────────────────────────────────────────────────────

    def _compute_slip_entries(self) -> List[SlipEntry]:
        """
        Calcola i percorsi fisici delle slip lanes.

        Il trigger e' spostato _SLIP_PRETRIGGER (2) celle PRIMA della
        stop line, cosi' il bypass non dipende dallo stato del semaforo.

        Il path inizia con un "hook" di 3 celle che porta l'auto
        fuori dalla corsia principale (sotto/sopra il bordo della
        strada) PRIMA di raggiungere la stop line, poi prosegue con
        la gamba L classica e termina con la exit cell.

        Geometria hook per ogni angolo:
          SW (→↓): 1 sud + 2 est  → poi N sud + exit
          NW (↓←): 1 ovest + 2 sud → poi N ovest + exit
          NE (←↑): 1 nord + 2 ovest → poi N nord + exit
          SE (↑→): 1 est + 2 nord → poi N est + exit
        """
        topo = self.topo
        if not topo.slip_lanes_enabled:
            return []

        N   = topo.slip_len          # lunghezza gamba L (celle)
        P   = _SLIP_PRETRIGGER       # celle prima della stop line = 2
        ir0 = self.ir0; ir1 = self.ir1
        ic0 = self.ic0; ic1 = self.ic1
        entries = []

        def _f(cells):
            """Filtra celle fuori dalla griglia."""
            return tuple(c for c in cells if self.in_bounds(c[0], c[1]))

        # ── SW: → turning right to ↓ ──────────────────────────────
        # Stop line →  : col ic0-1
        # Trigger       : (ir1, ic0-1-P) = (ir1, ic0-3)
        # Hook (3 celle): 1 SUD + 2 EST  → bypassano la riga ir1 col ic0-1
        # L-leg (N celle): sud in col ic0-1, da ir1+2 a ir1+N
        # Exit          : (ir1+N, ic0) going ↓
        if topo.west.enabled and topo.north.enabled:
            tc, tr = ic0 - 1 - P, ir1   # trigger col, row
            if self.in_bounds(tr, tc):
                hook = [
                    (ir1 + 1, ic0 - 1 - P),   # 1 sud
                    (ir1 + 1, ic0 - P),        # est
                    (ir1 + 1, ic0 - 1),        # est (sotto la stop line row)
                ]
                l_leg = [(ir1 + k, ic0 - 1) for k in range(2, N + 1)]
                exit_cell = (ir1 + N, ic0)
                path = _f(hook + l_leg + [exit_cell])
                vis  = _f(hook + l_leg)
                if path:
                    entries.append(SlipEntry(
                        tr, tc, 0, 1,
                        ir1 + N, ic0, 1, 0,
                        "SW", path, vis
                    ))

        # ── NW: ↓ turning right to ← ──────────────────────────────
        # Stop line ↓  : riga ir0-1, col [ic0..cc-1]
        # Trigger       : (ir0-1-P, ic0) = (ir0-3, ic0)
        # Hook (3 celle): 1 OVEST + 2 SUD → bypassano la col ic0 riga ir0-1
        # L-leg (N celle): ovest in riga ir0-1, da ic0-2 a ic0-N
        # Exit          : (ir0, ic0-N) going ←
        if topo.north.enabled and topo.east.enabled:
            tr, tc = ir0 - 1 - P, ic0
            if self.in_bounds(tr, tc):
                hook = [
                    (ir0 - 1 - P, ic0 - 1),   # 1 ovest
                    (ir0 - P,     ic0 - 1),    # sud
                    (ir0 - 1,     ic0 - 1),    # sud (sinistra della stop col)
                ]
                l_leg = [(ir0 - 1, ic0 - k) for k in range(2, N + 1)]
                exit_cell = (ir0, ic0 - N)
                path = _f(hook + l_leg + [exit_cell])
                vis  = _f(hook + l_leg)
                if path:
                    entries.append(SlipEntry(
                        tr, tc, 1, 0,
                        ir0, ic0 - N, 0, -1,
                        "NW", path, vis
                    ))

        # ── NE: ← turning right to ↑ ──────────────────────────────
        # Stop line ← : col ic1+1, righe [ir0..cr-1]
        # Trigger      : (ir0, ic1+1+P) = (ir0, ic1+3)
        # Hook (3 celle): 1 NORD + 2 OVEST → bypassano la riga ir0 col ic1+1
        # L-leg (N celle): nord in col ic1+1, da ir0-2 a ir0-N
        # Exit          : (ir0-N, ic1) going ↑
        if topo.east.enabled and topo.south.enabled:
            tr, tc = ir0, ic1 + 1 + P
            if self.in_bounds(tr, tc):
                hook = [
                    (ir0 - 1, ic1 + 1 + P),   # 1 nord
                    (ir0 - 1, ic1 + P),        # ovest
                    (ir0 - 1, ic1 + 1),        # ovest (sopra la stop line row)
                ]
                l_leg = [(ir0 - k, ic1 + 1) for k in range(2, N + 1)]
                exit_cell = (ir0 - N, ic1)
                path = _f(hook + l_leg + [exit_cell])
                vis  = _f(hook + l_leg)
                if path:
                    entries.append(SlipEntry(
                        tr, tc, 0, -1,
                        ir0 - N, ic1, -1, 0,
                        "NE", path, vis
                    ))

        # ── SE: ↑ turning right to → ──────────────────────────────
        # Stop line ↑ : riga ir1+1, col [cc..ic1]
        # Trigger      : (ir1+1+P, ic1) = (ir1+3, ic1)
        # Hook (3 celle): 1 EST + 2 NORD → bypassano la riga ir1+1 col ic1
        # L-leg (N celle): est in riga ir1+1, da ic1+2 a ic1+N
        # Exit          : (ir1, ic1+N) going →
        if topo.south.enabled and topo.west.enabled:
            tr, tc = ir1 + 1 + P, ic1
            if self.in_bounds(tr, tc):
                hook = [
                    (ir1 + 1 + P, ic1 + 1),   # 1 est
                    (ir1 + P,     ic1 + 1),    # nord
                    (ir1 + 1,     ic1 + 1),    # nord (destra della stop col range)
                ]
                l_leg = [(ir1 + 1, ic1 + k) for k in range(2, N + 1)]
                exit_cell = (ir1, ic1 + N)
                path = _f(hook + l_leg + [exit_cell])
                vis  = _f(hook + l_leg)
                if path:
                    entries.append(SlipEntry(
                        tr, tc, -1, 0,
                        ir1, ic1 + N, 0, 1,
                        "SE", path, vis
                    ))

        return entries

    def check_slip_entry(
        self, r: int, c: int, dr: int, dc: int
    ) -> Optional[SlipEntry]:
        """Controlla se (r,c,dr,dc) e' un trigger di ingresso slip lane."""
        return self._slip_entry_map.get((r, c, dr, dc))

    @property
    def slip_visual_cells(self) -> Set[Tuple[int,int]]:
        return self._slip_visual_cells

    @property
    def slip_path_cells(self) -> Set[Tuple[int,int]]:
        return self._slip_path_cells

    @property
    def slip_entries(self) -> List[SlipEntry]:
        return self._slip_entries

    def is_slip_exclusive_lane(self, r: int, c: int, dr: int, dc: int) -> bool:
        """
        True se (r,c) e' nella zona di approccio esclusiva allo slip
        (le N celle prima del trigger, compreso il trigger stesso).

        Il trigger e' ora a _SLIP_PRETRIGGER celle prima della stop line:
          → : trigger a col ic0-3, zona [ic0-3-N … ic0-3] in riga ir1
          ↓ : trigger a riga ir0-3, zona [ir0-3-N … ir0-3] in col ic0
          ← : trigger a col ic1+3, zona [ic1+3 … ic1+3+N] in riga ir0
          ↑ : trigger a riga ir1+3, zona [ir1+3 … ir1+3+N] in col ic1
        """
        if not self.topo.slip_exclusive:
            return False
        li = self.lane_index(r, c, dr, dc)
        if li != 0:
            return False

        N = self.topo.slip_len
        P = _SLIP_PRETRIGGER
        trig_offset = 1 + P   # stop line offset (1) + pretrigger (2) = 3

        if dc == 1:   # →: trigger col = ic0 - trig_offset
            t = self.ic0 - trig_offset
            return r == self.ir1 and t - N <= c <= t
        if dc == -1:  # ←: trigger col = ic1 + trig_offset
            t = self.ic1 + trig_offset
            return r == self.ir0 and t <= c <= t + N
        if dr == 1:   # ↓: trigger row = ir0 - trig_offset
            t = self.ir0 - trig_offset
            return c == self.ic0 and t - N <= r <= t
        if dr == -1:  # ↑: trigger row = ir1 + trig_offset
            t = self.ir1 + trig_offset
            return c == self.ic1 and t <= r <= t + N
        return False

    def __repr__(self) -> str:
        return (
            f"GridGeometry(size={self.size}, "
            f"center=({self.center_r},{self.center_c}), "
            f"ir=[{self.ir0},{self.ir1}], ic=[{self.ic0},{self.ic1}], "
            f"lanes E{self.lanes_east}/W{self.lanes_west}/"
            f"S{self.lanes_south}/N{self.lanes_north})"
        )
