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
import copy

from .core.config import (
    SimConfig, PersonalityProfile, DEFAULT_PROFILES,
    VehicleTypeWeights, BusStop, ManualObstacle,
)
from .core.types import LightPolicy
from .world.topology import TopologyConfig, RoadSegment, TOPOLOGIES


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
    spawn_prob        = 0.55,
    density_cap       = 0.90,
    light_green_h     = 35,
    light_green_v     = 35,
    light_yellow      = 4,
    steps             = 700,
)


# ── 3. Incidenti frequenti e persistenti ──────────────────────────────
SCENARIOS["accident_prone"] = SimConfig(
    output_file       = "out_accident_prone.gif",
    accident_prob     = 0.003,
    accident_dur_min  = 40,
    accident_dur_max  = 120,
    spawn_prob        = 0.35,
    steps             = 600,
)


# ── 4. Ostacoli manuali (cantieri fissi) ──────────────────────────────
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
    accident_prob     = 0.0012,
    steps             = 600,
)


# ── 6. Semaforo adattivo ──────────────────────────────────────────────
SCENARIOS["adaptive_light"] = SimConfig(
    output_file              = "out_adaptive_light.gif",
    light_policy             = LightPolicy.ADAPTIVE,
    light_min_green          = 12,
    light_max_green          = 80,
    adaptive_check_interval  = 8,
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
    spawn_prob    = 0.25,
    accident_prob = 0.0008,
    steps         = 500,
    num_lanes     = 5,
    max_speed     = 5,
)


# ── 8. Corsia preferenziale verticale ─────────────────────────────────
SCENARIOS["priority_vertical"] = SimConfig(
    output_file      = "out_priority_v.gif",
    light_policy     = LightPolicy.FIXED,
    light_green_v    = 70,
    light_green_h    = 20,
    light_yellow     = 5,
    spawn_prob_south = 0.50,
    spawn_prob_north = 0.50,
    spawn_prob_east  = 0.25,
    spawn_prob_west  = 0.25,
    steps            = 600,
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
SCENARIOS["fixed_incident"] = SimConfig(
    output_file      = "out_fixed_incident.gif",
    spawn_prob       = 0.40,
    accident_prob    = 0.0001,
    manual_obstacles = [
        ManualObstacle(row=46, col=55, duration=300, label="incidente_principale"),
        ManualObstacle(row=47, col=55, duration=300, label="incidente_secondario"),
    ],
    steps            = 600,
)


# ── 11-15. Scenari ROW ────────────────────────────────────────────────
SCENARIOS["row_strict"] = SimConfig(
    output_file             = "out_row_strict.gif",
    row_enabled             = True,
    row_lookahead           = 12,
    row_oncoming_check      = 18,
    row_yield_gap           = 6,
    row_frustration_factor  = 0.005,
    row_distance_weight     = 0.1,
    row_gap_weight          = 0.8,
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=30, ignore_row_prob=0.01),
        NORMAL     = dict(spawn_weight=55, ignore_row_prob=0.05),
        AGGRESSIVE = dict(spawn_weight=12, ignore_row_prob=0.15),
        RUSHER     = dict(spawn_weight=3,  ignore_row_prob=0.25),
    ),
    spawn_prob    = 0.38,
    accident_prob = 0.0002,
    steps         = 600,
)

SCENARIOS["row_chaos"] = SimConfig(
    output_file             = "out_row_chaos.gif",
    row_enabled             = True,
    row_lookahead           = 6,
    row_oncoming_check      = 8,
    row_yield_gap           = 2,
    row_frustration_factor  = 0.06,
    row_distance_weight     = 0.5,
    row_gap_weight          = 0.2,
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=5,  ignore_row_prob=0.05),
        NORMAL     = dict(spawn_weight=30, ignore_row_prob=0.20),
        AGGRESSIVE = dict(spawn_weight=40, ignore_row_prob=0.60),
        RUSHER     = dict(spawn_weight=25, ignore_row_prob=0.85),
    ),
    spawn_prob    = 0.42,
    accident_prob = 0.0015,
    steps         = 600,
)

SCENARIOS["row_disabled"] = SimConfig(
    output_file   = "out_row_disabled.gif",
    row_enabled   = False,
    light_policy  = LightPolicy.FIXED,
    spawn_prob    = 0.38,
    accident_prob = 0.0006,
    steps         = 600,
)

