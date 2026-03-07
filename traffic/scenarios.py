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
import copy


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
