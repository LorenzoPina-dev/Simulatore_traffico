"""
traffic_light.py — Semaforo e politiche di ciclo.

TrafficLight e' una macchina a stati che gestisce le fasi semaforiche.
La politica di ciclo e' selezionabile tramite LightPolicy in SimConfig:

    FIXED          — ciclo fisso classico, tempi configurabili per asse
    ADAPTIVE       — prolunga il verde verso la direzione con piu' code
    ALWAYS_GREEN_H — sempre verde sull'asse orizzontale
    ALWAYS_GREEN_V — sempre verde sull'asse verticale
    NO_LIGHT       — nessun semaforo (tutti passano sempre)
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Set

from .config import LightPolicy

if TYPE_CHECKING:
    from .config   import SimConfig
    from .geometry import GridGeometry


class TrafficLight:
    """
    Semaforo per un incrocio a +.

    Fase interna (self._phase):
        'HG'  — asse H verde, asse V rosso
        'HY'  — asse H giallo (transizione)
        'VG'  — asse V verde, asse H rosso
        'VY'  — asse V giallo (transizione)
        'ALL' — tutti verdi (solo NO_LIGHT)

    I metodi h_go() e v_go() ritornano True se la rispettiva
    direzione ha il via libera (verde o giallo per chi e' gia' in moto).
    """

    def __init__(self, cfg: "SimConfig", geo: "GridGeometry"):
        self._policy  = cfg.light_policy
        self._green_h = cfg.light_green_h
        self._green_v = cfg.light_green_v
        self._yellow  = cfg.light_yellow
        self._min_g   = cfg.light_min_green
        self._max_g   = cfg.light_max_green
        self._check   = cfg.adaptive_check_interval
        self._geo     = geo

        self._t      = 0         # contatore interno step nella fase corrente
        self._phase  = "HG"      # fase iniziale: H verde
        self._period = 0         # calcolato da _build_period()

        if self._policy == LightPolicy.NO_LIGHT:
            self._phase = "ALL"
        elif self._policy == LightPolicy.ALWAYS_GREEN_H:
            self._phase = "HG"
        elif self._policy == LightPolicy.ALWAYS_GREEN_V:
            self._phase = "VG"

        self._build_period()

    # ── Ciclo ──────────────────────────────────────────────────────────

    def _build_period(self):
        """Precalcola la durata totale di un ciclo completo (FIXED)."""
        self._period = self._green_h + self._green_v + 2 * self._yellow

    def tick(self, cars=None):
        """
        Avanza il semaforo di uno step.

        Args:
            cars : lista di Car attive (richiesta solo da ADAPTIVE)
        """
        if self._policy in (LightPolicy.NO_LIGHT,
                            LightPolicy.ALWAYS_GREEN_H,
                            LightPolicy.ALWAYS_GREEN_V):
            return   # nessun aggiornamento necessario

        self._t += 1

        if self._policy == LightPolicy.FIXED:
            self._tick_fixed()
        elif self._policy == LightPolicy.ADAPTIVE:
            self._tick_adaptive(cars or [])

    def _tick_fixed(self):
        """Avanza il ciclo fisso."""
        if self._phase == "HG" and self._t >= self._green_h:
            self._phase = "HY"; self._t = 0
        elif self._phase == "HY" and self._t >= self._yellow:
            self._phase = "VG"; self._t = 0
        elif self._phase == "VG" and self._t >= self._green_v:
            self._phase = "VY"; self._t = 0
        elif self._phase == "VY" and self._t >= self._yellow:
            self._phase = "HG"; self._t = 0

    def _tick_adaptive(self, cars):
        """
        Ciclo adattivo: controlla le code ogni `_check` step e
        prolunga il verde della direzione con piu' auto in attesa.
        Rispetta comunque le durate minima e massima.
        """
        # Fase gialla: transizione fissa, non interrompibile
        if self._phase in ("HY", "VY"):
            if self._t >= self._yellow:
                self._phase = "VG" if self._phase == "HY" else "HG"
                self._t = 0
            return

        # Durata minima garantita
        if self._t < self._min_g:
            return

        # Durata massima: cambia comunque
        if self._t >= self._max_g:
            self._start_yellow()
            return

        # Controllo adattivo ogni N step
        if self._t % self._check == 0:
            h_queue = self._count_h_queue(cars)
            v_queue = self._count_v_queue(cars)
            if self._phase == "HG" and v_queue > h_queue * 1.5:
                self._start_yellow()
            elif self._phase == "VG" and h_queue > v_queue * 1.5:
                self._start_yellow()

    def _start_yellow(self):
        """Transisce alla fase gialla dalla fase verde corrente."""
        if self._phase == "HG":
            self._phase = "HY"
        elif self._phase == "VG":
            self._phase = "VY"
        self._t = 0

    def _count_h_queue(self, cars) -> int:
        """Conta auto orizzontali in attesa vicino alla stop line."""
        geo = self._geo
        return sum(
            1 for c in cars
            if c.dc != 0                         # direzione orizzontale
            and not geo.in_intersection(c.r, c.c)
            and c.spd == 0
        )

    def _count_v_queue(self, cars) -> int:
        """Conta auto verticali in attesa vicino alla stop line."""
        geo = self._geo
        return sum(
            1 for c in cars
            if c.dr != 0                         # direzione verticale
            and not geo.in_intersection(c.r, c.c)
            and c.spd == 0
        )

    # ── Stato corrente ─────────────────────────────────────────────────

    def h_go(self) -> bool:
        """True se l'asse orizzontale ha il via libera."""
        return self._phase in ("HG", "HY", "ALL")

    def v_go(self) -> bool:
        """True se l'asse verticale ha il via libera."""
        return self._phase in ("VG", "VY", "ALL")

    def is_yellow(self) -> bool:
        """True se siamo in una fase di transizione gialla."""
        return self._phase in ("HY", "VY")

    def phase_label(self) -> str:
        """Etichetta leggibile della fase corrente."""
        labels = {
            "HG":  "H:VERDE   V:ROSSO",
            "HY":  "H:GIALLO  V:ROSSO",
            "VG":  "H:ROSSO   V:VERDE",
            "VY":  "H:ROSSO   V:GIALLO",
            "ALL": "LIBERO (no semaforo)",
        }
        return labels.get(self._phase, self._phase)

    def stop_line_colors(self) -> tuple:
        """
        Ritorna (color_h, color_v) come indici nella colormap:
            8 = ROSSO, 9 = VERDE, 10 = GIALLO
        Usato dal Renderer per disegnare le stop line.
        """
        if self._phase == "HG":  return (9, 8)
        if self._phase == "VG":  return (8, 9)
        if self._phase == "ALL": return (9, 9)
        return (10, 10)  # giallo / transizione

    # ── Celle di blocco ────────────────────────────────────────────────

    def red_block_cells(self, car, step: int, geo: "GridGeometry") -> Set:
        """
        Restituisce il set di celle virtuali bloccate dal semaforo
        per questa auto. Se l'auto ha deciso di passare col rosso,
        il set e' vuoto.

        Il blocco e' posizionato SULLA stop line (1 cella prima
        dell'incrocio), cosi' le auto si fermano una cella piu' indietro
        e la stop line rimane visibile nel render.

        La decisione di passare col rosso viene campionata una sola
        volta per step (memoizzata su car._rr_step / car._rr_val).
        """
        is_h = (car.dc != 0)
        go   = self.h_go() if is_h else self.v_go()
        if go:
            return set()

        # Campiona una volta per step
        if car._rr_step != step:
            car._rr_step = step
            car._rr_val  = (
                __import__("random").random() < car.rr
            )

        if car._rr_val:
            return set()   # passaggio col rosso

        # Blocca la stop line stessa (le auto si fermano 1 cella prima)
        r, c = car.r, car.c
        if car.dc == 1:   return {(r, geo.ic0 - 1)}
        if car.dc == -1:  return {(r, geo.ic1 + 1)}
        if car.dr == 1:   return {(geo.ir0 - 1, c)}
        return {(geo.ir1 + 1, c)}
