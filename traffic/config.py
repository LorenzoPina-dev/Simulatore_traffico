"""
config.py — Parametri completi della simulazione.

Tutto cio' che controlla il comportamento della simulazione vive qui,
in strutture dati tipizzate e documentate. Per creare una configurazione
personalizzata basta istanziare SimConfig() e sovrascrivere i campi
desiderati, oppure partire da uno degli scenari predefiniti in scenarios.py.

Esempio rapido:
    from traffic import SimConfig
    cfg = SimConfig(spawn_prob=0.5, accident_prob=0.002, num_lanes=4)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional


# =====================================================================
# POLITICHE SEMAFORO
# =====================================================================

class LightPolicy(Enum):
    """Politica di gestione del ciclo semaforico."""

    FIXED       = "fixed"
    # Ciclo fisso classico: verde_H -> giallo -> verde_V -> giallo.
    # I tempi sono determinati da light_green_h, light_green_v, light_yellow.

    ADAPTIVE    = "adaptive"
    # Il semaforo prolunga il verde della direzione con piu' auto in coda.
    # Controlla ogni `adaptive_check_interval` step.
    # Durata minima garantita: light_min_green; massima: light_max_green.

    ALWAYS_GREEN_H = "always_green_h"
    # Asse orizzontale ha sempre il verde (asse verticale sempre rosso).
    # Utile per testare scorrimento su una sola direzione.

    ALWAYS_GREEN_V = "always_green_v"
    # Asse verticale ha sempre il verde.

    NO_LIGHT    = "no_light"
    # Nessun semaforo: tutti passano sempre (incrocio non regolato).


# =====================================================================
# OSTACOLO MANUALE (piazzato a mano nella configurazione)
# =====================================================================

@dataclass
class ManualObstacle:
    """
    Un ostacolo fisso piazzato manualmente sulla griglia.

    Attributi:
        row      : riga della cella (coordinata griglia)
        col      : colonna della cella
        duration : durata in step (-1 = permanente per tutta la simulazione)
        label    : etichetta descrittiva (es. 'cantiere', 'incidente')
    """
    row:      int
    col:      int
    duration: int   = -1        # -1 = permanente
    label:    str   = "ostacolo"


# =====================================================================
# PROFILO PERSONALITA' GUIDATORE
# =====================================================================

@dataclass
class PersonalityProfile:
    """
    Parametri comportamentali di un profilo di guidatore.

    Attributi:
        name         : nome del profilo (es. 'CAUTIOUS')
        max_speed    : velocita' massima personale (celle/step)
        dawdle_prob  : probabilita' di rallentare casualmente (distrazione)
        react_time   : step di ritardo alla ripartenza dopo uno stop
        run_red_prob : probabilita' di passare col rosso per step
        ignore_lane  : probabilita' di ignorare la regola di corsia
        spawn_weight : peso relativo nello spawn (non normalizzato)
    """
    name:           str
    max_speed:      int
    dawdle_prob:    float
    react_time:     int
    run_red_prob:   float
    ignore_lane:    float
    ignore_row_prob: float   # prob. di ignorare la precedenza (right-of-way)
    spawn_weight:   float


# Profili predefiniti — modificabili o sostituibili nella SimConfig
DEFAULT_PROFILES: List[PersonalityProfile] = [
    PersonalityProfile(
        name="CAUTIOUS",   max_speed=2, dawdle_prob=0.28,
        react_time=3, run_red_prob=0.02, ignore_lane=0.03,
        ignore_row_prob=0.02,   # quasi sempre cede la precedenza
        spawn_weight=10,
    ),
    PersonalityProfile(
        name="NORMAL",     max_speed=3, dawdle_prob=0.12,
        react_time=1, run_red_prob=0.05, ignore_lane=0.08,
        ignore_row_prob=0.10,   # raramente ignora la precedenza
        spawn_weight=55,
    ),
    PersonalityProfile(
        name="AGGRESSIVE", max_speed=4, dawdle_prob=0.04,
        react_time=0, run_red_prob=0.28, ignore_lane=0.40,
        ignore_row_prob=0.45,   # spesso taglia la strada
        spawn_weight=25,
    ),
    PersonalityProfile(
        name="RUSHER",     max_speed=5, dawdle_prob=0.02,
        react_time=0, run_red_prob=0.58, ignore_lane=0.68,
        ignore_row_prob=0.72,   # quasi mai cede la precedenza
        spawn_weight=10,
    ),
]


# =====================================================================
# CONFIGURAZIONE PRINCIPALE
# =====================================================================

@dataclass
class SimConfig:
    """
    Configurazione completa della simulazione.
    Ogni parametro ha un valore di default ragionevole.
    Tutti i parametri sono sovrascrivibili singolarmente.

    --- GRIGLIA E GEOMETRIA ---
    grid_size   : lato della griglia quadrata in celle
    num_lanes   : corsie per senso di marcia (totale per asse = num_lanes * 2)
    max_speed   : velocita' massima globale in celle/step

    --- SIMULAZIONE ---
    steps       : numero totale di step (frame dell'animazione)
    interval_ms : millisecondi tra frame (basso = animazione veloce)
    output_file : nome del file GIF di output
    fps         : frame per secondo nella GIF
    dpi         : risoluzione della GIF

    --- SPAWN TRAFFICO ---
    spawn_prob        : probabilita' di generare un'auto per corsia per step
    spawn_prob_east   : override spawn per direzione EST  (None = usa spawn_prob)
    spawn_prob_west   : override spawn per direzione OVEST
    spawn_prob_south  : override spawn per direzione SUD
    spawn_prob_north  : override spawn per direzione NORD
    density_cap       : densita' massima (0-1) oltre la quale lo spawn si ferma

    --- SEMAFORO ---
    light_policy          : politica del ciclo (LightPolicy enum)
    light_green_h         : step di verde per asse orizzontale
    light_green_v         : step di verde per asse verticale
    light_yellow          : step di fase gialla
    adaptive_check_interval : ogni quanti step il semaforo adattivo controlla le code
    light_min_green       : durata minima del verde in modalita' ADAPTIVE
    light_max_green       : durata massima del verde in modalita' ADAPTIVE

    --- INCIDENTI ---
    accident_prob     : probabilita' per auto per step di causare un incidente
    accident_dur_min  : durata minima di un incidente (step)
    accident_dur_max  : durata massima di un incidente (step)

    --- OSTACOLI MANUALI ---
    manual_obstacles  : lista di ManualObstacle piazzati all'inizio

    --- PERSONALITA' GUIDATORI ---
    personalities     : lista di PersonalityProfile (sovrascrive i default)

    --- COMPORTAMENTO INCROCIO ---
    inter_max_speed   : velocita' massima dentro la zona incrocio
    frustration_max   : valore massimo di frustrazione accumulabile
    frustration_dawdle_factor : quanto ogni punto di frustrazione aumenta il dawdle
    """

    # ── Griglia ──────────────────────────────────────────────────────
    grid_size:  int   = 90
    num_lanes:  int   = 3
    max_speed:  int   = 4

    # ── Simulazione ──────────────────────────────────────────────────
    steps:       int   = 600
    interval_ms: int   = 80
    output_file: str   = "traffic_simulation_intersection.gif"
    fps:         int   = 12
    dpi:         int   = 90

    # ── Spawn ─────────────────────────────────────────────────────────
    spawn_prob:       float         = 0.32
    spawn_prob_east:  float | None  = None
    spawn_prob_west:  float | None  = None
    spawn_prob_south: float | None  = None
    spawn_prob_north: float | None  = None
    density_cap:      float         = 0.75

    # ── Semaforo ──────────────────────────────────────────────────────
    light_policy:             LightPolicy = LightPolicy.FIXED
    light_green_h:            int         = 45
    light_green_v:            int         = 45
    light_yellow:             int         = 6
    adaptive_check_interval:  int         = 10
    light_min_green:          int         = 15
    light_max_green:          int         = 90

    # ── Incidenti ─────────────────────────────────────────────────────
    accident_prob:    float = 0.00045
    accident_dur_min: int   = 12
    accident_dur_max: int   = 55

    # ── Ostacoli manuali ──────────────────────────────────────────────
    manual_obstacles: List[ManualObstacle] = field(default_factory=list)

    # ── Personalita' ──────────────────────────────────────────────────
    personalities: List[PersonalityProfile] = field(
        default_factory=lambda: list(DEFAULT_PROFILES)
    )

    # ── Topologia incrocio ───────────────────────────────────────────
    # topology : TopologyConfig che descrive i bracci e le corsie dedicate.
    #            None = topologia standard a + (equivale a TopologyConfig()).
    topology: object = field(default=None)  # TopologyConfig | None

    def __post_init__(self):
        """Inizializza topology al valore di default se None."""
        if self.topology is None:
            from .topology import TopologyConfig
            self.topology = TopologyConfig()

    # ── Comportamento incrocio ────────────────────────────────────────
    inter_max_speed:           int   = 2
    frustration_max:           int   = 20
    frustration_dawdle_factor: float = 0.02

    # ── Precedenza (right-of-way) ─────────────────────────────────────
    # row_enabled            : attiva/disattiva l'intero sistema di precedenza
    # row_lookahead          : celle prima dell'incrocio in cui il check si attiva
    # row_oncoming_check     : celle (dal lato opposto) da scansionare per minacce
    # row_frustration_factor : incremento P(ignora) per punto di frustrazione
    # row_yield_gap          : gap minimo oncoming per considerare libero il passo
    row_enabled:            bool  = True
    row_lookahead:          int   = 8
    row_oncoming_check:     int   = 12
    row_frustration_factor: float = 0.03
    row_yield_gap:          int   = 3

    # ── Helper: probabilita' spawn per direzione ──────────────────────
    def spawn_for(self, direction: str) -> float:
        """
        Ritorna la probabilita' di spawn per una direzione di marcia.

        Priorita':
            1. spawn_prob del segmento di provenienza (TopologyConfig)
            2. override direzionale di SimConfig (spawn_prob_east, ecc.)
            3. spawn_prob globale

        Args:
            direction: 'east'|'west'|'south'|'north' (direzione di marcia)

        Mapping direzione → segmento fisico:
            'east'  (cars going →) proviene da WEST segment
            'west'  (cars going ←) proviene da EAST segment
            'south' (cars going ↓) proviene da NORTH segment
            'north' (cars going ↑) proviene da SOUTH segment
        """
        # 1. Override da topologia (segmento fisico di provenienza)
        seg_name = {"east": "west", "west": "east",
                    "south": "north", "north": "south"}.get(direction)
        if seg_name and self.topology is not None:
            seg = getattr(self.topology, seg_name, None)
            if seg and seg.spawn_prob is not None:
                return seg.spawn_prob

        # 2. Override direzionale SimConfig
        override = {
            "east":  self.spawn_prob_east,
            "west":  self.spawn_prob_west,
            "south": self.spawn_prob_south,
            "north": self.spawn_prob_north,
        }.get(direction)
        return override if override is not None else self.spawn_prob

    def summary(self) -> str:
        """Stringa riassuntiva dei parametri principali."""
        rule = getattr(self.topology, "row_yield_to", "right") if self.topology else "right"
        row_str = (
            f"ON  rule={rule}  lookahead={self.row_lookahead}  "
            f"oncoming={self.row_oncoming_check}  "
            f"frus_factor={self.row_frustration_factor}"
            if self.row_enabled else "OFF"
        )
        lines = [
            f"  Griglia    : {self.grid_size}x{self.grid_size}  "
            f"Corsie: {self.num_lanes}/senso  MaxSpd: {self.max_speed}",
            f"  Spawn      : {self.spawn_prob:.0%}  "
            f"DensityCap: {self.density_cap:.0%}",
            f"  Semaforo   : {self.light_policy.value}  "
            f"Verde H:{self.light_green_h} V:{self.light_green_v} "
            f"Giallo:{self.light_yellow}",
            f"  Incidenti  : p={self.accident_prob:.5f}  "
            f"dur=[{self.accident_dur_min},{self.accident_dur_max}]",
            f"  Ostacoli   : {len(self.manual_obstacles)} manuali",
            f"  Precedenza : {row_str}",
            f"  Step       : {self.steps}  FPS:{self.fps}  DPI:{self.dpi}",
        ]
        return "\n".join(lines)