SCENARIOS["row_distance_based"] = SimConfig(
    output_file             = "out_row_distance.gif",
    row_enabled             = True,
    row_lookahead           = 12,
    row_oncoming_check      = 15,
    row_yield_gap           = 4,
    row_frustration_factor  = 0.04,
    row_distance_weight     = 0.4,
    row_gap_weight          = 0.6,
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=10, ignore_row_prob=0.05),
        NORMAL     = dict(spawn_weight=40, ignore_row_prob=0.15),
        AGGRESSIVE = dict(spawn_weight=30, ignore_row_prob=0.50),
        RUSHER     = dict(spawn_weight=20, ignore_row_prob=0.80),
    ),
    spawn_prob    = 0.40,
    accident_prob = 0.0010,
    steps         = 600,
)

SCENARIOS["row_extreme"] = SimConfig(
    output_file             = "out_row_extreme.gif",
    row_enabled             = True,
    row_lookahead           = 8,
    row_oncoming_check      = 10,
    row_yield_gap           = 2,
    row_frustration_factor  = 0.08,
    row_distance_weight     = 0.7,
    row_gap_weight          = 0.1,
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=5,  ignore_row_prob=0.10),
        NORMAL     = dict(spawn_weight=20, ignore_row_prob=0.30),
        AGGRESSIVE = dict(spawn_weight=40, ignore_row_prob=0.75),
        RUSHER     = dict(spawn_weight=35, ignore_row_prob=0.95),
    ),
    spawn_prob    = 0.45,
    accident_prob = 0.0020,
    steps         = 600,
)


# =====================================================================
# SCENARI TOPOLOGIA
# =====================================================================

_RB_LANES = 3  # corsie anello (size = 2*N+3)
SCENARIOS["roundabout"] = SimConfig(
    output_file  = "out_roundabout.gif",
    num_lanes    = _RB_LANES,      # corsie in entrata/uscita (6x6 con 3)
    topology     = TopologyConfig(
        name="roundabout_custom",
        roundabout=True,
        roundabout_lanes=_RB_LANES,
        row_yield_to="left",
    ),
    light_policy = LightPolicy.NO_LIGHT,
    row_enabled  = True,
    row_lookahead = 10,
    spawn_prob   = 0.35,
    steps        = 600,
)

SCENARIOS["T_no_north"] = SimConfig(
    output_file   = "out_T_no_north.gif",
    topology      = TOPOLOGIES["T_no_north"],
    spawn_prob    = 0.35,
    steps         = 500,
    light_green_h = 40,
    light_green_v = 25,
)

SCENARIOS["T_no_east"] = SimConfig(
    output_file = "out_T_no_east.gif",
    topology    = TOPOLOGIES["T_no_east"],
    spawn_prob  = 0.35,
    steps       = 500,
)

SCENARIOS["dedicated_left"] = SimConfig(
    output_file   = "out_dedicated_left.gif",
    num_lanes     = 3,
    topology      = TOPOLOGIES["dedicated_left_all"],
    spawn_prob    = 0.38,
    steps         = 600,
    row_enabled   = True,
    row_lookahead = 10,
)

SCENARIOS["dedicated_both"] = SimConfig(
    output_file = "out_dedicated_both.gif",
    num_lanes   = 4,
    topology    = TOPOLOGIES["dedicated_both_all"],
    spawn_prob  = 0.40,
    steps       = 600,
    row_enabled = True,
)

SCENARIOS["asymmetric_main"] = SimConfig(
    output_file      = "out_asymmetric_main.gif",
    num_lanes        = 4,
    topology         = TOPOLOGIES["asymmetric_H_main"],
    spawn_prob       = 0.38,
    spawn_prob_east  = 0.45,
    spawn_prob_west  = 0.45,
    light_green_h    = 55,
    light_green_v    = 25,
    steps            = 600,
)

SCENARIOS["offset_intersection"] = SimConfig(
    output_file = "out_offset.gif",
    topology    = TOPOLOGIES["offset_left"],
    spawn_prob  = 0.32,
    steps       = 500,
)

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
    spawn_prob_east  = 0.50,
    light_green_h    = 50,
    light_green_v    = 20,
    steps            = 600,
    row_enabled      = True,
)

