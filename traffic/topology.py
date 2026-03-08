"""
topology.py — Topologie degli incroci.

Un'intersezione e' composta da fino a 4 SEGMENTI STRADALI fisici:
    west  — strada a ovest dell'incrocio  (porta traffico → e ←)
    east  — strada a est                  (porta traffico → e ←)
    north — strada a nord                 (porta traffico ↓ e ↑)
    south — strada a sud                  (porta traffico ↓ e ↑)

Disabilitare un segmento crea intersezioni a T, Y (offset), ecc.
Le corsie dedicate si inseriscono DENTRO il range corsie esistente
(la corsia piu' a sinistra/destra in senso di marcia e' riservata).

Convenzioni senso di marcia:
    → (est)  : usa le righe del WEST segment  [center_r … ir1]
    ← (ovest): usa le righe dell'EAST segment [ir0 … center_r-1]
    ↓ (sud)  : usa le colonne del NORTH segment [center_c … ic1]
    ↑ (nord) : usa le colonne del SOUTH segment [ic0 … center_c-1]

Perche' il segmento WEST porta il traffico → e non ←?
    Il segmento WEST e' la strada fisica a ovest dell'incrocio.
    Le auto provenienti da ovest (going →) entrano DA quel segmento.
    Le auto che escono a ovest (going ←) escono IN quel segmento.
    Se lo disabilito, non ci sono ne' entrate ne' uscite verso ovest.

Utilizzo rapido:
    from traffic.topology import RoadSegment, TopologyConfig, TOPOLOGIES

    # T-incrocio: nessuna strada a nord
    topo = TopologyConfig(
        name="T_south",
        north=RoadSegment(enabled=False)
    )
    cfg = SimConfig(topology=topo)

    # Incrocio con corsie dedicate alla svolta
    topo = TOPOLOGIES["dedicated_turns"]
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# =====================================================================
# SEGMENTO STRADALE
# =====================================================================

@dataclass
class RoadSegment:
    """
    Configurazione di un singolo braccio stradale.

    Attributi:
        enabled          : se False il braccio non esiste (T-junction, ecc.)
        lanes_inbound    : corsie in ENTRATA verso l'incrocio
                           None = usa SimConfig.num_lanes
        lanes_outbound   : corsie in USCITA dall'incrocio
                           None = uguale a lanes_inbound
        left_turn_lane   : True = la corsia piu' A SINISTRA del senso di
                           marcia e' dedicata alla svolta a sinistra
        right_turn_lane  : True = la corsia piu' A DESTRA e' dedicata
                           alla svolta a destra
        spawn_prob       : probabilita' di spawn per questo braccio
                           None = usa SimConfig.spawn_prob (o override direzionale)
        label            : nome descrittivo (usato nel render e nel debug)

    Nota sulle corsie dedicate:
        Le corsie dedicate NON aggiungono celle alla griglia.
        La corsia gia' esistente piu' esterna viene riservata per quella
        manovra: le auto che spawnano in quella riga/colonna hanno
        l'intent forzato. Richiede almeno 2 corsie (se hai 1 sola corsia
        non puoi dedicarne una — il flag viene ignorato).
    """
    enabled:         bool          = True
    lanes_inbound:   Optional[int] = None
    lanes_outbound:  Optional[int] = None
    left_turn_lane:  bool          = False
    right_turn_lane: bool          = False
    spawn_prob:      Optional[float] = None
    label:           str           = ""

    def inbound(self, default: int) -> int:
        """Corsie in entrata effettive."""
        return self.lanes_inbound if self.lanes_inbound is not None else default

    def outbound(self, default: int) -> int:
        """Corsie in uscita effettive."""
        n = self.inbound(default)
        return self.lanes_outbound if self.lanes_outbound is not None else n

    def forced_intent(self, lane_idx: int, total_lanes: int) -> Optional[str]:
        """
        Restituisce l'intent forzato per una corsia dedicata, None altrimenti.

        Args:
            lane_idx    : indice corsia (0 = destra, N-1 = sinistra nel
                          senso di marcia)
            total_lanes : numero totale di corsie in entrata
        """
        if total_lanes < 2:
            return None  # con 1 sola corsia non si puo' dedicare
        if self.left_turn_lane and lane_idx == total_lanes - 1:
            return "left"
        if self.right_turn_lane and lane_idx == 0:
            return "right"
        return None

    def __repr__(self) -> str:
        if not self.enabled:
            return "RoadSegment(disabled)"
        parts = [f"lanes={self.lanes_inbound or 'default'}"]
        if self.left_turn_lane:  parts.append("left_lane")
        if self.right_turn_lane: parts.append("right_lane")
        if self.spawn_prob is not None: parts.append(f"spawn={self.spawn_prob:.0%}")
        if self.label: parts.append(f'"{self.label}"')
        return f"RoadSegment({', '.join(parts)})"


# =====================================================================
# TOPOLOGIA INCROCIO
# =====================================================================

@dataclass
class TopologyConfig:
    """
    Descrive la topologia completa dell'incrocio.

    I quattro segmenti (west, east, north, south) descrivono i bracci
    fisici dell'incrocio. Disabilita un segmento per creare T-junction,
    strade a senso unico, ecc.

    Attributi:
        name              : nome descrittivo della topologia
        west              : segmento a ovest  (traffico → e ←)
        east              : segmento a est    (traffico → e ←)
        north             : segmento a nord   (traffico ↓ e ↑)
        south             : segmento a sud    (traffico ↓ e ↑)
        center_row_offset : sposta il centro dell'incrocio verticalmente
                            (positivo = verso sud, negativo = verso nord)
        center_col_offset : sposta il centro orizzontalmente
                            (positivo = verso est, negativo = verso ovest)

    Esempi:
        # + standard
        TopologyConfig()

        # T-junction: strada che termina a nord
        TopologyConfig(name="T_no_north", north=RoadSegment(enabled=False))

        # Incrocio con corsia dedicata svolta sinistra su tutti i bracci
        TopologyConfig(
            name="all_left_lanes",
            west=RoadSegment(left_turn_lane=True),
            east=RoadSegment(left_turn_lane=True),
            north=RoadSegment(left_turn_lane=True),
            south=RoadSegment(left_turn_lane=True),
        )

        # Incrocio spostato (non centrato nella griglia)
        TopologyConfig(name="offset", center_row_offset=-10)
    """
    name:              str         = "plus"
    west:  RoadSegment = field(default_factory=RoadSegment)
    east:  RoadSegment = field(default_factory=RoadSegment)
    north: RoadSegment = field(default_factory=RoadSegment)
    south: RoadSegment = field(default_factory=RoadSegment)
    center_row_offset: int = 0
    center_col_offset: int = 0

    # ── Slip lanes (bypass diagonali per svolta destra) ───────────────
    # slip_lanes_enabled : attiva i bypass diagonali ai 4 angoli
    # slip_len           : celle di anticipo/posticipo del bypass
    # slip_exclusive     : True = la corsia destra e' SOLO per il bypass
    #                      (auto con intent!='right' non vi entrano)
    slip_lanes_enabled: bool = False
    slip_len:           int  = 5
    slip_exclusive:     bool = True

    # ── Helper ────────────────────────────────────────────────────────

    def arm(self, name: str) -> RoadSegment:
        """Ritorna il segmento per nome ('west'|'east'|'north'|'south')."""
        return getattr(self, name)

    def enabled_arms(self) -> list:
        """Lista dei nomi dei segmenti abilitati."""
        return [s for s in ("west", "east", "north", "south")
                if getattr(self, s).enabled]

    def num_enabled(self) -> int:
        return sum(1 for s in ("west", "east", "north", "south")
                   if getattr(self, s).enabled)

    def exit_segment(self, dr: int, dc: int, intent: str) -> str:
        """
        Ritorna il nome del segmento di USCITA per una manovra.

        Logica:
            → destra  → esce a sud   (south)
            → sinistra→ esce a nord  (north)
            → dritto  → esce a est   (east)
            ← destra  → esce a nord  (north)
            ← sinistra→ esce a sud   (south)
            ← dritto  → esce a ovest (west)
            ↓ destra  → esce a ovest (west)
            ↓ sinistra→ esce a est   (east)
            ↓ dritto  → esce a sud   (south)
            ↑ destra  → esce a est   (east)
            ↑ sinistra→ esce a ovest (west)
            ↑ dritto  → esce a nord  (north)
        """
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
        """True se la manovra e' possibile (il segmento di uscita e' abilitato)."""
        seg = self.exit_segment(dr, dc, intent)
        return self.arm(seg).enabled

    def fallback_intent(self, dr: int, dc: int, intent: str) -> str:
        """
        Se l'intent originale porta a un segmento disabilitato,
        restituisce l'intent alternativo migliore ('straight' > 'right').
        """
        if self.is_turn_possible(dr, dc, intent):
            return intent
        for fallback in ("straight", "right", "left"):
            if fallback != intent and self.is_turn_possible(dr, dc, fallback):
                return fallback
        return "straight"  # ultimo fallback

    def summary(self) -> str:
        arms_str = " | ".join(
            f"{name}:{self.arm(name)}"
            for name in ("west", "east", "north", "south")
        )
        return f"Topology[{self.name}]: {arms_str}"


# =====================================================================
# TOPOLOGIE PRESET
# =====================================================================

def _seg(**kw) -> RoadSegment:
    """Shorthand per creare un RoadSegment."""
    return RoadSegment(**kw)


TOPOLOGIES: dict[str, TopologyConfig] = {}

# ── 1. Incrocio a + standard ──────────────────────────────────────────
TOPOLOGIES["plus"] = TopologyConfig(name="plus")

# ── 2. T-junction: manca il braccio nord ──────────────────────────────
# Strade est-ovest + braccio verso sud. Nessuna uscita verso nord.
TOPOLOGIES["T_no_north"] = TopologyConfig(
    name="T_no_north",
    north=_seg(enabled=False),
)

# ── 3. T-junction: manca il braccio sud ───────────────────────────────
TOPOLOGIES["T_no_south"] = TopologyConfig(
    name="T_no_south",
    south=_seg(enabled=False),
)

# ── 4. T-junction: manca il braccio est ───────────────────────────────
# Strada nord-sud + entrata da ovest (strada termina all'incrocio)
TOPOLOGIES["T_no_east"] = TopologyConfig(
    name="T_no_east",
    east=_seg(enabled=False),
)

# ── 5. T-junction: manca il braccio ovest ─────────────────────────────
TOPOLOGIES["T_no_west"] = TopologyConfig(
    name="T_no_west",
    west=_seg(enabled=False),
)

# ── 6. + con corsie dedicate svolta sinistra su tutti i bracci ────────
# Ogni direzione ha la corsia piu' a sinistra riservata alla svolta sx.
# Richiede almeno 2 corsie (num_lanes >= 2).
TOPOLOGIES["dedicated_left_all"] = TopologyConfig(
    name="dedicated_left_all",
    west=_seg(left_turn_lane=True),
    east=_seg(left_turn_lane=True),
    north=_seg(left_turn_lane=True),
    south=_seg(left_turn_lane=True),
)

# ── 7. + con corsie dedicate svolta destra su tutti i bracci ──────────
TOPOLOGIES["dedicated_right_all"] = TopologyConfig(
    name="dedicated_right_all",
    west=_seg(right_turn_lane=True),
    east=_seg(right_turn_lane=True),
    north=_seg(right_turn_lane=True),
    south=_seg(right_turn_lane=True),
)

# ── 8. + con corsie dedicate sia sinistra che destra (richiede >=3 corsie)
TOPOLOGIES["dedicated_both_all"] = TopologyConfig(
    name="dedicated_both_all",
    west=_seg(left_turn_lane=True,  right_turn_lane=True),
    east=_seg(left_turn_lane=True,  right_turn_lane=True),
    north=_seg(left_turn_lane=True, right_turn_lane=True),
    south=_seg(left_turn_lane=True, right_turn_lane=True),
)

# ── 9. Incrocio asimmetrico: asse H ha piu' corsie di V ──────────────
# Simula una strada principale (H, 4 corsie) che incrocia una secondaria (V, 2)
TOPOLOGIES["asymmetric_H_main"] = TopologyConfig(
    name="asymmetric_H_main",
    west=_seg(lanes_inbound=4, label="main"),
    east=_seg(lanes_inbound=4, label="main"),
    north=_seg(lanes_inbound=2, label="secondary"),
    south=_seg(lanes_inbound=2, label="secondary"),
)

# ── 10. Incrocio asimmetrico: asse V ha piu' corsie ───────────────────
TOPOLOGIES["asymmetric_V_main"] = TopologyConfig(
    name="asymmetric_V_main",
    west=_seg(lanes_inbound=2, label="secondary"),
    east=_seg(lanes_inbound=2, label="secondary"),
    north=_seg(lanes_inbound=4, label="main"),
    south=_seg(lanes_inbound=4, label="main"),
)

# ── 11. Incrocio completo con corsie dedicate solo su asse principale ─
# Asse H (principale) ha corsie dedicate; asse V (secondario) no.
TOPOLOGIES["main_with_dedicated"] = TopologyConfig(
    name="main_with_dedicated",
    west=_seg(lanes_inbound=4, left_turn_lane=True, right_turn_lane=True),
    east=_seg(lanes_inbound=4, left_turn_lane=True, right_turn_lane=True),
    north=_seg(lanes_inbound=2),
    south=_seg(lanes_inbound=2),
)

# ── 12. Incrocio spostato a sinistra (offset centro) ──────────────────
# Simula un incrocio decentrato, utile per strade non simmetriche.
TOPOLOGIES["offset_left"] = TopologyConfig(
    name="offset_left",
    center_col_offset=-10,  # incrocio spostato 10 celle a ovest
)

# ── 13. T-junction con corsia dedicata (asse principale con dedicate) ─
TOPOLOGIES["T_no_north_dedicated"] = TopologyConfig(
    name="T_no_north_dedicated",
    north=_seg(enabled=False),
    west=_seg(left_turn_lane=True),
    east=_seg(right_turn_lane=True),
    south=_seg(lanes_inbound=2),
)

# ── 14. Incrocio "a stella" ridotto: solo 3 bracci asimmetrici ────────
# Nord e sud diversi, est disabilitato, ovest con piu' corsie
TOPOLOGIES["star_3arm"] = TopologyConfig(
    name="star_3arm",
    east=_seg(enabled=False),
    west=_seg(lanes_inbound=3, left_turn_lane=True),
    north=_seg(lanes_inbound=2),
    south=_seg(lanes_inbound=2),
)


# ── 15. + con slip lanes (bypass diagonali) ───────────────────────────
TOPOLOGIES["slip_standard"] = TopologyConfig(
    name               = "slip_standard",
    slip_lanes_enabled = True,
    slip_len           = 5,
    slip_exclusive     = True,
)

# ── 16. + con slip lanes NON esclusive (corsia dx usata da tutti) ───
TOPOLOGIES["slip_shared"] = TopologyConfig(
    name               = "slip_shared",
    slip_lanes_enabled = True,
    slip_len           = 5,
    slip_exclusive     = False,
)

# ── 17. Boulevard con slip lanes + corsie dedicate sx ──────────────
TOPOLOGIES["slip_dedicated"] = TopologyConfig(
    name               = "slip_dedicated",
    west               = _seg(left_turn_lane=True),
    east               = _seg(left_turn_lane=True),
    north              = _seg(left_turn_lane=True),
    south              = _seg(left_turn_lane=True),
    slip_lanes_enabled = True,
    slip_len           = 6,
    slip_exclusive     = True,
)

# ── 18. T-junction con slip lane (sul braccio presente) ────────────
TOPOLOGIES["T_slip"] = TopologyConfig(
    name               = "T_slip",
    north              = _seg(enabled=False),
    slip_lanes_enabled = True,
    slip_len           = 5,
    slip_exclusive     = True,
)


def list_topologies() -> list:
    """Ritorna la lista dei nomi delle topologie disponibili."""
    return list(TOPOLOGIES.keys())
