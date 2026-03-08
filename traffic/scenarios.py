"""
scenarios.py — Configurazioni preset pronte all'uso.

Ogni scenario e' una SimConfig completa con parametri calibrati
per evidenziare un fenomeno specifico del traffico.

Utilizzo:
    from traffic import SCENARIOS
    cfg = SCENARIOS["heavy_traffic"]

    # oppure
    from traffic import SCENARIOS
    for name, cfg in SCENARIOS.items():
        print(name, cfg.summary())
"""

from __future__ import annotations
from .config import (
    SimConfig, LightPolicy, ManualObstacle,
    PersonalityProfile, DEFAULT_PROFILES,
)
from .topology import TopologyConfig, RoadSegment, TOPOLOGIES
import copy

def _seg(**kw) -> RoadSegment:
    return RoadSegment(**kw)


def list_scenarios() -> list:
    """Ritorna la lista dei nomi degli scenari disponibili."""
    return list(SCENARIOS.keys())


# ── Helper per clonare profili e modificarli ──────────────────────────

def _profiles(**overrides) -> list:
    """
    Clona i profili default e applica le modifiche indicate.
    overrides: nome_profilo -> dict di campi da sovrascrivere.
    Esempio: _profiles(RUSHER=dict(spawn_weight=30))
    """
    profs = [copy.copy(p) for p in DEFAULT_PROFILES]
    for name, changes in overrides.items():
        for p in profs:
            if p.name == name:
                for k, v in changes.items():
                    setattr(p, k, v)
    return profs


# =====================================================================
# SCENARI
# =====================================================================

SCENARIOS: dict[str, SimConfig] = {}


# ── 1. Default ────────────────────────────────────────────────────────
SCENARIOS["default"] = SimConfig(
    output_file="out_default.gif",
)


# ── 2. Traffico intenso ───────────────────────────────────────────────
SCENARIOS["heavy_traffic"] = SimConfig(
    output_file       = "out_heavy_traffic.gif",
    spawn_prob        = 0.55,        # spawn molto aggressivo
    density_cap       = 0.90,        # lascia accumulare piu' traffico
    light_green_h     = 35,
    light_green_v     = 35,
    light_yellow      = 4,
    steps             = 700,
)


# ── 3. Incidenti frequenti e persistenti ──────────────────────────────
SCENARIOS["accident_prone"] = SimConfig(
    output_file       = "out_accident_prone.gif",
    accident_prob     = 0.003,       # x6 rispetto al default
    accident_dur_min  = 40,          # incidenti lunghi
    accident_dur_max  = 120,
    spawn_prob        = 0.35,
    steps             = 600,
)


# ── 4. Ostacoli manuali (cantieri fissi) ──────────────────────────────
# Due corsie bloccate permanentemente su assi opposti
SCENARIOS["roadworks"] = SimConfig(
    output_file       = "out_roadworks.gif",
    spawn_prob        = 0.38,
    accident_prob     = 0.0002,
    manual_obstacles  = [
        ManualObstacle(row=46, col=20, duration=-1, label="cantiere_H"),
        ManualObstacle(row=46, col=21, duration=-1, label="cantiere_H"),
        ManualObstacle(row=46, col=22, duration=-1, label="cantiere_H"),
        ManualObstacle(row=20, col=46, duration=-1, label="cantiere_V"),
        ManualObstacle(row=21, col=46, duration=-1, label="cantiere_V"),
    ],
    steps             = 600,
)


# ── 5. Guidatori aggressivi / frettolosi ──────────────────────────────
SCENARIOS["aggressive_drivers"] = SimConfig(
    output_file       = "out_aggressive.gif",
    personalities     = _profiles(
        CAUTIOUS   = dict(spawn_weight=3),
        NORMAL     = dict(spawn_weight=30),
        AGGRESSIVE = dict(spawn_weight=42, run_red_prob=0.40),
        RUSHER     = dict(spawn_weight=25, run_red_prob=0.75, max_speed=6),
    ),
    spawn_prob        = 0.35,
    accident_prob     = 0.0012,      # piu' incidenti per guida pericolosa
    steps             = 600,
)


