"""
renderer.py — Visualizzazione matplotlib della simulazione.

Renderer costruisce e aggiorna la figura a due pannelli:
    - Pannello principale: griglia 2D con colormap
    - Pannello statistiche: 3 serie temporali (auto, velocita', rossi)

Utilizzo:
    sim = Sim(cfg)
    renderer = Renderer(sim)
    ani = renderer.build_animation()
    renderer.save(ani)
    plt.show()
"""

from __future__ import annotations
from typing import List, TYPE_CHECKING

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap

if TYPE_CHECKING:
    from .simulation import Sim


# ── Palette e legenda ─────────────────────────────────────────────────

PALETTE = [
    "#0f1117",   #  0  vuoto
    "#2a3a4a",   #  1  strada
    "#3a5060",   #  2  incrocio
    "#e63946",   #  3  auto ferma   (v=0)
    "#f4a261",   #  4  auto lenta   (v=1)
    "#ffd166",   #  5  auto media   (v=2-3)
    "#06d6a0",   #  6  auto veloce  (v=4+)
    "#b548c6",   #  7  ostacolo / incidente
    "#ff2020",   #  8  stop ROSSO
    "#20ff20",   #  9  stop VERDE
    "#ffc300",   # 10  stop GIALLO
]

LEGEND_ITEMS = [
    "Vuoto",
    "Strada",
    "Incrocio",
    "Auto ferma  (v=0)",
    "Auto lenta  (v=1)",
    "Auto media  (v=2-3)",
    "Auto veloce (v=4+)",
    "Ostacolo / incidente",
    "Stop line ROSSO",
    "Stop line VERDE",
    "Stop line GIALLO",
]


