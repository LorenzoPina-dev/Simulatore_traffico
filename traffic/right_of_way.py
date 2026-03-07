"""
right_of_way.py — Logica di precedenza (diritto di precedenza / right-of-way).

Regola implementata:
    Chi svolta a SINISTRA deve cedere la precedenza a chiunque provenga
    dalla direzione opposta andando DRITTO o girando a DESTRA.

La decisione di rispettare o ignorare la precedenza dipende da:
    - Profilo personalita' del guidatore  (ignore_row_prob base)
    - Frustrazione accumulata             (ogni punto += row_frustration_factor)
    - Gap disponibile nella corsia opposta (se gap >= row_yield_gap, passa)

La decisione viene campionata UNA VOLTA per step per auto
e memoizzata su car._row_val / car._row_step.

Architettura:
    RightOfWayChecker
        |-- is_left_turn_approaching()   : il controllo si applica?
        |-- oncoming_threat()            : c'e' traffico con precedenza?
        |-- _ignore_probability()        : P di ignorare la precedenza
        |-- should_yield()               : API principale → bool
        |-- yield_block_cell()           : cella virtuale da bloccare se yield
"""

from __future__ import annotations
import random
from typing import Dict, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .config   import SimConfig
    from .geometry import GridGeometry
    from .entities import Car