# ── 6. Semaforo adattivo ──────────────────────────────────────────────
SCENARIOS["adaptive_light"] = SimConfig(
    output_file              = "out_adaptive_light.gif",
    light_policy             = LightPolicy.ADAPTIVE,
    light_min_green          = 12,
    light_max_green          = 80,
    adaptive_check_interval  = 8,
    # Traffico asimmetrico: molto piu' traffico verso EST
    spawn_prob_east          = 0.55,
    spawn_prob_west          = 0.20,
    spawn_prob_south         = 0.30,
    spawn_prob_north         = 0.30,
    steps                    = 600,
)


# ── 7. Nessun semaforo (incrocio non regolato) ────────────────────────
SCENARIOS["no_lights"] = SimConfig(
    output_file   = "out_no_lights.gif",
    light_policy  = LightPolicy.NO_LIGHT,
    spawn_prob    = 0.25,            # spawn basso per non saturare subito
    accident_prob = 0.0008,          # piu' incidenti senza regole
    steps         = 500,
    num_lanes     = 5,
    max_speed     = 5,
)


# ── 8. Corsia preferenziale verticale ─────────────────────────────────
# Verde lungo sull'asse V, rosso lungo sull'asse H
SCENARIOS["priority_vertical"] = SimConfig(
    output_file   = "out_priority_v.gif",
    light_policy  = LightPolicy.FIXED,
    light_green_v = 70,              # asse V ha quasi sempre il verde
    light_green_h = 20,
    light_yellow  = 5,
    spawn_prob_south = 0.50,
    spawn_prob_north = 0.50,
    spawn_prob_east  = 0.25,
    spawn_prob_west  = 0.25,
    steps         = 600,
)


# ── 9. Traffico basso e fluido ────────────────────────────────────────
SCENARIOS["light_traffic"] = SimConfig(
    output_file   = "out_light.gif",
    spawn_prob    = 0.12,
    accident_prob = 0.0001,
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=20),
        NORMAL     = dict(spawn_weight=65),
        AGGRESSIVE = dict(spawn_weight=12),
        RUSHER     = dict(spawn_weight=3),
    ),
    steps         = 400,
)


# ── 10. Scenario incidente prefissato + traffico alto ────────────────
# Un incidente di lunga durata viene piazzato sulla corsia principale
SCENARIOS["fixed_incident"] = SimConfig(
    output_file      = "out_fixed_incident.gif",
    spawn_prob       = 0.40,
    accident_prob    = 0.0001,       # quasi no incidenti spontanei
    manual_obstacles = [
        ManualObstacle(row=46, col=55, duration=300, label="incidente_principale"),
        ManualObstacle(row=47, col=55, duration=300, label="incidente_secondario"),
    ],
    steps            = 600,
)


# ── 11. Precedenza rispettata (guidatori prudenti, parametri stretti) ─
# Evidenzia le code generate dalle svolta a sinistra quando la
# precedenza viene rispettata quasi sempre. Utile per osservare
# come la regola rallenta il flusso delle svolte ma riduce gli incidenti.
SCENARIOS["row_strict"] = SimConfig(
    output_file             = "out_row_strict.gif",
    row_enabled             = True,
    row_lookahead           = 12,        # finestra ampia: inizia a cedere presto
    row_oncoming_check      = 18,        # scansiona lontano
    row_yield_gap           = 6,         # cede anche se il traffico e' abbastanza lontano
    row_frustration_factor  = 0.005,     # la frustrazione conta poco
    # Tutti guidatori prudenti: quasi nessuno ignora la precedenza
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=30, ignore_row_prob=0.01),
        NORMAL     = dict(spawn_weight=55, ignore_row_prob=0.05),
        AGGRESSIVE = dict(spawn_weight=12, ignore_row_prob=0.15),
        RUSHER     = dict(spawn_weight=3,  ignore_row_prob=0.25),
    ),
    spawn_prob      = 0.38,
    accident_prob   = 0.0002,
    steps           = 600,
)


