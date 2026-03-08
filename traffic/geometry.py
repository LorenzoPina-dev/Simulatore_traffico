"""
geometry.py — Geometria della griglia e funzioni spaziali.

GridGeometry calcola e memorizza tutti i bounds dell'incrocio
a partire da SimConfig + TopologyConfig.

Supporta:
    - Numero di corsie diverso per ogni braccio
    - Centro dell'incrocio con offset rispetto al centro della griglia
    - Bracci disabilitati (T-junction, ecc.)
    - Corsie dedicate (left_turn_lane / right_turn_lane)
    - Slip lanes: corsie fisiche a L attorno agli angoli dell'incrocio

Convenzione CODICE DELLA STRADA (guida a DESTRA):
    WEST segment  →  porta traffico → (east-going)  righe [center_r … ir1]   (a SUD = destra per chi va EST)
    EAST segment  →  porta traffico ← (west-going)  righe [ir0 … center_r-1](a NORD = destra per chi va OVEST)
    NORTH segment →  porta traffico ↓ (south-going) colonne [ic0 … center_c-1](a OVEST = destra per chi va SUD)
    SOUTH segment →  porta traffico ↑ (north-going) colonne [center_c … ic1] (a EST = destra per chi va NORD)

Bounds incrocio:
    ir0 = center_r - lanes_west
    ir1 = center_r + lanes_east - 1
    ic0 = center_c - lanes_south   (prima col ↓, lato OVEST)
    ic1 = center_c + lanes_north - 1

Slip lane paths (L-shape, percorso fisico visibile):
    SW (→ to ↓):  N celle a SUD lungo col ic0-1, poi exit in (ir1+N, ic0)
    NW (↓ to ←):  N celle a OVEST lungo riga ir0-1, poi exit in (ir0, ic0-N)
    NE (← to ↑):  N celle a NORD lungo col ic1+1, poi exit in (ir0-N, ic1)
    SE (↑ to →):  N celle a EST lungo riga ir1+1, poi exit in (ir1, ic1+N)
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Iterator, Optional, Tuple, Dict, List, Set, NamedTuple

if TYPE_CHECKING:
    from .config   import SimConfig
    from .topology import TopologyConfig


class SlipEntry(NamedTuple):
    """
    Descrive un singolo slip lane (bypass fisico a L attorno a un angolo).

    entry_r, entry_c       : cella trigger di ingresso (ultima cella normale prima dell'incrocio)
    entry_dr, entry_dc     : direzione in entrata
    exit_r,  exit_c        : prima cella dopo lo slip (su strada normale)
    exit_dr, exit_dc       : direzione di uscita (sulla nuova strada)
    corner                 : angolo ('SW'|'NW'|'NE'|'SE')
    path                   : sequenza ordinata (r,c) celle fisiche del percorso,
                             inclusa la exit cell come ultima
    visual_cells           : tuple (r,c) delle sole celle di bypass (senza exit cell)
                             da colorare come slip lane nel render
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
    path:         tuple   # ordinato: slip cells + exit cell
    visual_cells: tuple   # solo le slip cells (sottoinsieme di path)


class GridGeometry:
    """
    Geometria completa dell'incrocio, calcolata da SimConfig + TopologyConfig.
    """

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
        # Celle visive (solo la parte bypass, non la exit cell che è strada normale)
        self._slip_visual_cells: Set[Tuple[int,int]] = {
            cell for e in self._slip_entries for cell in e.visual_cells
        }
        # Tutte le celle del percorso (inclusa exit) per collision avoidance
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

        Regola CODICE DELLA STRADA: le auto entrano SEMPRE dalla corsia
        piu' a destra (lane 0), poi usano il cambio corsia per sorpassare.
        Eccezione: corsie dedicate (left_turn_lane / right_turn_lane) che
        vengono yieldate comunque per permettere lo spawn su di esse.
        """
        topo = self.topo

        # → (est): spawn su corsia 0 = riga ir1 (piu' a sud = destra per chi va est)
        if topo.west.enabled:
            total = self.lanes_east
            # Corsia 0 (rightmost)
            r0 = self.ir1
            fi0 = topo.west.forced_intent(0, total)
            yield (r0, 0, 0, 1, "east", fi0)
            # Corsie dedicate aggiuntive (se esistono)
            for r in range(self.center_r, self.ir1):
                li = self.ir1 - r
                fi = topo.west.forced_intent(li, total)
                if fi is not None:   # solo se e' una corsia dedicata
                    yield (r, 0, 0, 1, "east", fi)

        # ← (ovest): spawn su corsia 0 = riga ir0 (piu' a nord = destra per chi va ovest)
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

        # ↓ (sud): spawn su corsia 0 = col ic0 (piu' a ovest = destra per chi va sud)
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

        # ↑ (nord): spawn su corsia 0 = col ic1 (piu' a est = destra per chi va nord)
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
        Calcola i percorsi fisici delle slip lanes per ogni angolo abilitato.

        Ogni percorso è un L-shape che bypassa l'angolo dell'incrocio:
          SW (→→↓): N celle SUD lungo col ic0-1, poi entra in (ir1+N, ic0) going ↓
          NW (↓→←): N celle OVEST lungo riga ir0-1, poi entra in (ir0, ic0-N) going ←
          NE (←→↑): N celle NORD lungo col ic1+1, poi entra in (ir0-N, ic1) going ↑
          SE (↑→→): N celle EST lungo riga ir1+1, poi entra in (ir1, ic1+N) going →

        Il trigger di ingresso è all'ultima cella normale PRIMA dell'incrocio
        sulla corsia più esterna (lane 0) del segmento in avvicinamento.
        """
        topo = self.topo
        if not topo.slip_lanes_enabled:
            return []

        N   = topo.slip_len
        ir0 = self.ir0; ir1 = self.ir1
        ic0 = self.ic0; ic1 = self.ic1
        entries = []

        def _filter(cells):
            return tuple(c for c in cells if self.in_bounds(c[0], c[1]))

        # ── SW: → turning right to ↓ ─────────────────────────────────
        # Entry trigger: (ir1, ic0-1) going →
        # Path: N celle SUD in col ic0-1, poi cella di uscita (ir1+N, ic0)
        if topo.west.enabled and topo.north.enabled:
            er, ec    = ir1, ic0 - 1
            exit_r, exit_c = ir1 + N, ic0
            if self.in_bounds(er, ec) and self.in_bounds(exit_r, exit_c):
                slip_cells = [(ir1 + k, ic0 - 1) for k in range(1, N + 1)]
                path = _filter(slip_cells + [(exit_r, exit_c)])
                vis  = _filter(slip_cells)
                if path:
                    entries.append(SlipEntry(
                        er, ec, 0, 1,
                        exit_r, exit_c, 1, 0,
                        "SW", path, vis
                    ))

        # ── NW: ↓ turning right to ← ─────────────────────────────────
        # Entry trigger: (ir0-1, ic0) going ↓
        # Path: N celle OVEST in riga ir0-1, poi cella di uscita (ir0, ic0-N)
        if topo.north.enabled and topo.east.enabled:
            er, ec    = ir0 - 1, ic0
            exit_r, exit_c = ir0, ic0 - N
            if self.in_bounds(er, ec) and self.in_bounds(exit_r, exit_c):
                slip_cells = [(ir0 - 1, ic0 - k) for k in range(1, N + 1)]
                path = _filter(slip_cells + [(exit_r, exit_c)])
                vis  = _filter(slip_cells)
                if path:
                    entries.append(SlipEntry(
                        er, ec, 1, 0,
                        exit_r, exit_c, 0, -1,
                        "NW", path, vis
                    ))

        # ── NE: ← turning right to ↑ ─────────────────────────────────
        # Entry trigger: (ir0, ic1+1) going ←
        # Path: N celle NORD in col ic1+1, poi cella di uscita (ir0-N, ic1)
        if topo.east.enabled and topo.south.enabled:
            er, ec    = ir0, ic1 + 1
            exit_r, exit_c = ir0 - N, ic1
            if self.in_bounds(er, ec) and self.in_bounds(exit_r, exit_c):
                slip_cells = [(ir0 - k, ic1 + 1) for k in range(1, N + 1)]
                path = _filter(slip_cells + [(exit_r, exit_c)])
                vis  = _filter(slip_cells)
                if path:
                    entries.append(SlipEntry(
                        er, ec, 0, -1,
                        exit_r, exit_c, -1, 0,
                        "NE", path, vis
                    ))

        # ── SE: ↑ turning right to → ─────────────────────────────────
        # Entry trigger: (ir1+1, ic1) going ↑
        # Path: N celle EST in riga ir1+1, poi cella di uscita (ir1, ic1+N)
        if topo.south.enabled and topo.west.enabled:
            er, ec    = ir1 + 1, ic1
            exit_r, exit_c = ir1, ic1 + N
            if self.in_bounds(er, ec) and self.in_bounds(exit_r, exit_c):
                slip_cells = [(ir1 + 1, ic1 + k) for k in range(1, N + 1)]
                path = _filter(slip_cells + [(exit_r, exit_c)])
                vis  = _filter(slip_cells)
                if path:
                    entries.append(SlipEntry(
                        er, ec, -1, 0,
                        exit_r, exit_c, 0, 1,
                        "SE", path, vis
                    ))

        return entries

    def check_slip_entry(
        self, r: int, c: int, dr: int, dc: int
    ) -> Optional[SlipEntry]:
        """Controlla se (r,c,dr,dc) è un trigger di ingresso slip lane."""
        return self._slip_entry_map.get((r, c, dr, dc))

    @property
    def slip_visual_cells(self) -> Set[Tuple[int,int]]:
        """Celle di bypass da colorare come slip road (senza exit cell)."""
        return self._slip_visual_cells

    @property
    def slip_path_cells(self) -> Set[Tuple[int,int]]:
        """Tutte le celle dei percorsi slip (incluse exit cells)."""
        return self._slip_path_cells

    @property
    def slip_entries(self) -> List[SlipEntry]:
        return self._slip_entries

    def is_slip_exclusive_lane(self, r: int, c: int, dr: int, dc: int) -> bool:
        """
        True se (r,c) è nella corsia esclusiva di avvicinamento allo slip
        (le N celle prima dell'incrocio sulla corsia più esterna).
        Usato dallo spawn per forzare intent='right'.
        """
        if not self.topo.slip_exclusive:
            return False
        li = self.lane_index(r, c, dr, dc)
        if li != 0:
            return False
        N = self.topo.slip_len
        if dc == 1  and r == self.ir1 and self.ic0 - N <= c < self.ic0:
            return True
        if dr == 1  and c == self.ic0 and self.ir0 - N <= r < self.ir0:
            return True
        if dc == -1 and r == self.ir0 and self.ic1 < c <= self.ic1 + N:
            return True
        if dr == -1 and c == self.ic1 and self.ir1 < r <= self.ir1 + N:
            return True
        return False

    def __repr__(self) -> str:
        return (
            f"GridGeometry(size={self.size}, "
            f"center=({self.center_r},{self.center_c}), "
            f"ir=[{self.ir0},{self.ir1}], ic=[{self.ic0},{self.ic1}], "
            f"lanes E{self.lanes_east}/W{self.lanes_west}/"
            f"S{self.lanes_south}/N{self.lanes_north})"
        )