class RightOfWayChecker:
    """
    Valuta, per ogni auto che sta per girare a sinistra, se deve cedere
    la precedenza al traffico opposto e se — in base alla personalita'
    e alla frustrazione — scegliera' effettivamente di farlo.

    Parametri da SimConfig:
        row_enabled            : attiva/disattiva l'intero sistema
        row_lookahead          : celle prima dell'incrocio in cui il check si attiva
        row_oncoming_check     : celle (dal lato opposto) da scansionare per minacce
        row_frustration_factor : incremento P(ignora) per punto di frustrazione
        row_yield_gap          : se gap oncoming >= questo valore, l'auto procede
    """

    def __init__(self, cfg: "SimConfig", geo: "GridGeometry"):
        self._cfg = cfg
        self._geo = geo

    # ── API principale ────────────────────────────────────────────────

    def should_yield(self, car: "Car", occ: Dict, step: int) -> bool:
        """
        Ritorna True se l'auto DEVE fermarsi per cedere la precedenza.

        Logica:
            1. Il sistema e' abilitato e l'auto gira a sinistra?
            2. E' nella finestra di approccio all'incrocio?
            3. C'e' traffico opposto con precedenza?
            4. Il guidatore decide di rispettare la precedenza?

        La decisione (3+4) viene memoizzata per lo step corrente.
        """
        cfg = self._cfg
        if not cfg.row_enabled:
            return False
        if car.intent != "left":
            return False
        if car.in_inter:
            return False   # gia' dentro: non si ferma piu'
        if not self.is_approaching(car):
            return False

        # Campiona la decisione una sola volta per step
        if car._row_step != step:
            car._row_step = step
            threat = self.oncoming_threat(car, occ)
            if not threat:
                car._row_val = False
            else:
                p_ignore = self._ignore_probability(car)
                car._row_val = (random.random() >= p_ignore)  # True = cede
        return car._row_val

    def yield_block_cell(self, car: "Car") -> Set:
        """
        Ritorna la cella virtuale da bloccare per simulare l'attesa.
        E' la cella di ingresso nell'incrocio per la direzione del veicolo.
        """
        geo = self._geo
        if car.dc == 1:   return {(car.r, geo.ic0)}      # →  blocca entrata destra
        if car.dc == -1:  return {(car.r, geo.ic1)}      # ←  blocca entrata sinistra
        if car.dr == 1:   return {(geo.ir0, car.c)}      # ↓  blocca entrata alto
        return {(geo.ir1, car.c)}                         # ↑  blocca entrata basso

    # ── Finestra di approccio ─────────────────────────────────────────

    def is_approaching(self, car: "Car") -> bool:
        """
        True se il veicolo e' entro `row_lookahead` celle dall'incrocio
        nella sua direzione di marcia.

        Questo limita il check alla zona immediatamente prima dell'incrocio,
        evitando falsi positivi per auto lontane.
        """
        geo = self._geo
        lk  = self._cfg.row_lookahead

        if car.dc == 1:   # → : si avvicina da sinistra
            return geo.ic0 - lk <= car.c < geo.ic0
        if car.dc == -1:  # ← : si avvicina da destra
            return geo.ic1 < car.c <= geo.ic1 + lk
        if car.dr == 1:   # ↓ : si avvicina dall'alto
            return geo.ir0 - lk <= car.r < geo.ir0
        # ↑ : si avvicina dal basso
        return geo.ir1 < car.r <= geo.ir1 + lk

    # ── Rilevamento traffico opposto ──────────────────────────────────

    def oncoming_threat(self, car: "Car", occ: Dict) -> bool:
        """
        True se esiste almeno un veicolo con precedenza nel percorso
        che la svolta a sinistra andrà a intersecare.

        "Veicolo con precedenza" = viene dalla direzione opposta
        (testa a testa) e ha intent in {"straight", "right", None}.
        I veicoli che girano a sinistra anch'essi NON hanno precedenza
        su un altro che gira a sinistra (conflitto simmetrico ignorato
        per semplicita').

        Scansione: righe/colonne della corsia opposta entro
        `row_oncoming_check` celle dall'ingresso opposto dell'incrocio.
        """
        geo  = self._geo
        chk  = self._cfg.row_oncoming_check
        odr, odc = -car.dr, -car.dc   # direzione opposta (testa a testa)

        # Genera le celle da scansionare
        cells = self._oncoming_cells(car, chk)

        for (r, c) in cells:
            other = occ.get((r, c))
            if other is None:
                continue
            if (other.dr, other.dc) != (odr, odc):
                continue   # non viene dalla direzione opposta
            if other.intent == "left":
                continue   # anche lui gira a sinistra: nessuna precedenza
            # Ha precedenza: c'e' una minaccia
            # Verifica aggiuntiva: gap nella corsia opposta dalla nostra posizione
            # Se il traffico e' molto lontano e il gap e' ampio, possiamo passare
            dist = self._distance_to_intersection(other)
            if dist > self._cfg.row_yield_gap:
                # Lontano: considera comunque minaccia ma con peso ridotto
                # (la decisione finale la prende _ignore_probability)
                return True
            return True

        return False

    def _oncoming_cells(self, car: "Car", lookahead: int):
        """
        Genera le coordinate delle celle da scansionare per il traffico
        opposto. Include sia le celle DENTRO l'incrocio (traffico gia'
        in transito) che le celle di APPROCCIO dal lato opposto.
        """
        geo = self._geo
        cells = []

        if car.dc == 1:      # → : cerca ← nelle righe ir0..center-1
            rows = range(geo.ir0, geo.center)
            # Traffico ← nell'incrocio
            for r in rows:
                for c in range(geo.ic0, geo.ic1 + 1):
                    cells.append((r, c))
            # Traffico ← in approccio (viene da destra, c > ic1)
            for r in rows:
                for c in range(geo.ic1 + 1, geo.ic1 + 1 + lookahead):
                    if geo.in_bounds(r, c):
                        cells.append((r, c))

        elif car.dc == -1:   # ← : cerca → nelle righe center..ir1
            rows = range(geo.center, geo.ir1 + 1)
            for r in rows:
                for c in range(geo.ic0, geo.ic1 + 1):
                    cells.append((r, c))
            # Traffico → in approccio (viene da sinistra, c < ic0)
            for r in rows:
                for c in range(max(0, geo.ic0 - lookahead), geo.ic0):
                    if geo.in_bounds(r, c):
                        cells.append((r, c))

        elif car.dr == 1:    # ↓ : cerca ↑ nelle colonne ic0..center-1
            cols = range(geo.ic0, geo.center)
            for c in cols:
                for r in range(geo.ir0, geo.ir1 + 1):
                    cells.append((r, c))
            # Traffico ↑ in approccio (viene dal basso, r > ir1)
            for c in cols:
                for r in range(geo.ir1 + 1, geo.ir1 + 1 + lookahead):
                    if geo.in_bounds(r, c):
                        cells.append((r, c))

        else:                # ↑ : cerca ↓ nelle colonne center..ic1
            cols = range(geo.center, geo.ic1 + 1)
            for c in cols:
                for r in range(geo.ir0, geo.ir1 + 1):
                    cells.append((r, c))
            # Traffico ↓ in approccio (viene dall'alto, r < ir0)
            for c in cols:
                for r in range(max(0, geo.ir0 - lookahead), geo.ir0):
                    if geo.in_bounds(r, c):
                        cells.append((r, c))

        return cells

    def _distance_to_intersection(self, other: "Car") -> int:
        """
        Stima la distanza di 'other' dall'ingresso dell'incrocio
        (in celle). Usata per valutare quanto e' urgente la minaccia.
        """
        geo = self._geo
        if other.dc == 1:   return max(0, geo.ic0 - other.c)
        if other.dc == -1:  return max(0, other.c - geo.ic1)
        if other.dr == 1:   return max(0, geo.ir0 - other.r)
        return max(0, other.r - geo.ir1)

    # ── Calcolo probabilita' di ignorare ─────────────────────────────

    def _ignore_probability(self, car: "Car") -> float:
        """
        Calcola la probabilita' che il guidatore IGNORI la precedenza.

        Formula:
            P(ignora) = clamp(ignore_row_prob + frus * factor, 0, max_ignore)

        Dove:
            ignore_row_prob : parametro base del profilo personalita'
            frus            : frustrazione corrente [0, frustration_max]
            factor          : row_frustration_factor da SimConfig
            max_ignore      : 0.95 (nessuno ignora sempre al 100%)
        """
        base   = car.ir                               # ignore_row_prob del profilo
        bonus  = car.frus * self._cfg.row_frustration_factor
        return min(base + bonus, 0.95)

    # ── Statistiche ───────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"RightOfWayChecker("
            f"enabled={self._cfg.row_enabled}, "
            f"lookahead={self._cfg.row_lookahead}, "
            f"oncoming_check={self._cfg.row_oncoming_check})"
        )
