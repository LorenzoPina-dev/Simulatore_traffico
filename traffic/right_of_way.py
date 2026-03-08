"""
right_of_way.py — Logica di precedenza (diritto di precedenza / right-of-way).

Supporta tre regole, configurabili via TopologyConfig.row_yield_to:

  "right"    (default) — Incrocio non regolato italiano:
                chi viene DA DESTRA ha la precedenza su tutti.
                Ogni auto cede a quella proveniente dal braccio a destra.

  "left"     — Rotatoria:
                chi e' GIA' NELL'INCROCIO (da sinistra) ha la precedenza.
                Le auto in entrata cedono a chi circola gia'.

  "oncoming" — Comportamento storico:
                solo chi gira a sinistra cede al traffico opposto (dritto/destra).

Per "right" e "left" il controllo si attiva per TUTTE le auto in approccio,
non solo per chi gira a sinistra.

Parametri in SimConfig (invariati):
    row_enabled, row_lookahead, row_oncoming_check,
    row_frustration_factor, row_yield_gap
"""

from __future__ import annotations
import random
from typing import Dict, List, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .config   import SimConfig
    from .geometry import GridGeometry
    from .entities import Car


# Mappatura: (mia direzione) → (direzione da cui arriva chi ha precedenza)
# per la regola "yield to right" (incrocio italiano non regolato)
_YIELD_RIGHT: dict[Tuple[int,int], Tuple[int,int]] = {
    (0,  1): (-1, 0),   # → cede a ↑  (viene da sud)
    (-1, 0): (0,  1),   # ↑ cede a →  (viene da ovest)
    (0, -1): (1,  0),   # ← cede a ↓  (viene da nord)
    (1,  0): (0, -1),   # ↓ cede a ←  (viene da est)
}

# per la regola "yield to left" (rotatoria)
_YIELD_LEFT: dict[Tuple[int,int], Tuple[int,int]] = {
    (0,  1): (1,  0),   # → cede a ↓  (viene da nord)
    (1,  0): (0, -1),   # ↓ cede a ←  (viene da est)
    (0, -1): (-1, 0),   # ← cede a ↑  (viene da sud)
    (-1, 0): (0,  1),   # ↑ cede a →  (viene da ovest)
}