# ── 12. Precedenza ignorata (guidatori aggressivi + alta frustrazione) ─
# Scenario caotico: la maggioranza dei guidatori ignora la precedenza,
# specialmente quando frustrati. Genera molti piu' incidenti e
# un flusso imprevedibile all'incrocio.
SCENARIOS["row_chaos"] = SimConfig(
    output_file             = "out_row_chaos.gif",
    row_enabled             = True,
    row_lookahead           = 6,         # finestra corta: si accorge tardi
    row_oncoming_check      = 8,
    row_yield_gap           = 2,         # cede solo se il traffico e' vicinissimo
    row_frustration_factor  = 0.06,      # la frustrazione pesa molto sulla decisione
    # Guidatori prevalentemente aggressivi/frettolosi
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=5,  ignore_row_prob=0.05),
        NORMAL     = dict(spawn_weight=30, ignore_row_prob=0.20),
        AGGRESSIVE = dict(spawn_weight=40, ignore_row_prob=0.60),
        RUSHER     = dict(spawn_weight=25, ignore_row_prob=0.85),
    ),
    spawn_prob      = 0.42,
    accident_prob   = 0.0015,    # piu' incidenti per la guida caotica
    steps           = 600,
)


# ── 13. Confronto: precedenza ON vs OFF (stesso traffico) ─────────────
# Versione senza semaforo e SENZA sistema di precedenza:
# permette di confrontare visivamente col default per misurare
# l'impatto della regola sulla fluidita' e sugli incidenti.
SCENARIOS["row_disabled"] = SimConfig(
    output_file    = "out_row_disabled.gif",
    row_enabled    = False,          # precendenza completamente disabilitata
    light_policy   = LightPolicy.FIXED,
    spawn_prob     = 0.38,
    accident_prob  = 0.0006,
    steps          = 600,
)


# =====================================================================
# SCENARI TOPOLOGIA
# =====================================================================

# ── 14. T-junction: nessuna strada verso nord ───────────────────────
SCENARIOS["T_no_north"] = SimConfig(
    output_file = "out_T_no_north.gif",
    topology    = TOPOLOGIES["T_no_north"],
    spawn_prob  = 0.35,
    steps       = 500,
    light_green_h = 40,
    light_green_v = 25,   # asse V ha meno traffico
)

# ── 15. T-junction: strada che termina a est (solo 3 bracci) ────────
SCENARIOS["T_no_east"] = SimConfig(
    output_file = "out_T_no_east.gif",
    topology    = TOPOLOGIES["T_no_east"],
    spawn_prob  = 0.35,
    steps       = 500,
)

# ── 16. Incrocio con corsie dedicate svolta sinistra ───────────────
# Richiede num_lanes >= 2 perche' la corsia più a sinistra e' riservata.
SCENARIOS["dedicated_left"] = SimConfig(
    output_file = "out_dedicated_left.gif",
    num_lanes   = 3,
    topology    = TOPOLOGIES["dedicated_left_all"],
    spawn_prob  = 0.38,
    steps       = 600,
    row_enabled = True,
    row_lookahead = 10,
)

# ── 17. Corsie dedicate sia sinistra che destra (richiede 3+ corsie) ─
SCENARIOS["dedicated_both"] = SimConfig(
    output_file = "out_dedicated_both.gif",
    num_lanes   = 4,
    topology    = TOPOLOGIES["dedicated_both_all"],
    spawn_prob  = 0.40,
    steps       = 600,
    row_enabled = True,
)

# ── 18. Strada principale (H, 4 corsie) + secondaria (V, 2 corsie) ──
SCENARIOS["asymmetric_main"] = SimConfig(
    output_file   = "out_asymmetric_main.gif",
    num_lanes     = 4,   # default, ovverrideato dalla topologia per V
    topology      = TOPOLOGIES["asymmetric_H_main"],
    spawn_prob    = 0.38,
    # Spawn asimmetrico: più traffico sull'asse principale
    spawn_prob_east  = 0.45,  # ← su asse principale H
    spawn_prob_west  = 0.45,  # → su asse principale H  (wait, actually east label = west segment)
    light_green_h    = 55,    # verde più lungo per l'asse H (principale)
    light_green_v    = 25,
    steps            = 600,
)