SCENARIOS["boulevard"] = SimConfig(
    output_file = "out_boulevard.gif",
    num_lanes   = 4,
    topology    = TopologyConfig(
        name  = "boulevard",
        west  = _seg(lanes_inbound=4, left_turn_lane=True,  right_turn_lane=True),
        east  = _seg(lanes_inbound=4, left_turn_lane=True,  right_turn_lane=True),
        north = _seg(lanes_inbound=2),
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
# SCENARI SLIP LANES
# =====================================================================

SCENARIOS["slip_lanes"] = SimConfig(
    output_file   = "out_slip_lanes.gif",
    topology      = TOPOLOGIES["slip_standard"],
    spawn_prob    = 0.35,
    steps         = 600,
    light_green_h = 40,
    light_green_v = 40,
    row_enabled   = True,
)

SCENARIOS["slip_shared"] = SimConfig(
    output_file = "out_slip_shared.gif",
    topology    = TOPOLOGIES["slip_shared"],
    spawn_prob  = 0.35,
    steps       = 600,
)

SCENARIOS["slip_boulevard"] = SimConfig(
    output_file   = "out_slip_boulevard.gif",
    num_lanes     = 3,
    topology      = TOPOLOGIES["slip_dedicated"],
    spawn_prob    = 0.40,
    light_green_h = 50,
    light_green_v = 30,
    row_enabled   = True,
    steps         = 600,
)

SCENARIOS["T_slip"] = SimConfig(
    output_file = "out_T_slip.gif",
    topology    = TOPOLOGIES["T_slip"],
    spawn_prob  = 0.35,
    steps       = 500,
)

SCENARIOS["slip_vs_noSlip"] = SimConfig(
    output_file   = "out_no_slip_comparison.gif",
    topology      = TopologyConfig(name="plus_noslip"),
    spawn_prob    = 0.35,
    steps         = 600,
    light_green_h = 40,
    light_green_v = 40,
)


# =====================================================================
# SCENARI v3 — IDM · MOBIL · VEICOLI ETEROGENEI · EMERGENZE · PLATOON
# =====================================================================

SCENARIOS["idm_standard"] = SimConfig(
    output_file     = "out_idm_standard.gif",
    use_idm         = True,
    use_mobil       = True,
    spawn_prob      = 0.32,
    steps           = 600,
    accident_prob   = 0.00040,
    vehicle_weights = VehicleTypeWeights(
        motorcycle = 10,
        car        = 68,
        van        = 14,
        bus        = 6,
        emergency  = 2,
    ),
)

SCENARIOS["idm_vs_nasch"] = SimConfig(
    output_file     = "out_idm_vs_nasch.gif",
    use_idm         = False,
    use_mobil       = False,
    spawn_prob      = 0.32,
    steps           = 600,
    vehicle_weights = VehicleTypeWeights(
        motorcycle = 0,
        car        = 100,
        van        = 0,
        bus        = 0,
        emergency  = 0,
    ),
)

SCENARIOS["mixed_vehicles"] = SimConfig(
    output_file     = "out_mixed_vehicles.gif",
    use_idm         = True,
    use_mobil       = True,
    num_lanes       = 3,
    max_speed       = 5,
    spawn_prob      = 0.30,
    steps           = 600,
    accident_prob   = 0.00055,
    vehicle_weights = VehicleTypeWeights(
        motorcycle = 15,
        car        = 55,
        van        = 18,
        bus        = 10,
        emergency  = 2,
    ),
)

SCENARIOS["motorcycle_fleet"] = SimConfig(
    output_file     = "out_motorcycle_fleet.gif",
    use_idm         = True,
    use_mobil       = True,
    max_speed       = 5,
    spawn_prob      = 0.30,
    steps           = 500,
    accident_prob   = 0.00060,
    vehicle_weights = VehicleTypeWeights(
        motorcycle = 70,
        car        = 25,
        van        = 3,
        bus        = 0,
        emergency  = 2,
    ),
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=8),
        NORMAL     = dict(spawn_weight=45),
        AGGRESSIVE = dict(spawn_weight=35),
        RUSHER     = dict(spawn_weight=12),
    ),
)

SCENARIOS["heavy_vehicles"] = SimConfig(
    output_file     = "out_heavy_vehicles.gif",
    use_idm         = True,
    use_mobil       = True,
    num_lanes       = 3,
    max_speed       = 3,
    spawn_prob      = 0.28,
    steps           = 600,
    accident_prob   = 0.00035,
    light_policy    = LightPolicy.ADAPTIVE,
    light_min_green = 15,
    light_max_green = 80,
    vehicle_weights = VehicleTypeWeights(
        motorcycle = 2,
        car        = 30,
        van        = 40,
        bus        = 26,
        emergency  = 2,
    ),
)


# =====================================================================
# SCENARI EMERGENZA
# =====================================================================

SCENARIOS["emergency_frequent"] = SimConfig(
    output_file              = "out_emergency_frequent.gif",
    use_idm                  = True,
    use_mobil                = True,
    spawn_prob               = 0.30,
    steps                    = 600,
    accident_prob            = 0.00050,
    emergency_preempt_dist   = 20,
    emergency_pull_over_dist = 14,
    vehicle_weights          = VehicleTypeWeights(
        motorcycle = 5,
        car        = 55,
        van        = 20,
        bus        = 5,
        emergency  = 15,
    ),
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=20),
        NORMAL     = dict(spawn_weight=60),
        AGGRESSIVE = dict(spawn_weight=15),
        RUSHER     = dict(spawn_weight=5),
    ),
)

