"""
world/topology.py — Topologie degli incroci.

Un'intersezione e' composta da fino a 4 SEGMENTI STRADALI fisici:
    west  — strada a ovest dell'incrocio  (porta traffico → e ←)
    east  — strada a est                  (porta traffico → e ←)
    north — strada a nord                 (porta traffico ↓ e ↑)
    south — strada a sud                  (porta traffico ↓ e ↑)

Disabilitare un segmento crea intersezioni a T, Y (offset), ecc.
Le corsie dedicate si inseriscono DENTRO il range corsie esistente.

Convenzioni senso di marcia:
    → (est)  : usa le righe del WEST segment  [center_r … ir1]
    ← (ovest): usa le righe dell'EAST segment [ir0 … center_r-1]
    ↓ (sud)  : usa le colonne del NORTH segment [center_c … ic1]
    ↑ (nord) : usa le colonne del SOUTH segment [ic0 … center_c-1]
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RoadSegment:
    """
    Configurazione di un singolo braccio stradale.

    Attributi:
        enabled          : se False il braccio non esiste (T-junction, ecc.)
        lanes_inbound    : corsie in ENTRATA verso l'incrocio (None = default)
        lanes_outbound   : corsie in USCITA (None = uguale a inbound)
        left_turn_lane   : corsia più a sinistra dedicata alla svolta sx
        right_turn_lane  : corsia più a destra dedicata alla svolta dx
        spawn_prob       : override probabilità spawn (None = usa cfg)
        label            : nome descrittivo
    """
    enabled:         bool            = True
    lanes_inbound:   Optional[int]   = None
    lanes_outbound:  Optional[int]   = None
    left_turn_lane:  bool            = False
    right_turn_lane: bool            = False
    spawn_prob:      Optional[float] = None
    label:           str             = ""

    def inbound(self, default: int) -> int:
        return self.lanes_inbound if self.lanes_inbound is not None else default

    def outbound(self, default: int) -> int:
        n = self.inbound(default)
        return self.lanes_outbound if self.lanes_outbound is not None else n

    def forced_intent(self, lane_idx: int, total_lanes: int) -> Optional[str]:
        """Intent forzato per corsie dedicate, None altrimenti."""
        if total_lanes < 2:
            return None
        if self.left_turn_lane and lane_idx == total_lanes - 1:
            return "left"
        if self.right_turn_lane and lane_idx == 0:
            return "right"
        return None

    def __repr__(self) -> str:
        if not self.enabled:
            return "RoadSegment(disabled)"
        parts = [f"lanes={self.lanes_inbound or 'default'}"]
        if self.left_turn_lane:   parts.append("left_lane")
        if self.right_turn_lane:  parts.append("right_lane")
        if self.spawn_prob is not None: parts.append(f"spawn={self.spawn_prob:.0%}")
        if self.label: parts.append(f'"{self.label}"')
        return f"RoadSegment({', '.join(parts)})"


@dataclass
class TopologyConfig:
    """
    Topologia completa dell'incrocio.

    I quattro segmenti (west/east/north/south) descrivono i bracci fisici.
    Disabilita un segmento per T-junction, strade a senso unico, ecc.

    row_yield_to:
        "right"    — precedenza a destra (regola italiana)
        "left"     — precedenza a sinistra (rotatoria)
        "oncoming" — solo chi gira a sinistra cede
    roundabout:
        True  — usa logica di rotatoria (percorso ad anello in IPR/render)
    roundabout_lanes:
        numero di corsie nell'anello della rotatoria
    """
    name:              str         = "plus"
    west:  RoadSegment = field(default_factory=RoadSegment)
    east:  RoadSegment = field(default_factory=RoadSegment)
    north: RoadSegment = field(default_factory=RoadSegment)
    south: RoadSegment = field(default_factory=RoadSegment)
    center_row_offset: int = 0
    center_col_offset: int = 0
    slip_lanes_enabled: bool = False
    slip_len:           int  = 5
    slip_exclusive:     bool = True
    row_yield_to:       str  = "right"
    roundabout:         bool = False
    roundabout_lanes:   int  = 1

    def arm(self, name: str) -> RoadSegment:
        return getattr(self, name)

    def enabled_arms(self) -> list:
        return [s for s in ("west", "east", "north", "south")
                if getattr(self, s).enabled]

    def num_enabled(self) -> int:
        return sum(1 for s in ("west", "east", "north", "south")
                   if getattr(self, s).enabled)

    def exit_segment(self, dr: int, dc: int, intent: str) -> str:
        """Nome del segmento di uscita per una data manovra."""
        if intent == "straight":
            if dc == 1:  return "east"
            if dc == -1: return "west"
            if dr == 1:  return "south"
            return "north"
        if intent == "right":
            if dc == 1:  return "south"
            if dc == -1: return "north"
            if dr == 1:  return "west"
            return "east"
        # left
        if dc == 1:  return "north"
        if dc == -1: return "south"
        if dr == 1:  return "east"
        return "west"

    def is_turn_possible(self, dr: int, dc: int, intent: str) -> bool:
        return self.arm(self.exit_segment(dr, dc, intent)).enabled

    def fallback_intent(self, dr: int, dc: int, intent: str) -> str:
        if self.is_turn_possible(dr, dc, intent):
            return intent
        for fallback in ("straight", "right", "left"):
            if fallback != intent and self.is_turn_possible(dr, dc, fallback):
                return fallback
        return "straight"

    def summary(self) -> str:
        arms_str = " | ".join(
            f"{n}:{self.arm(n)}" for n in ("west", "east", "north", "south")
        )
        return f"Topology[{self.name}]: {arms_str}"


# ─────────────────────────────────────────────────────────────────────
# Topologie preset
# ─────────────────────────────────────────────────────────────────────

def _seg(**kw) -> RoadSegment:
    return RoadSegment(**kw)


TOPOLOGIES: dict[str, TopologyConfig] = {
    "plus": TopologyConfig(name="plus"),

    "T_no_north": TopologyConfig(name="T_no_north", north=_seg(enabled=False)),
    "T_no_south": TopologyConfig(name="T_no_south", south=_seg(enabled=False)),
    "T_no_east":  TopologyConfig(name="T_no_east",  east=_seg(enabled=False)),
    "T_no_west":  TopologyConfig(name="T_no_west",  west=_seg(enabled=False)),

    "dedicated_left_all": TopologyConfig(
        name="dedicated_left_all",
        west=_seg(left_turn_lane=True), east=_seg(left_turn_lane=True),
        north=_seg(left_turn_lane=True), south=_seg(left_turn_lane=True),
    ),
    "dedicated_right_all": TopologyConfig(
        name="dedicated_right_all",
        west=_seg(right_turn_lane=True), east=_seg(right_turn_lane=True),
        north=_seg(right_turn_lane=True), south=_seg(right_turn_lane=True),
    ),
    "dedicated_both_all": TopologyConfig(
        name="dedicated_both_all",
        west=_seg(left_turn_lane=True, right_turn_lane=True),
        east=_seg(left_turn_lane=True, right_turn_lane=True),
        north=_seg(left_turn_lane=True, right_turn_lane=True),
        south=_seg(left_turn_lane=True, right_turn_lane=True),
    ),

    "asymmetric_H_main": TopologyConfig(
        name="asymmetric_H_main",
        west=_seg(lanes_inbound=4, label="main"),
        east=_seg(lanes_inbound=4, label="main"),
        north=_seg(lanes_inbound=2, label="secondary"),
        south=_seg(lanes_inbound=2, label="secondary"),
    ),
    "asymmetric_V_main": TopologyConfig(
        name="asymmetric_V_main",
        west=_seg(lanes_inbound=2, label="secondary"),
        east=_seg(lanes_inbound=2, label="secondary"),
        north=_seg(lanes_inbound=4, label="main"),
        south=_seg(lanes_inbound=4, label="main"),
    ),
    "main_with_dedicated": TopologyConfig(
        name="main_with_dedicated",
        west=_seg(lanes_inbound=4, left_turn_lane=True, right_turn_lane=True),
        east=_seg(lanes_inbound=4, left_turn_lane=True, right_turn_lane=True),
        north=_seg(lanes_inbound=2), south=_seg(lanes_inbound=2),
    ),
    "offset_left": TopologyConfig(name="offset_left", center_col_offset=-10),
    "T_no_north_dedicated": TopologyConfig(
        name="T_no_north_dedicated", north=_seg(enabled=False),
        west=_seg(left_turn_lane=True), east=_seg(right_turn_lane=True),
        south=_seg(lanes_inbound=2),
    ),
    "star_3arm": TopologyConfig(
        name="star_3arm", east=_seg(enabled=False),
        west=_seg(lanes_inbound=3, left_turn_lane=True),
        north=_seg(lanes_inbound=2), south=_seg(lanes_inbound=2),
    ),

    "slip_standard":  TopologyConfig(name="slip_standard",  slip_lanes_enabled=True, slip_len=5, slip_exclusive=True),
    "slip_shared":    TopologyConfig(name="slip_shared",     slip_lanes_enabled=True, slip_len=5, slip_exclusive=False),
    "slip_dedicated": TopologyConfig(
        name="slip_dedicated",
        west=_seg(left_turn_lane=True), east=_seg(left_turn_lane=True),
        north=_seg(left_turn_lane=True), south=_seg(left_turn_lane=True),
        slip_lanes_enabled=True, slip_len=6, slip_exclusive=True,
    ),
    "T_slip": TopologyConfig(name="T_slip", north=_seg(enabled=False),
                             slip_lanes_enabled=True, slip_len=5, slip_exclusive=True),

    "roundabout":       TopologyConfig(name="roundabout",       row_yield_to="left", roundabout=True),
    "yield_to_main":    TopologyConfig(
        name="yield_to_main",
        west=_seg(lanes_inbound=4, label="main"), east=_seg(lanes_inbound=4, label="main"),
        north=_seg(lanes_inbound=2, label="secondary"), south=_seg(lanes_inbound=2, label="secondary"),
        row_yield_to="left",
    ),
    "priority_right":      TopologyConfig(name="priority_right",      row_yield_to="right"),
    "slip_priority_right": TopologyConfig(
        name="slip_priority_right",
        slip_lanes_enabled=True, slip_len=5, slip_exclusive=True, row_yield_to="right",
    ),
}


def list_topologies() -> list:
    """Nomi delle topologie disponibili."""
    return list(TOPOLOGIES.keys())