# ── 19. Incrocio spostato a sinistra ─────────────────────────────
SCENARIOS["offset_intersection"] = SimConfig(
    output_file = "out_offset.gif",
    topology    = TOPOLOGIES["offset_left"],
    spawn_prob  = 0.32,
    steps       = 500,
)

# ── 20. T-junction con corsie dedicate + spawn asimmetrico ─────────
SCENARIOS["T_dedicated"] = SimConfig(
    output_file = "out_T_dedicated.gif",
    num_lanes   = 3,
    topology    = TopologyConfig(
        name  = "T_dedicated_custom",
        north = _seg(enabled=False),
        west  = _seg(lanes_inbound=3, left_turn_lane=True,  label="main_in"),
        east  = _seg(lanes_inbound=3, right_turn_lane=True, label="main_out"),
        south = _seg(lanes_inbound=2, label="side"),
    ),
    spawn_prob       = 0.38,
    spawn_prob_east  = 0.50,  # traffico abbondante in entrata
    light_green_h    = 50,
    light_green_v    = 20,
    steps            = 600,
    row_enabled      = True,
)

# ── 21. Incrocio completo stile boulevard ─────────────────────────
# 4 corsie per senso su asse H, corsie dedicate svolta, asse V secondario
SCENARIOS["boulevard"] = SimConfig(
    output_file = "out_boulevard.gif",
    num_lanes   = 4,
    topology    = TopologyConfig(
        name  = "boulevard",
        west  = _seg(lanes_inbound=4, left_turn_lane=True,  right_turn_lane=True),
        east  = _seg(lanes_inbound=4, left_turn_lane=True,  right_turn_lane=True),
        north = _seg(lanes_inbound=2, left_turn_lane=False, right_turn_lane=False),
        south = _seg(lanes_inbound=2),
    ),
    spawn_prob_east  = 0.50,
    spawn_prob_west  = 0.50,
    spawn_prob_south = 0.20,
    spawn_prob_north = 0.20,
    light_green_h    = 60,
    light_green_v    = 20,
    accident_prob    = 0.00030,
    row_enabled      = True,
    steps            = 600,
)


# =====================================================================
# SCENARI SLIP LANES (bypass svolta destra)
# =====================================================================

# ── 22. Incrocio standard con slip lanes ───────────────────────────
SCENARIOS["slip_lanes"] = SimConfig(
    output_file        = "out_slip_lanes.gif",
    topology           = TOPOLOGIES["slip_standard"],
    spawn_prob         = 0.35,
    steps              = 600,
    light_green_h      = 40,
    light_green_v      = 40,
    row_enabled        = True,
)

# ── 23. Slip lanes con corsie condivise (non esclusive) ─────────────
# La corsia dx non e' riservata: anche auto dritto/sx possono starci
SCENARIOS["slip_shared"] = SimConfig(
    output_file        = "out_slip_shared.gif",
    topology           = TOPOLOGIES["slip_shared"],
    spawn_prob         = 0.35,
    steps              = 600,
)

# ── 24. Boulevard con slip lanes + corsie sx dedicate ──────────────
# Scenario ricco: asse principale con corsia sx dedicata E bypass dx
SCENARIOS["slip_boulevard"] = SimConfig(
    output_file        = "out_slip_boulevard.gif",
    num_lanes          = 3,
    topology           = TOPOLOGIES["slip_dedicated"],
    spawn_prob         = 0.40,
    light_green_h      = 50,
    light_green_v      = 30,
    row_enabled        = True,
    steps              = 600,
)

# ── 25. T-junction con slip lanes ───────────────────────────────
SCENARIOS["T_slip"] = SimConfig(
    output_file        = "out_T_slip.gif",
    topology           = TOPOLOGIES["T_slip"],
    spawn_prob         = 0.35,
    steps              = 500,
)

# ── 26. Confronto slip_lanes vs standard (stesso traffico, no slip) ──
# Uguale a slip_lanes ma senza bypass: utile per misurare il guadagno
SCENARIOS["slip_vs_noSlip"] = SimConfig(
    output_file        = "out_no_slip_comparison.gif",
    topology           = TopologyConfig(name="plus_noslip"),  # niente slip
    spawn_prob         = 0.35,
    steps              = 600,
    light_green_h      = 40,
    light_green_v      = 40,
)