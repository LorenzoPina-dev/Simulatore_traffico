"""
entities.py — Entita' della simulazione: Personality, Car, Obstacle.

Queste classi rappresentano gli oggetti che popolano la griglia.
Non contengono logica di simulazione (quella vive in Sim),
ma solo lo stato e i parametri individuali.
"""

from __future__ import annotations
import random
from enum import IntEnum
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .config   import SimConfig, PersonalityProfile
    from .geometry import GridGeometry


# =====================================================================
# ENUM PERSONALITA'
# =====================================================================

class Personality(IntEnum):
    """
    Indice nella lista cfg.personalities.
    I valori corrispondono alle posizioni in SimConfig.personalities.
    Se aggiungi profili custom, aggiungi valori qui di conseguenza
    oppure usa direttamente gli indici interi.
    """
    CAUTIOUS   = 0
    NORMAL     = 1
    AGGRESSIVE = 2
    RUSHER     = 3


# =====================================================================
# AUTO
# =====================================================================

class Car:
    """
    Rappresenta un singolo veicolo sulla griglia.

    Stato di movimento:
        r, c    : posizione corrente (riga, colonna)
        dr, dc  : vettore direzione unitario
        spd     : velocita' corrente (celle/step)

    Stato comportamentale:
        delay   : step di ritardo ancora da aspettare (reaction time)
        frus    : frustrazione accumulata [0, frustration_max]
        t_stop  : step consecutivi a velocita' zero
        dist    : distanza totale percorsa (statistica)

    Attributi fissi (da PersonalityProfile):
        ms      : velocita' massima personale
        dw      : probabilita' dawdle base
        rt      : reaction time in step
        rr      : probabilita' passare col rosso per step
        il      : probabilita' ignorare regola di corsia
        ir      : probabilita' base di ignorare la precedenza (right-of-way)

    Stato incrocio:
        li       : indice corsia corrente
        intent   : 'straight' | 'right' | 'left'
        in_inter : True se attualmente nella zona a +
        turned   : True se la svolta e' gia' stata eseguita

    Cache:
        _rr_val, _rr_step : memoizzazione decisione passaggio col rosso
    """

    _next_id: int = 0

    def __init__(
        self,
        r: int, c: int,
        dr: int, dc: int,
        profile_index: int,
        cfg: "SimConfig",
        geo: "GridGeometry",
    ):
        Car._next_id += 1
        self.id = Car._next_id

        self.r  = r
        self.c  = c
        self.dr = dr
        self.dc = dc

        # Parametri dal profilo personalita'
        prof: "PersonalityProfile" = cfg.personalities[profile_index]
        self.pers = profile_index
        self.ms   = prof.max_speed
        self.dw   = prof.dawdle_prob
        self.rt   = prof.react_time
        self.rr   = prof.run_red_prob
        self.il   = prof.ignore_lane
        self.ir   = prof.ignore_row_prob

        # Stato dinamico
        self.spd    = 1
        self.delay  = 0
        self.frus   = 0
        self.t_stop = 0
        self.dist   = 0

        # Stato incrocio
        self.li       = geo.lane_index(r, c, dr, dc)
        self.intent   = _assign_intent(self.li, cfg.num_lanes, prof.ignore_lane)
        self.in_inter = False
        self.turned   = False

        # Cache rosso
        self._rr_val  = False
        self._rr_step = -1

        # Cache precedenza (right-of-way)
        self._row_val  = False   # True = ha deciso di cedere la precedenza
        self._row_step = -1

        # Stato slip lane (bypass fisico a L, visibile cella per cella)
        # slip_path     : sequenza ordinata (r,c) celle del percorso (slip + exit cell)
        # slip_path_idx : indice della prossima cella da raggiungere
        # slip_exit_dr/dc : direzione di marcia al termine del percorso
        self.slip_path:     tuple = ()   # vuoto = non in slip lane
        self.slip_path_idx: int   = 0
        self.slip_exit_dr:  int   = 0
        self.slip_exit_dc:  int   = 0

    def __repr__(self) -> str:
        return (
            f"Car(id={self.id}, pos=({self.r},{self.c}), "
            f"dir=({self.dr},{self.dc}), spd={self.spd}, "
            f"pers={self.pers}, frus={self.frus})"
        )


def _assign_intent(lane_idx: int, num_lanes: int, ignore_lane_prob: float) -> str:
    """
    Assegna il piano di svolta all'incrocio in base alla corsia e alla personalita'.

    Regole standard:
        corsia 0       (destra)  : dritto (60%) o destra (40%)
        corsia N-1     (sinistra): dritto (55%) o sinistra (45%)
        corsie centrali          : dritto (68%) o sinistra (32%)

    Se il guidatore ignora le regole di corsia (probabilita' ignore_lane_prob),
    la scelta e' completamente casuale tra le tre opzioni.

    Args:
        lane_idx        : indice corsia (0 = destra, N-1 = sinistra)
        num_lanes       : numero di corsie per senso di marcia
        ignore_lane_prob: probabilita' di ignorare la regola di corsia
    """
    if random.random() < ignore_lane_prob or num_lanes == 1:
        return random.choices(["straight", "right", "left"], [50, 25, 25])[0]

    if lane_idx == 0:
        return random.choices(["straight", "right"], [60, 40])[0]
    if lane_idx == num_lanes - 1:
        return random.choices(["straight", "left"], [55, 45])[0]
    return random.choices(["straight", "left"], [68, 32])[0]


# =====================================================================
# OSTACOLO
# =====================================================================

class Obstacle:
    """
    Blocco fisso su una cella della griglia.
    Rappresenta incidenti, veicoli in panne, cantieri temporanei, ecc.

    Attributi:
        r, c     : posizione sulla griglia
        dur      : durata residua in step (-1 = permanente)
        label    : etichetta descrittiva
    """

    def __init__(self, r: int, c: int, dur: int, label: str = "incidente"):
        self.r     = r
        self.c     = c
        self.dur   = dur       # -1 = permanente
        self.label = label

    def tick(self) -> bool:
        """
        Avanza di uno step.
        Ritorna True se l'ostacolo e' ancora attivo, False se scaduto.
        Gli ostacoli permanenti (dur=-1) ritornano sempre True.
        """
        if self.dur == -1:
            return True
        self.dur -= 1
        return self.dur > 0

    def __repr__(self) -> str:
        dur_str = "permanente" if self.dur == -1 else f"dur={self.dur}"
        return f"Obstacle({self.label}, pos=({self.r},{self.c}), {dur_str})"