class RightOfWayChecker:
    """
    Valuta, per ogni auto in approccio, se deve cedere la precedenza
    in base alla regola configurata nella topologia corrente.

    API:
        should_yield(car, occ, step) -> bool
        yield_block_cell(car)        -> Set[tuple]
        is_approaching(car)          -> bool
        oncoming_threat(car, occ)    -> bool
    """

    def __init__(self, cfg: "SimConfig", geo: "GridGeometry"):
        self._cfg = cfg
        self._geo = geo

    # ── Regola attiva ─────────────────────────────────────────────────

    def _rule(self) -> str:
        """Ritorna la regola di precedenza attiva ('right'|'left'|'oncoming')."""
        rule = getattr(self._geo.topo, "row_yield_to", "oncoming")
        return rule if rule in ("right", "left", "oncoming") else "oncoming"

    # ── API principale ────────────────────────────────────────────────

    def should_yield(self, car: "Car", occ: Dict, step: int) -> bool:
        """
        Ritorna True se l'auto deve cedere la precedenza questo step.

        La decisione viene campionata una sola volta per step e memoizzata
        su car._row_val / car._row_step per evitare oscillazioni.
        """
        cfg  = self._cfg
        rule = self._rule()

        if not cfg.row_enabled:
            return False
        if car.in_inter:
            return False
        if not self.is_approaching(car):
            return False

        # "oncoming": solo chi gira a sinistra
        if rule == "oncoming" and car.intent != "left":
            return False

        # Campionamento una volta per step
        if car._row_step != step:
            car._row_step = step
            threat = self.oncoming_threat(car, occ)
            if not threat:
                car._row_val = False
            else:
                p_ignore     = self._ignore_probability(car)
                car._row_val = (random.random() >= p_ignore)
        return car._row_val

    def yield_block_cell(self, car: "Car") -> Set:
        """
        Cella virtuale da bloccare per simulare l'attesa in precedenza.
        E' la prima cella di ingresso nell'incrocio.
        """
        geo = self._geo
        if car.dc == 1:   return {(car.r, geo.ic0)}
        if car.dc == -1:  return {(car.r, geo.ic1)}
        if car.dr == 1:   return {(geo.ir0, car.c)}
        return {(geo.ir1, car.c)}

    # ── Approccio ─────────────────────────────────────────────────────

    def is_approaching(self, car: "Car") -> bool:
        """True se l'auto e' entro row_lookahead celle dall'incrocio."""
        geo = self._geo
        lk  = self._cfg.row_lookahead
        if car.dc == 1:   return geo.ic0 - lk <= car.c < geo.ic0
        if car.dc == -1:  return geo.ic1 < car.c <= geo.ic1 + lk
        if car.dr == 1:   return geo.ir0 - lk <= car.r < geo.ir0
        return geo.ir1 < car.r <= geo.ir1 + lk

    # ── Rilevamento minaccia ──────────────────────────────────────────

    def oncoming_threat(self, car: "Car", occ: Dict) -> bool:
        """
        True se esiste un veicolo con precedenza nel percorso di conflitto.

        Logica per regola:
          "oncoming" : traffico opposto (testa a testa) non girante sx
          "right"    : traffico dal braccio a destra in avvicinamento
          "left"     : traffico dal braccio a sinistra (gia' nell'incrocio)
        """
        rule = self._rule()
        chk  = self._cfg.row_oncoming_check

        if rule == "oncoming":
            return self._threat_oncoming(car, occ, chk)
        elif rule == "right":
            pdr, pdc = _YIELD_RIGHT.get((car.dr, car.dc), (0, 0))
            return self._threat_from_direction(car, occ, pdr, pdc, chk)
        else:  # "left"
            pdr, pdc = _YIELD_LEFT.get((car.dr, car.dc), (0, 0))
            return self._threat_from_direction(car, occ, pdr, pdc, chk)

    # ── Implementazioni per regola ────────────────────────────────────

    def _threat_oncoming(self, car: "Car", occ: Dict, chk: int) -> bool:
        """
        Regola "oncoming": cerca traffico opposto (chi viene testa a testa)
        che non sta girando a sinistra.
        """
        odr, odc = -car.dr, -car.dc
        for (r, c) in self._oncoming_cells(car, chk):
            other = occ.get((r, c))
            if other is None:
                continue
            if (other.dr, other.dc) != (odr, odc):
                continue
            if other.intent == "left":
                continue   # anche lui gira sx: simmetrico, ignora
            return True
        return False

    def _threat_from_direction(
        self,
        car: "Car",
        occ: Dict,
        pdr: int, pdc: int,
        chk: int,
    ) -> bool:
        """
        Regola "right"/"left": cerca veicoli che si avvicinano dal braccio
        di priorita' (direzione pdr, pdc) entro chk celle dall'incrocio.
        Controlla anche l'interno dell'incrocio (gia' dentro = minaccia reale).
        """
        if (pdr, pdc) == (0, 0):
            return False

        geo  = self._geo
        cells: List[Tuple[int,int]] = []

        # Celle DENTRO l'incrocio (veicoli gia' in transito)
        cells += self._inter_cells_for(pdr, pdc)

        # Celle di APPROCCIO (nel braccio di provenienza)
        cells += self._approach_cells_for(pdr, pdc, chk)

        for (r, c) in cells:
            other = occ.get((r, c))
            if other is None:
                continue
            if (other.dr, other.dc) != (pdr, pdc):
                continue
            dist = self._distance_to_intersection(other)
            if dist <= chk:
                return True
        return False

    # ── Celle da scansionare ──────────────────────────────────────────

    def _oncoming_cells(self, car: "Car", lookahead: int) -> List[Tuple[int,int]]:
        """Celle per traffico opposto (regola 'oncoming')."""
        geo = self._geo
        cells: List[Tuple[int,int]] = []

        if car.dc == 1:      # → : cerca ← nelle righe ir0..center-1
            rows = range(geo.ir0, geo.center_r)
            for r in rows:
                for c in range(geo.ic0, geo.ic1 + 1):
                    cells.append((r, c))
                for c in range(geo.ic1 + 1, geo.ic1 + 1 + lookahead):
                    if geo.in_bounds(r, c): cells.append((r, c))

        elif car.dc == -1:   # ← : cerca → nelle righe center..ir1
            rows = range(geo.center_r, geo.ir1 + 1)
            for r in rows:
                for c in range(geo.ic0, geo.ic1 + 1):
                    cells.append((r, c))
                for c in range(max(0, geo.ic0 - lookahead), geo.ic0):
                    if geo.in_bounds(r, c): cells.append((r, c))

        elif car.dr == 1:    # ↓ : cerca ↑ nelle colonne cc..ic1
            cols = range(geo.center_c, geo.ic1 + 1)
            for c in cols:
                for r in range(geo.ir0, geo.ir1 + 1):
                    cells.append((r, c))
                for r in range(geo.ir1 + 1, geo.ir1 + 1 + lookahead):
                    if geo.in_bounds(r, c): cells.append((r, c))

        else:                # ↑ : cerca ↓ nelle colonne ic0..cc-1
            cols = range(geo.ic0, geo.center_c)
            for c in cols:
                for r in range(geo.ir0, geo.ir1 + 1):
                    cells.append((r, c))
                for r in range(max(0, geo.ir0 - lookahead), geo.ir0):
                    if geo.in_bounds(r, c): cells.append((r, c))

        return cells

    def _inter_cells_for(self, pdr: int, pdc: int) -> List[Tuple[int,int]]:
        """Celle nell'incrocio percorse da veicoli con direzione (pdr,pdc)."""
        geo   = self._geo
        cells = []
        if pdc == 1:   # → nell'incrocio: righe [cr..ir1]
            for r in range(geo.center_r, geo.ir1 + 1):
                for c in range(geo.ic0, geo.ic1 + 1):
                    cells.append((r, c))
        elif pdc == -1: # ← nell'incrocio: righe [ir0..cr-1]
            for r in range(geo.ir0, geo.center_r):
                for c in range(geo.ic0, geo.ic1 + 1):
                    cells.append((r, c))
        elif pdr == 1:  # ↓ nell'incrocio: colonne [ic0..cc-1]
            for c in range(geo.ic0, geo.center_c):
                for r in range(geo.ir0, geo.ir1 + 1):
                    cells.append((r, c))
        else:           # ↑ nell'incrocio: colonne [cc..ic1]
            for c in range(geo.center_c, geo.ic1 + 1):
                for r in range(geo.ir0, geo.ir1 + 1):
                    cells.append((r, c))
        return cells

    def _approach_cells_for(
        self, pdr: int, pdc: int, chk: int
    ) -> List[Tuple[int,int]]:
        """
        Celle di approccio (fuori incrocio) per veicoli con direzione (pdr,pdc).
        Scansiona le celle sul loro braccio prima dell'ingresso.
        """
        geo   = self._geo
        cells = []
        if pdc == 1:   # → proviene da ovest: col 0..ic0-1, righe [cr..ir1]
            for r in range(geo.center_r, geo.ir1 + 1):
                for c in range(max(0, geo.ic0 - chk), geo.ic0):
                    cells.append((r, c))
        elif pdc == -1: # ← proviene da est: col ic1+1..end, righe [ir0..cr-1]
            for r in range(geo.ir0, geo.center_r):
                for c in range(geo.ic1 + 1, min(geo.size, geo.ic1 + 1 + chk)):
                    cells.append((r, c))
        elif pdr == 1:  # ↓ proviene da nord: riga 0..ir0-1, col [ic0..cc-1]
            for c in range(geo.ic0, geo.center_c):
                for r in range(max(0, geo.ir0 - chk), geo.ir0):
                    cells.append((r, c))
        else:           # ↑ proviene da sud: riga ir1+1..end, col [cc..ic1]
            for c in range(geo.center_c, geo.ic1 + 1):
                for r in range(geo.ir1 + 1, min(geo.size, geo.ir1 + 1 + chk)):
                    cells.append((r, c))
        return cells

    def _distance_to_intersection(self, other: "Car") -> int:
        """Distanza di 'other' dall'ingresso dell'incrocio (in celle)."""
        geo = self._geo
        if other.dc == 1:   return max(0, geo.ic0 - other.c)
        if other.dc == -1:  return max(0, other.c - geo.ic1)
        if other.dr == 1:   return max(0, geo.ir0 - other.r)
        return max(0, other.r - geo.ir1)

    # ── Probabilita' di ignorare ──────────────────────────────────────

    def _ignore_probability(self, car: "Car") -> float:
        """P(ignora precedenza) = base + frus * factor, capped a 0.95."""
        base  = car.ir
        bonus = car.frus * self._cfg.row_frustration_factor
        return min(base + bonus, 0.95)

    def __repr__(self) -> str:
        return (
            f"RightOfWayChecker(rule={self._rule()!r}, "
            f"enabled={self._cfg.row_enabled}, "
            f"lookahead={self._cfg.row_lookahead})"
        )
