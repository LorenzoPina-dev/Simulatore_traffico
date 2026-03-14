"""
core/config.py — Parametri completi della simulazione.

SimConfig è un dataclass immutabile (dal punto di vista logico) che raccoglie
tutti i parametri configurabili. Non contiene logica di simulazione.

Dipendenze: solo da core/types.py — zero dipendenze circolari.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

from .types import VehicleType, LightPolicy


# ─────────────────────────────────────────────────────────────────────
# Strutture dati di supporto
# ─────────────────────────────────────────────────────────────────────

@dataclass
class PersonalityProfile:
    """
    Profilo comportamentale di un guidatore.

    Attributi:
        name             : nome descrittivo (es. 'CAUTIOUS')
        max_speed        : velocità massima [celle/step]
        dawdle_prob      : probabilità perturbazione stocastica IDM
        react_time       : step di ritardo alla ripartenza
        run_red_prob     : probabilità di passare col rosso per step
        ignore_lane      : probabilità di ignorare la corsia dedicata
        ignore_row_prob  : probabilità di ignorare la precedenza
        spawn_weight     : peso relativo nello spawn
    """
    name:            str
    max_speed:       int
    dawdle_prob:     float
    react_time:      int
    run_red_prob:    float
    ignore_lane:     float
    ignore_row_prob: float
    spawn_weight:    float


DEFAULT_PROFILES: List[PersonalityProfile] = [
    PersonalityProfile("CAUTIOUS",   max_speed=2, dawdle_prob=0.28,
                       react_time=3, run_red_prob=0.02, ignore_lane=0.03,
                       ignore_row_prob=0.02, spawn_weight=10),
    PersonalityProfile("NORMAL",     max_speed=3, dawdle_prob=0.12,
                       react_time=1, run_red_prob=0.05, ignore_lane=0.08,
                       ignore_row_prob=0.10, spawn_weight=55),
    PersonalityProfile("AGGRESSIVE", max_speed=4, dawdle_prob=0.04,
                       react_time=0, run_red_prob=0.28, ignore_lane=0.40,
                       ignore_row_prob=0.45, spawn_weight=25),
    PersonalityProfile("RUSHER",     max_speed=5, dawdle_prob=0.02,
                       react_time=0, run_red_prob=0.58, ignore_lane=0.68,
                       ignore_row_prob=0.72, spawn_weight=10),
]


@dataclass
class VehicleTypeWeights:
    """Pesi relativi per lo spawn di ogni tipo di veicolo (non devono sommare a 1)."""
    motorcycle: float = 8.0
    car:        float = 72.0
    van:        float = 13.0
    bus:        float = 5.0
    emergency:  float = 2.0


@dataclass
class BusStop:
    """
    Fermata autobus sulla griglia.

    Il bus si ferma su (row, col) per dwell_time step, poi riparte.
    """
    row:        int
    col:        int
    dwell_time: int = 20
    label:      str = "fermata"


@dataclass
class ManualObstacle:
    """Blocco fisso posizionato manualmente (cantiere, incidente prefissato)."""
    row:      int
    col:      int
    duration: int = -1    # -1 = permanente
    label:    str = "ostacolo"


# ─────────────────────────────────────────────────────────────────────
# Configurazione principale
# ─────────────────────────────────────────────────────────────────────

@dataclass
class SimConfig:
    """
    Configurazione completa della simulazione.

    Sezioni:
        GRIGLIA     — grid_size, num_lanes, max_speed
        SIMULAZIONE — steps, interval_ms, output_file, fps, dpi
        SPAWN       — spawn_prob, spawn_prob_*, density_cap
        SEMAFORO    — light_policy, light_green_h/v, light_yellow, adaptive_*
        INCIDENTI   — accident_prob, accident_dur_*
        IDM         — use_idm, idm_delta
        MOBIL       — use_mobil, mobil_politeness/threshold/safe_decel/right_bias
        VEICOLI     — vehicle_weights
        BUS         — bus_stops
        PLATOONING  — platooning_enabled, platoon_*
        EMERGENZA   — emergency_preempt_dist, emergency_pull_over_dist
        PERSONALITÀ — personalities
        TOPOLOGIA   — topology (TopologyConfig, lazy import)
        PRECEDENZA  — row_enabled, row_lookahead, row_*
        INCROCIO    — inter_max_speed, frustration_*
    """

    # ── Griglia ──────────────────────────────────────────────────────
    grid_size:  int = 90
    num_lanes:  int = 3
    max_speed:  int = 4

    # ── Simulazione ──────────────────────────────────────────────────
    steps:       int = 600
    interval_ms: int = 120
    output_file: str = "traffic_simulation_intersection.gif"
    fps:         int = 12
    dpi:         int = 90

    # ── Spawn ─────────────────────────────────────────────────────────
    spawn_prob:       float         = 0.32
    spawn_prob_east:  Optional[float] = None
    spawn_prob_west:  Optional[float] = None
    spawn_prob_south: Optional[float] = None
    spawn_prob_north: Optional[float] = None
    density_cap:      float         = 0.75

    # ── Semaforo ──────────────────────────────────────────────────────
    light_policy:            LightPolicy = LightPolicy.FIXED
    light_green_h:           int         = 60
    light_green_v:           int         = 60
    light_yellow:            int         = 9
    adaptive_check_interval: int         = 15
    light_min_green:         int         = 25
    light_max_green:         int         = 150

    # ── Incidenti ─────────────────────────────────────────────────────
    accident_prob:    float = 0.00045
    accident_dur_min: int   = 12
    accident_dur_max: int   = 55

    # ── Ostacoli manuali ──────────────────────────────────────────────
    manual_obstacles: List[ManualObstacle] = field(default_factory=list)

    # ── IDM ───────────────────────────────────────────────────────────
    use_idm:   bool = True
    idm_delta: int  = 4

    # ── MOBIL ─────────────────────────────────────────────────────────
    use_mobil:        bool  = True
    mobil_politeness: float = 0.5
    mobil_threshold:  float = 0.10
    mobil_safe_decel: float = 3.0
    mobil_right_bias: float = 0.05

    # ── Veicoli eterogenei ────────────────────────────────────────────
    vehicle_weights: VehicleTypeWeights = field(default_factory=VehicleTypeWeights)

    # ── Fermate bus ───────────────────────────────────────────────────
    bus_stops: List[BusStop] = field(default_factory=list)

    # ── Platooning ────────────────────────────────────────────────────
    platooning_enabled: bool  = False
    platoon_min_speed:  float = 2.0
    platoon_gap:        int   = 1
    platoon_max_size:   int   = 5
    platoon_form_prob:  float = 0.02

    # ── Emergenza ─────────────────────────────────────────────────────
    emergency_preempt_dist:   int = 18
    emergency_pull_over_dist: int = 12

    # ── Personalità guidatori ─────────────────────────────────────────
    personalities: List[PersonalityProfile] = field(
        default_factory=lambda: list(DEFAULT_PROFILES)
    )

    # ── Topologia (lazy import per evitare import circolari) ──────────
    topology: object = field(default=None)

    def __post_init__(self):
        if self.topology is None:
            from ..world.topology import TopologyConfig
            self.topology = TopologyConfig()

    # ── Comportamento incrocio ────────────────────────────────────────
    inter_max_speed:           int   = 2
    frustration_max:           int   = 20
    frustration_dawdle_factor: float = 0.02

    # ── Precedenza ────────────────────────────────────────────────────
    row_enabled:            bool  = True
    row_lookahead:          int   = 8
    row_oncoming_check:     int   = 12
    row_frustration_factor: float = 0.03
    row_yield_gap:          int   = 3
    row_distance_weight:    float = 0.3
    row_gap_weight:         float = 0.5

    # ── Helper ────────────────────────────────────────────────────────

    def spawn_for(self, direction: str) -> float:
        """Probabilità di spawn per una direzione, con override per braccio."""
        seg_name = {"east": "west", "west": "east",
                    "south": "north", "north": "south"}.get(direction)
        if seg_name and self.topology is not None:
            seg = getattr(self.topology, seg_name, None)
            if seg and getattr(seg, "spawn_prob", None) is not None:
                return seg.spawn_prob
        override = {
            "east":  self.spawn_prob_east,
            "west":  self.spawn_prob_west,
            "south": self.spawn_prob_south,
            "north": self.spawn_prob_north,
        }.get(direction)
        return override if override is not None else self.spawn_prob

    def summary(self) -> str:
        rule = getattr(self.topology, "row_yield_to", "right") if self.topology else "right"
        idm  = f"IDM={'ON' if self.use_idm else 'OFF'} MOBIL={'ON' if self.use_mobil else 'OFF'}"
        vw   = self.vehicle_weights
        return "\n".join([
            f"  Griglia    : {self.grid_size}x{self.grid_size}  Corsie:{self.num_lanes}  MaxSpd:{self.max_speed}",
            f"  Fisica     : {idm}  platoon={'ON' if self.platooning_enabled else 'OFF'}",
            f"  Spawn      : {self.spawn_prob:.0%}  DensityCap:{self.density_cap:.0%}",
            f"  Veicoli    : moto={vw.motorcycle} car={vw.car} van={vw.van} bus={vw.bus} em={vw.emergency}",
            f"  Semaforo   : {self.light_policy.value}  H:{self.light_green_h} V:{self.light_green_v}",
            f"  Incidenti  : p={self.accident_prob:.5f}  dur=[{self.accident_dur_min},{self.accident_dur_max}]",
            f"  Precedenza : {'ON rule=' + rule if self.row_enabled else 'OFF'}",
            f"  Step       : {self.steps}  FPS:{self.fps}  DPI:{self.dpi}",
        ])
