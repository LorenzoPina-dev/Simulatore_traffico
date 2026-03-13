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
from traffic import LightPolicy, ManualObstacle


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

    args = [a for a in sys.argv[1:] if not a.startswith("--") and not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]

    if "--list" in flags or "-l" in flags:
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
    
    # Opzioni di debug
    debug_mode = "--debug" in sys.argv
    print_reservations = "--print-res" in sys.argv
    save_gif = "--save" in sys.argv
    
    # ... codice esistente ...
    
    sim = Sim(cfg)
    sim.debug = debug_mode
    
    if debug_mode:
        print("\n[DEBUG] Modalità debug attivata")
        print(f"[DEBUG] Celle incrocio: rows [{sim.geo.ir0}-{sim.geo.ir1}], cols [{sim.geo.ic0}-{sim.geo.ic1}]")
    
    renderer = Renderer(sim)
    ani = renderer.build_animation()
    
    # Aggiungi callback per print periodico delle prenotazioni
    if print_reservations:
        def debug_callback(frame):
            if frame % 50 == 0:  # stampa ogni 50 step
                sim.print_reservations()
        
        # Modifica l'animazione per includere il callback
        original_update = renderer.update_frame
        def wrapped_update(frame):
            debug_callback(frame)
            return original_update(frame)
        renderer.update_frame = wrapped_update
    
    print("[main] Avvio simulazione live — chiudi la finestra per uscire.")
    if save_gif:
        print(f"[main] Al termine verrà salvata la GIF: {cfg.output_file}")
    if debug_mode:
        print("[main] Premi 'p' nella finestra per stampare le prenotazioni")
        
        # Aggiungi handler per tasto 'p'
        def on_key(event):
            if event.key == 'p':
                sim.print_reservations()
        renderer.fig.canvas.mpl_connect('key_press_event', on_key)
    
    plt.show()

    # ── Salva GIF solo se richiesto con --save ────────────────────────
    if save_gif:
        print("[main] Salvataggio GIF in corso...")
        sim2      = Sim(cfg)          # nuova istanza per ripartire da zero
        renderer2 = Renderer(sim2)
        ani2      = renderer2.build_animation()
        renderer2.save(ani2)
        plt.close(renderer2.fig)


if __name__ == "__main__":
    main()