SCENARIOS["emergency_heavy"] = SimConfig(
    output_file              = "out_emergency_heavy.gif",
    use_idm                  = True,
    use_mobil                = True,
    spawn_prob               = 0.50,
    density_cap              = 0.85,
    steps                    = 600,
    accident_prob            = 0.00030,
    emergency_preempt_dist   = 18,
    emergency_pull_over_dist = 12,
    light_green_h            = 40,
    light_green_v            = 40,
    vehicle_weights          = VehicleTypeWeights(
        motorcycle = 8,
        car        = 63,
        van        = 16,
        bus        = 5,
        emergency  = 8,
    ),
)

SCENARIOS["emergency_no_preempt"] = SimConfig(
    output_file              = "out_emergency_no_preempt.gif",
    use_idm                  = True,
    use_mobil                = True,
    spawn_prob               = 0.30,
    steps                    = 600,
    emergency_preempt_dist   = 0,
    emergency_pull_over_dist = 0,
    vehicle_weights          = VehicleTypeWeights(
        motorcycle = 5,
        car        = 55,
        van        = 20,
        bus        = 5,
        emergency  = 15,
    ),
)


# =====================================================================
# SCENARI BUS
# =====================================================================

SCENARIOS["bus_route"] = SimConfig(
    output_file     = "out_bus_route.gif",
    use_idm         = True,
    use_mobil       = True,
    num_lanes       = 3,
    spawn_prob      = 0.32,
    steps           = 600,
    accident_prob   = 0.00025,
    vehicle_weights = VehicleTypeWeights(
        motorcycle = 5,
        car        = 60,
        van        = 15,
        bus        = 18,
        emergency  = 2,
    ),
    bus_stops = [
        BusStop(row=45, col=25, dwell_time=22, label="Fermata_W1"),
        BusStop(row=45, col=65, dwell_time=22, label="Fermata_E1"),
        BusStop(row=25, col=45, dwell_time=20, label="Fermata_N1"),
        BusStop(row=65, col=45, dwell_time=20, label="Fermata_S1"),
    ],
)

SCENARIOS["bus_express"] = SimConfig(
    output_file     = "out_bus_express.gif",
    use_idm         = True,
    use_mobil       = True,
    num_lanes       = 2,
    spawn_prob      = 0.28,
    steps           = 500,
    vehicle_weights = VehicleTypeWeights(
        motorcycle = 5,
        car        = 65,
        van        = 15,
        bus        = 13,
        emergency  = 2,
    ),
    bus_stops = [
        BusStop(row=45, col=20, dwell_time=30, label="Fermata_W_express"),
        BusStop(row=45, col=70, dwell_time=30, label="Fermata_E_express"),
    ],
)

SCENARIOS["bus_and_emergency"] = SimConfig(
    output_file              = "out_bus_emergency.gif",
    use_idm                  = True,
    use_mobil                = True,
    num_lanes                = 3,
    spawn_prob               = 0.30,
    steps                    = 600,
    emergency_preempt_dist   = 20,
    emergency_pull_over_dist = 12,
    vehicle_weights          = VehicleTypeWeights(
        motorcycle = 5,
        car        = 55,
        van        = 16,
        bus        = 14,
        emergency  = 10,
    ),
    bus_stops = [
        BusStop(row=45, col=25, dwell_time=20, label="Fermata_W"),
        BusStop(row=45, col=65, dwell_time=20, label="Fermata_E"),
        BusStop(row=25, col=45, dwell_time=18, label="Fermata_N"),
        BusStop(row=65, col=45, dwell_time=18, label="Fermata_S"),
    ],
)


# =====================================================================
# SCENARI PLATOONING
# =====================================================================

SCENARIOS["platooning_base"] = SimConfig(
    output_file        = "out_platooning_base.gif",
    use_idm            = True,
    use_mobil          = True,
    platooning_enabled = True,
    platoon_min_speed  = 1.5,
    platoon_gap        = 1,
    platoon_max_size   = 5,
    platoon_form_prob  = 0.04,
    spawn_prob         = 0.30,
    steps              = 600,
    accident_prob      = 0.00020,
    vehicle_weights    = VehicleTypeWeights(
        motorcycle = 8,
        car        = 72,
        van        = 16,
        bus        = 2,
        emergency  = 2,
    ),
)

