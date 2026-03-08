"""
main.py — Entry point del simulatore di traffico.

Utilizzo:
    python main.py                          # scenario di default
    python main.py heavy_traffic            # scenario predefinito
    python main.py adaptive_light           # semaforo adattivo
    python main.py --list                   # elenca tutti gli scenari

Creare uno scenario personalizzato al volo:
    Modificare il blocco CUSTOM CONFIG qui sotto oppure aggiungere
    una voce in traffic/scenarios.py.
"""

import sys
import matplotlib.pyplot as plt

from traffic import SCENARIOS, list_scenarios, SimConfig, Sim, Renderer
from traffic import TopologyConfig, RoadSegment, TOPOLOGIES, list_topologies
from traffic.config import LightPolicy, ManualObstacle


# =====================================================================
# CUSTOM CONFIG (opzionale — sovrascrive lo scenario scelto da CLI)
# =====================================================================
# Decommenta e modifica questo blocco per creare una configurazione
# personalizzata senza modificare scenarios.py.
#
# CUSTOM = SimConfig(
#     grid_size         = 90,
#     num_lanes         = 3,
#     max_speed         = 4,
#     steps             = 600,
#     interval_ms       = 80,
#     output_file       = "out_custom.gif",
#     fps               = 12,
#     dpi               = 90,
#
#     # ── Spawn ─────────────────────────────────────────────────────
#     spawn_prob        = 0.32,
#     spawn_prob_east   = None,   # None = usa spawn_prob
#     spawn_prob_west   = None,
#     spawn_prob_south  = None,
#     spawn_prob_north  = None,
#     density_cap       = 0.75,
#
#     # ── Semaforo ──────────────────────────────────────────────────
#     light_policy      = LightPolicy.FIXED,
#     light_green_h     = 45,
#     light_green_v     = 45,
#     light_yellow      = 6,
#
#     # ── Incidenti ─────────────────────────────────────────────────
#     accident_prob     = 0.00045,
#     accident_dur_min  = 12,
#     accident_dur_max  = 55,
#
#     # ── Ostacoli manuali ──────────────────────────────────────────
#     manual_obstacles  = [
#         ManualObstacle(row=46, col=30, duration=200, label="cantiere"),
#     ],
# )
CUSTOM = None   # <- imposta a None per usare lo scenario CLI


# =====================================================================
# SELEZIONE SCENARIO
# =====================================================================

def select_config() -> SimConfig:
    """Ritorna la SimConfig da usare basandosi su CUSTOM o CLI."""

    if CUSTOM is not None:
        print("[main] Uso configurazione CUSTOM definita in main.py")
        return CUSTOM

    args = sys.argv[1:]

    if "--list" in args or "-l" in args:
        print("\nScenari disponibili:")
        for name in list_scenarios():
            cfg = SCENARIOS[name]
            print(f"\n  [{name}]")
            print(cfg.summary())
        sys.exit(0)

    name = args[0] if args else "default"

    if name not in SCENARIOS:
        print(f"Scenario '{name}' non trovato.")
        print(f"Disponibili: {', '.join(list_scenarios())}")
        print("Uso: python main.py [nome_scenario]")
        sys.exit(1)

    return SCENARIOS[name]


# =====================================================================
# MAIN
# =====================================================================

def main():
    cfg = select_config()

    print("=" * 54)
    print(f"  Simulatore Traffico  —  scenario: {sys.argv[1] if len(sys.argv) > 1 else 'default'}")
    print(cfg.summary())
    print("=" * 54)

    sim      = Sim(cfg)
    renderer = Renderer(sim)
    ani      = renderer.build_animation()
    renderer.save(ani)

    plt.show()


if __name__ == "__main__":
    main()