class Renderer:
    """
    Gestisce la visualizzazione matplotlib di una simulazione.

    Pannello superiore  : griglia 2D (imshow) con overlay linee corsie
    Pannello inferiore  : grafici temporali di auto, velocita' e passaggi rosso
    """

    def __init__(self, sim: "Sim"):
        self.sim  = sim
        self.cfg  = sim.cfg
        self.geo  = sim.geo
        self.cmap = ListedColormap(PALETTE)

        # Cronologie per i grafici statistiche
        self._hist_cars: List[float] = []
        self._hist_spd:  List[float] = []
        self._hist_rr:   List[float] = []
        self._hist_row:  List[float] = []   # violazioni precedenza cumulative

        self._build_figure()

    # ── Costruzione figura ────────────────────────────────────────────

    def _build_figure(self):
        self.fig, (self.ax, self.ax_s) = plt.subplots(
            2, 1,
            figsize=(10, 11),
            gridspec_kw={"height_ratios": [9, 2]},
        )
        self.fig.patch.set_facecolor("#0a0a12")

        geo = self.geo

        # ── Pannello principale ──────────────────────────────────────
        self.ax.set_facecolor("#0a0a12")
        self.im = self.ax.imshow(
            self.sim.render_grid(),
            cmap=self.cmap, vmin=0, vmax=10,
            aspect="equal", interpolation="nearest",
        )

        self._draw_lane_lines()
        self._draw_intersection_border()

        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for sp in self.ax.spines.values():
            sp.set_edgecolor("#333")

        legend_patches = [
            mpatches.Patch(color=PALETTE[i], label=LEGEND_ITEMS[i])
            for i in range(len(PALETTE))
        ]
        self.ax.legend(
            handles=legend_patches, loc="upper right",
            fontsize=7, ncol=3,
            facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
        )

        self.title = self.ax.set_title(
            f"Simulatore Incrocio a +  |  scenario: {self.cfg.output_file}",
            color="white", fontsize=10, pad=6,
        )

        # ── Pannello statistiche ─────────────────────────────────────
        self.ax_s.set_facecolor("#0d0d1a")
        self.ax_s.set_xlim(0, self.cfg.steps)
        self.ax_s.set_ylim(0, 100)
        self.ax_s.set_ylabel("Metriche (norm.)", color="#aaa", fontsize=8)
        self.ax_s.set_xlabel("Step", color="#aaa", fontsize=8)
        self.ax_s.tick_params(colors="#666", labelsize=7)
        for sp in self.ax_s.spines.values():
            sp.set_edgecolor("#333")

        self.line_cars, = self.ax_s.plot(
            [], [], color="#06d6a0", linewidth=1.2, label="Auto / 2")
        self.line_spd,  = self.ax_s.plot(
            [], [], color="#ffd166", linewidth=1.2, label="Vel.media x10")
        self.line_rr,   = self.ax_s.plot(
            [], [], color="#e63946", linewidth=1.0,
            linestyle="--", label="Rosso pass. / 10")
        self.line_row,  = self.ax_s.plot(
            [], [], color="#ff9f1c", linewidth=1.0,
            linestyle=":", label="Prec.ignorate / 5")
        self.ax_s.legend(
            loc="upper left", fontsize=7,
            facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
        )

        plt.tight_layout(pad=1.2)

    def _draw_lane_lines(self):
        """Disegna le linee tratteggiate tra corsie e la linea di mezzeria."""
        geo  = self.geo
        half = geo.half
        cx   = geo.center

        # Linea centrale piena (divide i sensi di marcia)
        self.ax.axhline(y=cx - 0.5, color="#ffffffcc", linewidth=1.5)
        self.ax.axvline(x=cx - 0.5, color="#ffffffcc", linewidth=1.5)

        # Linee tratteggiate tra corsie dello stesso senso
        for i in range(1, half):
            kw = dict(color="white", linewidth=0.5, linestyle="--", alpha=0.35)
            self.ax.axhline(y=cx + i - 0.5, **kw)
            self.ax.axhline(y=cx - half + i - 0.5, **kw)
            self.ax.axvline(x=cx + i - 0.5, **kw)
            self.ax.axvline(x=cx - half + i - 0.5, **kw)

    def _draw_intersection_border(self):
        """Disegna il bordo della zona incrocio."""
        geo = self.geo
        kw  = dict(color="#ffffff50", linewidth=0.8)
        self.ax.axvline(x=geo.ic0 - 0.5, **kw)
        self.ax.axvline(x=geo.ic1 + 0.5, **kw)
        self.ax.axhline(y=geo.ir0 - 0.5, **kw)
        self.ax.axhline(y=geo.ir1 + 0.5, **kw)

    # ── Aggiornamento frame ───────────────────────────────────────────

    def update_frame(self, frame: int):
        """Callback per FuncAnimation: aggiorna un frame."""
        self.sim.update()
        s = self.sim.stats()

        # Aggiorna griglia
        self.im.set_array(self.sim.render_grid())

        # Aggiorna titolo
        self.title.set_text(
            f"Step {s['step']:4d}  |  Auto: {s['cars']:3d}  |  "
            f"Inc.: {s['obstacles']:2d}  |  "
            f"Vel.: {s['avg_speed']:.2f}  |  Frus.: {s['avg_frus']:.1f}  |  "
            f"Sem.: {s['light_phase']}  |  "
            f"Acc.: {s['total_acc']}  |  Rosso: {s['total_rr']}  |  "
            f"Prec.att.: {s['waiting_row']}  "
            f"Prec.ign.: {s['total_row_vio']}"
        )

        # Aggiorna grafici
        self._hist_cars.append(s["cars"] / 2)
        self._hist_spd.append(s["avg_speed"] * 10)
        self._hist_rr.append(s["total_rr"] / 10)
        self._hist_row.append(s["total_row_vio"] / 5)

        xs = list(range(len(self._hist_cars)))
        self.line_cars.set_data(xs, self._hist_cars)
        self.line_spd.set_data(xs, self._hist_spd)
        self.line_rr.set_data(xs, self._hist_rr)
        self.line_row.set_data(xs, self._hist_row)

        self.ax_s.set_xlim(0, max(self.cfg.steps, len(self._hist_cars)))
        top = max(100.0,
                  max(self._hist_rr)  if self._hist_rr  else 100,
                  max(self._hist_row) if self._hist_row else 100)
        self.ax_s.set_ylim(0, top * 1.1)

        return self.im, self.title, self.line_cars, self.line_spd, self.line_rr, self.line_row

    # ── Build e save animazione ───────────────────────────────────────

    def build_animation(self) -> animation.FuncAnimation:
        """Crea e ritorna l'oggetto FuncAnimation."""
        return animation.FuncAnimation(
            self.fig,
            self.update_frame,
            frames=self.cfg.steps,
            interval=self.cfg.interval_ms,
            blit=False,
        )

    def save(self, ani: animation.FuncAnimation):
        """Salva la GIF su disco."""
        ani.save(
            self.cfg.output_file,
            writer="pillow",
            fps=self.cfg.fps,
            dpi=self.cfg.dpi,
        )
        print(f"\nSimulazione salvata: {self.cfg.output_file}")
        s = self.sim.stats()
        print(f"  Auto spawned totali : {s['total_spawned']}")
        print(f"  Incidenti totali    : {s['total_acc']}")
        print(f"  Passaggi col rosso  : {s['total_rr']}")
