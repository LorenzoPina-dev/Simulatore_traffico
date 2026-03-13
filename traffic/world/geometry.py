"""
world/geometry.py — Geometria della griglia e funzioni spaziali.

GridGeometry calcola e memorizza tutti i bounds dell'incrocio
a partire da SimConfig + TopologyConfig.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Iterator, Optional, Tuple, Dict, List, Set, NamedTuple

if TYPE_CHECKING:
    from ..core.config   import SimConfig
    from .topology       import TopologyConfig

_SLIP_PRETRIGGER = 2


class SlipEntry(NamedTuple):
    """Descrive un singolo slip lane (bypass fisico a L attorno a un angolo)."""
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

        self._slip_entries: List[SlipEntry]          = self._compute_slip_entries()
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
        return (self.ir0 <= r <= self.ir1) or (self.ic0 <= c <= self.ic1)

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.size and 0 <= c < self.size

    # ── Indice corsia ─────────────────────────────────────────────────

    def lane_index(self, r: int, c: int, dr: int, dc: int) -> int:
        if dc == 1:  return self.ir1 - r
        if dc == -1: return r - self.ir0
        if dr == 1:  return c - self.ic0
        if dr == -1: return self.ic1 - c
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
        topo = self.topo
        if topo.west.enabled:
            total = self.lanes_east
            for r in range(self.center_r, self.ir1 + 1):
                fi = topo.west.forced_intent(self.ir1 - r, total)
                if fi:
                    for c in range(0, self.ic0): cells[(r, c)] = fi
        if topo.east.enabled:
            total = self.lanes_west
            for r in range(self.ir0, self.center_r):
                fi = topo.east.forced_intent(r - self.ir0, total)
                if fi:
                    for c in range(self.ic1 + 1, self.size): cells[(r, c)] = fi
        if topo.north.enabled:
            total = self.lanes_south
            for c in range(self.ic0, self.center_c):
                fi = topo.north.forced_intent(c - self.ic0, total)
                if fi:
                    for r in range(0, self.ir0): cells[(r, c)] = fi
        if topo.south.enabled:
            total = self.lanes_north
            for c in range(self.center_c, self.ic1 + 1):
                fi = topo.south.forced_intent(self.ic1 - c, total)
                if fi:
                    for r in range(self.ir1 + 1, self.size): cells[(r, c)] = fi
        return cells

    # ── Punti di spawn ────────────────────────────────────────────────

    def spawn_entries(self) -> Iterator[Tuple[int, int, int, int, str, Optional[str]]]:
        topo = self.topo
        if topo.west.enabled:
            total = self.lanes_east
            yield (self.ir1, 0, 0, 1, "east", topo.west.forced_intent(0, total))
            for r in range(self.center_r, self.ir1):
                li = self.ir1 - r
                fi = topo.west.forced_intent(li, total)
                if fi is not None: yield (r, 0, 0, 1, "east", fi)
        if topo.east.enabled:
            total = self.lanes_west
            yield (self.ir0, self.size - 1, 0, -1, "west", topo.east.forced_intent(0, total))
            for r in range(self.ir0 + 1, self.center_r):
                li = r - self.ir0
                fi = topo.east.forced_intent(li, total)
                if fi is not None: yield (r, self.size - 1, 0, -1, "west", fi)
        if topo.north.enabled:
            total = self.lanes_south
            yield (0, self.ic0, 1, 0, "south", topo.north.forced_intent(0, total))
            for c in range(self.ic0 + 1, self.center_c):
                li = c - self.ic0
                fi = topo.north.forced_intent(li, total)
                if fi is not None: yield (0, c, 1, 0, "south", fi)
        if topo.south.enabled:
            total = self.lanes_north
            yield (self.size - 1, self.ic1, -1, 0, "north", topo.south.forced_intent(0, total))
            for c in range(self.center_c, self.ic1):
                li = self.ic1 - c
                fi = topo.south.forced_intent(li, total)
                if fi is not None: yield (self.size - 1, c, -1, 0, "north", fi)

    # ── Validità corsia ───────────────────────────────────────────────

    def valid_lane_cell(self, r: int, c: int, dr: int, dc: int) -> bool:
        if dc == 1:  return self.center_r <= r <= self.ir1
        if dc == -1: return self.ir0 <= r < self.center_r
        if dr == 1:  return self.ic0 <= c < self.center_c
        if dr == -1: return self.center_c <= c <= self.ic1
        return False

    # ── Slip Lanes ────────────────────────────────────────────────────

    def _compute_slip_entries(self) -> List[SlipEntry]:
        topo = self.topo
        if not topo.slip_lanes_enabled:
            return []
        N   = topo.slip_len
        P   = _SLIP_PRETRIGGER
        ir0 = self.ir0; ir1 = self.ir1
        ic0 = self.ic0; ic1 = self.ic1
        entries = []

        def _f(cells):
            return tuple(c for c in cells if self.in_bounds(c[0], c[1]))

        if topo.west.enabled and topo.north.enabled:
            tc, tr = ic0 - 1 - P, ir1
            if self.in_bounds(tr, tc):
                hook  = [(ir1+1, ic0-1-P), (ir1+1, ic0-P), (ir1+1, ic0-1)]
                l_leg = [(ir1+k, ic0-1) for k in range(2, N+1)]
                path  = _f(hook + l_leg + [(ir1+N, ic0)])
                vis   = _f(hook + l_leg)
                if path:
                    entries.append(SlipEntry(tr, tc, 0, 1, ir1+N, ic0, 1, 0, "SW", path, vis))

        if topo.north.enabled and topo.east.enabled:
            tr, tc = ir0-1-P, ic0
            if self.in_bounds(tr, tc):
                hook  = [(ir0-1-P, ic0-1), (ir0-P, ic0-1), (ir0-1, ic0-1)]
                l_leg = [(ir0-1, ic0-k) for k in range(2, N+1)]
                path  = _f(hook + l_leg + [(ir0, ic0-N)])
                vis   = _f(hook + l_leg)
                if path:
                    entries.append(SlipEntry(tr, tc, 1, 0, ir0, ic0-N, 0, -1, "NW", path, vis))

        if topo.east.enabled and topo.south.enabled:
            tr, tc = ir0, ic1+1+P
            if self.in_bounds(tr, tc):
                hook  = [(ir0-1, ic1+1+P), (ir0-1, ic1+P), (ir0-1, ic1+1)]
                l_leg = [(ir0-k, ic1+1) for k in range(2, N+1)]
                path  = _f(hook + l_leg + [(ir0-N, ic1)])
                vis   = _f(hook + l_leg)
                if path:
                    entries.append(SlipEntry(tr, tc, 0, -1, ir0-N, ic1, -1, 0, "NE", path, vis))

        if topo.south.enabled and topo.west.enabled:
            tr, tc = ir1+1+P, ic1
            if self.in_bounds(tr, tc):
                hook  = [(ir1+1+P, ic1+1), (ir1+P, ic1+1), (ir1+1, ic1+1)]
                l_leg = [(ir1+1, ic1+k) for k in range(2, N+1)]
                path  = _f(hook + l_leg + [(ir1, ic1+N)])
                vis   = _f(hook + l_leg)
                if path:
                    entries.append(SlipEntry(tr, tc, -1, 0, ir1, ic1+N, 0, 1, "SE", path, vis))

        return entries

    def check_slip_entry(self, r, c, dr, dc) -> Optional[SlipEntry]:
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

    def is_slip_exclusive_lane(self, r, c, dr, dc) -> bool:
        if not self.topo.slip_exclusive:
            return False
        if self.lane_index(r, c, dr, dc) != 0:
            return False
        N = self.topo.slip_len
        P = _SLIP_PRETRIGGER
        trig_offset = 1 + P
        if dc == 1:
            t = self.ic0 - trig_offset
            return r == self.ir1 and t - N <= c <= t
        if dc == -1:
            t = self.ic1 + trig_offset
            return r == self.ir0 and t <= c <= t + N
        if dr == 1:
            t = self.ir0 - trig_offset
            return c == self.ic0 and t - N <= r <= t
        if dr == -1:
            t = self.ir1 + trig_offset
            return c == self.ic1 and t <= r <= t + N
        return False

    def __repr__(self) -> str:
        return (
            f"GridGeometry(size={self.size}, "
            f"center=({self.center_r},{self.center_c}), "
            f"ir=[{self.ir0},{self.ir1}], ic=[{self.ic0},{self.ic1}])"
        )