SCENARIOS["platooning_heavy"] = SimConfig(
    output_file        = "out_platooning_heavy.gif",
    use_idm            = True,
    use_mobil          = True,
    platooning_enabled = True,
    platoon_min_speed  = 1.0,
    platoon_gap        = 1,
    platoon_max_size   = 7,
    platoon_form_prob  = 0.08,
    spawn_prob         = 0.35,
    steps              = 600,
    accident_prob      = 0.00015,
    vehicle_weights    = VehicleTypeWeights(
        motorcycle = 10,
        car        = 78,
        van        = 10,
        bus        = 0,
        emergency  = 2,
    ),
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=20),
        NORMAL     = dict(spawn_weight=62),
        AGGRESSIVE = dict(spawn_weight=14),
        RUSHER     = dict(spawn_weight=4),
    ),
)

SCENARIOS["platooning_off"] = SimConfig(
    output_file        = "out_platooning_off.gif",
    use_idm            = True,
    use_mobil          = True,
    platooning_enabled = False,
    spawn_prob         = 0.30,
    steps              = 600,
    vehicle_weights    = VehicleTypeWeights(
        motorcycle = 8,
        car        = 72,
        van        = 16,
        bus        = 2,
        emergency  = 2,
    ),
)


# =====================================================================
# SCENARI COMPLESSI
# =====================================================================

SCENARIOS["urban_realistic"] = SimConfig(
    output_file              = "out_urban_realistic.gif",
    use_idm                  = True,
    use_mobil                = True,
    platooning_enabled       = False,
    num_lanes                = 3,
    max_speed                = 4,
    spawn_prob               = 0.33,
    steps                    = 700,
    accident_prob            = 0.00040,
    light_policy             = LightPolicy.ADAPTIVE,
    light_min_green          = 15,
    light_max_green          = 70,
    emergency_preempt_dist   = 18,
    emergency_pull_over_dist = 12,
    vehicle_weights          = VehicleTypeWeights(
        motorcycle = 12,
        car        = 58,
        van        = 17,
        bus        = 9,
        emergency  = 4,
    ),
    bus_stops = [
        BusStop(row=45, col=22, dwell_time=20, label="Stop_W"),
        BusStop(row=45, col=68, dwell_time=20, label="Stop_E"),
        BusStop(row=22, col=45, dwell_time=18, label="Stop_N"),
        BusStop(row=68, col=45, dwell_time=18, label="Stop_S"),
    ],
    row_enabled   = True,
    row_lookahead = 9,
)

SCENARIOS["highway_platoon"] = SimConfig(
    output_file        = "out_highway_platoon.gif",
    use_idm            = True,
    use_mobil          = True,
    platooning_enabled = True,
    platoon_min_speed  = 2.5,
    platoon_gap        = 1,
    platoon_max_size   = 6,
    platoon_form_prob  = 0.05,
    grid_size          = 90,
    num_lanes          = 2,
    max_speed          = 6,
    spawn_prob         = 0.25,
    steps              = 600,
    accident_prob      = 0.00020,
    light_green_h      = 50,
    light_green_v      = 50,
    vehicle_weights    = VehicleTypeWeights(
        motorcycle = 12,
        car        = 75,
        van        = 10,
        bus        = 1,
        emergency  = 2,
    ),
    personalities = _profiles(
        CAUTIOUS   = dict(spawn_weight=10),
        NORMAL     = dict(spawn_weight=55),
        AGGRESSIVE = dict(spawn_weight=25),
        RUSHER     = dict(spawn_weight=10),
    ),
)

SCENARIOS["mobil_selfish"] = SimConfig(
    output_file      = "out_mobil_selfish.gif",
    use_idm          = True,
    use_mobil        = True,
    mobil_politeness = 0.05,
    mobil_threshold  = 0.05,
    spawn_prob       = 0.32,
    steps            = 500,
    vehicle_weights  = VehicleTypeWeights(
        motorcycle = 10,
        car        = 70,
        van        = 18,
        bus        = 0,
        emergency  = 2,
    ),
)

SCENARIOS["mobil_cooperative"] = SimConfig(
    output_file      = "out_mobil_cooperative.gif",
    use_idm          = True,
    use_mobil        = True,
    mobil_politeness = 0.90,
    mobil_threshold  = 0.20,
    spawn_prob       = 0.32,
    steps            = 500,
    vehicle_weights  = VehicleTypeWeights(
        motorcycle = 10,
        car        = 70,
        van        = 18,
        bus        = 0,
        emergency  = 2,
    ),
)
