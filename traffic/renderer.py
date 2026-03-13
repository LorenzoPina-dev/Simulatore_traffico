"""
renderer.py — Visualizzazione matplotlib della simulazione v3.

Novità v3:
  - Palette estesa con colori per moto (14), van (15), bus (16),
    emergenza (17), fermata bus (18)
  - Statistiche arricchite: tipo veicolo, plotoni, emergenze
  - Titolo mostra la composizione del traffico in tempo reale
"""

from __future__ import annotations
from typing import List, TYPE_CHECKING

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap
from matplotlib.text import Text
from matplotlib.patches import FancyBboxPatch
from matplotlib.widgets import Button

if TYPE_CHECKING:
    from .simulation import Sim

from .core.types import VehicleType as _VType

# ── Dimensione visiva per tipo (frazione della cella, 1.0 = cella piena) ──
_VSIZE = {
    _VType.MOTORCYCLE: 0.38,
    _VType.CAR:        0.55,
    _VType.VAN:        0.65,
    _VType.BUS:        0.80,
    _VType.EMERGENCY:  0.60,
}
_VSIZE_DEFAULT = 0.55

# Colore di fill per tipo / velocità
_VCOLOR_TYPE = {
    _VType.MOTORCYCLE: "#00b4d8",
    _VType.VAN:        "#457b9d",
    _VType.BUS:        "#1d3557",
    _VType.EMERGENCY:  "#ff2020",
}

# Offset pull-over (spostamento laterale verso il bordo destro della corsia).
# È espresso nella stessa unità della cella.
_PULL_OVER_SHIFT = 0.20


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
    "#1a3a5c",   # 11  corsia ded. sx
    "#2d1a5c",   # 12  corsia ded. dx
    "#0d3d2a",   # 13  slip lane
    # ── v3 ──────────────────────────────────────
    "#00b4d8",   # 14  moto          (azzurro chiaro)
    "#457b9d",   # 15  furgone/van   (blu acciaio)
    "#1d3557",   # 16  bus           (blu scuro)
    "#360208",   # 17  emergenza     (rosso vivo)
    "#2d6a4f",   # 18  fermata bus   (verde scuro)
    "#ffb347",   # 19  cella prenotata (arancione chiaro)
    "#9370db",   # 20  cella occupata+prenotata (viola)
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
    "Corsia ded. sx",
    "Corsia ded. dx",
    "Slip lane (bypass)",
    "Moto",
    "Furgone (van)",
    "Bus",
    "Emergenza",
    "Fermata bus",
    "Cella prenotata (IPR)",
    "Cella occupata+prenotata",
]


class Renderer:
    """
    Gestisce la visualizzazione matplotlib di una simulazione v3.

    Pannello superiore  : griglia 2D con colormap arricchita (19 valori)
    Pannello inferiore  : grafici temporali (auto, velocità, passaggi rosso,
                          plotoni attivi)
    """

    def __init__(self, sim: "Sim"):
        self.sim  = sim
        self.cfg  = sim.cfg
        self.geo  = sim.geo
        self.cmap = ListedColormap(PALETTE)

        # Cronologie
        self._hist_cars:   List[float] = []
        self._hist_spd:    List[float] = []
        self._hist_rr:     List[float] = []
        self._hist_row:    List[float] = []
        self._hist_plat:   List[float] = []   # plotoni attivi
        self._hist_spawn:  List[float] = []   # frequenza spawn (x100)
        self._ipr_texts:   List[Text] = []
        self._block_texts: List[Text] = []
        self._stop_texts:  List[Text] = []
        self._veh_patches: list        = []

        self._build_figure()

    # ── Costruzione figura ────────────────────────────────────────────

    # ── Helper bottoni spawn ──────────────────────────────────────────

    def _freq_label(self) -> str:
        """Etichetta frequenza spawn corrente."""
        mult = self.sim.spawn_rate_mult
        pct  = int(round(self.sim.cfg.spawn_prob * mult * 100))
        return f"{mult:.2f}x  ({pct}%)"

    def _on_toggle_spawn(self, _event):
        """Pausa / riprendi spawn."""
        self.sim.spawn_enabled = not self.sim.spawn_enabled
        if self.sim.spawn_enabled:
            self._btn_toggle.label.set_text("\u23f8 Pausa Spawn")
        else:
            self._btn_toggle.label.set_text("\u25b6 Riprendi Spawn")
        self.fig.canvas.draw_idle()

    def _on_freq_down(self, _event):
        """Diminuisce frequenza spawn del 25% (min 0.25x)."""
        self.sim.spawn_rate_mult = max(0.25, round(self.sim.spawn_rate_mult - 0.25, 2))
        self._lbl_freq.set_text(self._freq_label())
        self.fig.canvas.draw_idle()

    def _on_freq_up(self, _event):
        """Aumenta frequenza spawn del 25% (max 4.0x)."""
        self.sim.spawn_rate_mult = min(4.0, round(self.sim.spawn_rate_mult + 0.25, 2))
        self._lbl_freq.set_text(self._freq_label())
        self.fig.canvas.draw_idle()

    def _build_figure(self):
        # Figura leggermente più alta per ospitare la barra dei controlli
        self.fig = plt.figure(figsize=(10, 12.4))
        self.fig.patch.set_facecolor("#0a0a12")

        # Tre aree: griglia sim (alta), grafico stats (media), bottoni (bassa)
        self.ax   = self.fig.add_axes([0.04, 0.27, 0.92, 0.70])  # griglia
        self.ax_s = self.fig.add_axes([0.04, 0.13, 0.92, 0.12])  # stats

        geo = self.geo

        # ── Pannello principale ──────────────────────────────────────
        self.ax.set_facecolor("#0a0a12")
        self.im = self.ax.imshow(
            self.sim.render_grid(),
            cmap=self.cmap, vmin=0, vmax=len(PALETTE) - 1,
            aspect="equal", interpolation="nearest",
        )

        self._draw_lane_lines()
        self._draw_intersection_border()
        self._draw_slip_lanes()
        self._draw_bus_stops()

        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for sp in self.ax.spines.values():
            sp.set_edgecolor("#333")

        # Legenda (max 3 colonne)
        legend_patches = [
            mpatches.Patch(color=PALETTE[i], label=LEGEND_ITEMS[i])
            for i in range(len(PALETTE))
        ]
        self.ax.legend(
            handles=legend_patches, loc="upper right",
            fontsize=6.5, ncol=3,
            facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
        )

        scenario_name = self.cfg.output_file.replace(".gif", "")
        self.title = self.ax.set_title(
            f"Simulatore Incrocio  |  {scenario_name}",
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
            [], [], color="#06d6a0", linewidth=1.2, label="Auto /2")
        self.line_spd,  = self.ax_s.plot(
            [], [], color="#ffd166", linewidth=1.2, label="Vel.media ×10")
        self.line_rr,   = self.ax_s.plot(
            [], [], color="#e63946", linewidth=1.0, linestyle="--", label="Rosso /10")
        self.line_row,  = self.ax_s.plot(
            [], [], color="#ff9f1c", linewidth=1.0, linestyle=":", label="Prec.ign. /5")
        self.line_plat, = self.ax_s.plot(
            [], [], color="#00b4d8", linewidth=1.0, linestyle="-.", label="Plotoni ×3")
        self.line_spawn, = self.ax_s.plot(
            [], [], color="#c77dff", linewidth=1.6, linestyle="-", label="Spawn ×100")
        self.ax_s.legend(
            loc="upper left", fontsize=7,
            facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
        )

        # ── Barra controlli spawn ───────────────────────────────────────────
        _bkw = dict(facecolor="#1e1e30", edgecolor="#555")

        ax_btn_tog  = self.fig.add_axes([0.04, 0.02, 0.24, 0.07])
        ax_btn_down = self.fig.add_axes([0.32, 0.02, 0.13, 0.07])
        ax_lbl_freq = self.fig.add_axes([0.47, 0.02, 0.12, 0.07])
        ax_btn_up   = self.fig.add_axes([0.61, 0.02, 0.13, 0.07])

        ax_lbl_freq.set_axis_off()
        ax_lbl_freq.set_facecolor("#0d0d1a")

        self._btn_toggle = Button(ax_btn_tog,  "⏸ Pausa Spawn", **_bkw)
        self._btn_down   = Button(ax_btn_down, "− Freq (-25%)",  **_bkw)
        self._btn_up     = Button(ax_btn_up,   "+ Freq (+25%)",   **_bkw)

        for btn in (self._btn_toggle, self._btn_down, self._btn_up):
            btn.label.set_color("white")
            btn.label.set_fontsize(9)

        self._lbl_freq = ax_lbl_freq.text(
            0.5, 0.5, self._freq_label(),
            ha="center", va="center",
            color="#c77dff", fontsize=10, fontweight="bold",
            transform=ax_lbl_freq.transAxes,
        )

        self._btn_toggle.on_clicked(self._on_toggle_spawn)
        self._btn_down.on_clicked(self._on_freq_down)
        self._btn_up.on_clicked(self._on_freq_up)

    def _draw_lane_lines(self):
        geo  = self.geo
        topo = self.cfg.topology
        cr   = geo.center_r
        cc   = geo.center_c
        kw_c = dict(color="#ffffffcc", linewidth=1.5)
        kw_d = dict(color="white", linewidth=0.5, linestyle="--", alpha=0.35)

        if topo.west.enabled or topo.east.enabled:
            self.ax.axhline(y=cr - 0.5, **kw_c)
        if topo.north.enabled or topo.south.enabled:
            self.ax.axvline(x=cc - 0.5, **kw_c)
        if topo.west.enabled:
            for i in range(1, geo.lanes_east):
                self.ax.axhline(y=cr + i - 0.5, **kw_d)
        if topo.east.enabled:
            for i in range(1, geo.lanes_west):
                self.ax.axhline(y=geo.ir0 + i - 0.5, **kw_d)
        if topo.north.enabled:
            for i in range(1, geo.lanes_south):
                self.ax.axvline(x=geo.ic0 + i - 0.5, **kw_d)
        if topo.south.enabled:
            for i in range(1, geo.lanes_north):
                self.ax.axvline(x=cc + i - 0.5, **kw_d)

    def _draw_intersection_border(self):
        geo = self.geo
        kw  = dict(color="#ffffff50", linewidth=0.8)
        self.ax.axvline(x=geo.ic0 - 0.5, **kw)
        self.ax.axvline(x=geo.ic1 + 0.5, **kw)
        self.ax.axhline(y=geo.ir0 - 0.5, **kw)
        self.ax.axhline(y=geo.ir1 + 0.5, **kw)

    def _draw_slip_lanes(self):
        if not self.cfg.topology.slip_lanes_enabled:
            return
        geo = self.geo
        kw  = dict(color="#00ff9960", linewidth=1.0)
        tkw = dict(color="#00ff99", fontsize=4.5, ha="center", va="center",
                   fontweight="bold", alpha=0.85)
        for entry in geo.slip_entries:
            if not entry.path:
                continue
            all_pts = [(entry.entry_c, entry.entry_r)] + [(c, r) for (r, c) in entry.path]
            xs = [p[0] for p in all_pts]; ys = [p[1] for p in all_pts]
            self.ax.plot(xs, ys, **kw)
            vis = entry.visual_cells
            if vis:
                mid_r = sum(r for r, c in vis) / len(vis)
                mid_c = sum(c for r, c in vis) / len(vis)
                self.ax.text(mid_c, mid_r, "slip", **tkw)

    def _draw_bus_stops(self):
        """Disegna le etichette delle fermate bus sulla griglia."""
        if not self.cfg.bus_stops:
            return
        tkw = dict(color="#98f5e1", fontsize=4.0, ha="center", va="center",
                   fontweight="bold", alpha=0.90)
        for stop in self.cfg.bus_stops:
            self.ax.text(stop.col, stop.row, "B", **tkw)

    def _clear_ipr_texts(self):
        for t in self._ipr_texts:
            t.remove()
        self._ipr_texts.clear()

    def _draw_ipr_reservations(self):
        """Etichette con l'id veicolo sulle celle prenotate IPR."""
        self._clear_ipr_texts()
        res = self.sim.reservation_map()
        if not res:
            return
        geo = self.geo
        tkw = dict(
            color="#111111",
            fontsize=3.5,
            ha="center",
            va="center",
            fontweight="bold",
            alpha=0.9,
        )
        for (r, c), vid in res.items():
            if not geo.in_bounds(r, c):
                continue
            if not geo.in_intersection(r, c):
                continue
            self._ipr_texts.append(self.ax.text(c, r, str(vid), **tkw))

    def _clear_block_texts(self):
        for t in self._block_texts:
            t.remove()
        self._block_texts.clear()

    def _draw_entry_blocks(self):
        """Overlay motivi di blocco ingresso (RED/ROW/EXIT)."""
        self._clear_block_texts()
        blocks = self.sim.debug_entry_blocks()
        if not blocks:
            return
        geo = self.geo
        colors = {
            "RED": "#ff4d4d",
            "ROW": "#ffd166",
            "EXIT": "#4dabf7",
            "IPR": "#c77dff",
            "OCC": "#a0a0a0",
            "PRE": "#9bf6ff",
        }
        for r, c, reason, _vid in blocks:
            if not geo.in_bounds(r, c):
                continue
            if reason == "RED":
                label = "R"
            elif reason == "ROW":
                label = "Y"
            elif reason == "EXIT":
                label = "X"
            elif reason == "IPR":
                label = "P"
            elif reason == "OCC":
                label = "O"
            else:
                label = ">"
            tkw = dict(
                color=colors.get(reason, "white"),
                fontsize=4.0,
                ha="center",
                va="center",
                fontweight="bold",
                alpha=0.95,
            )
            self._block_texts.append(self.ax.text(c, r, label, **tkw))

    def _clear_stop_texts(self):
        for t in self._stop_texts:
            t.remove()
        self._stop_texts.clear()

    def _draw_stop_reasons(self):
        """Overlay motivi di stop sui veicoli fermi."""
        self._clear_stop_texts()
        stops = self.sim.debug_stop_reasons()
        if not stops:
            return
        geo = self.geo
        colors = {
            "RED": "#ff4d4d",
            "ROW": "#ffd166",
            "EXIT": "#4dabf7",
            "IPR": "#c77dff",
            "OCC": "#a0a0a0",
            "PRE": "#9bf6ff",
            "SAFE": "#ffffff",
            "DELAY": "#ffb347",
        }
        labels = {
            "RED": "R",
            "ROW": "Y",
            "EXIT": "X",
            "IPR": "P",
            "OCC": "O",
            "PRE": ">",
            "SAFE": "S",
            "DELAY": "D",
        }
        for r, c, reason, _vid in stops:
            if not geo.in_bounds(r, c):
                continue
            tkw = dict(
                color=colors.get(reason, "white"),
                fontsize=4.0,
                ha="center",
                va="center",
                fontweight="bold",
                alpha=0.95,
            )
            self._stop_texts.append(self.ax.text(c, r, labels.get(reason, "?"), **tkw))

    # ── Aggiornamento frame ───────────────────────────────────────────

    def _clear_vehicle_patches(self):
        for p in self._veh_patches:
            p.remove()
        self._veh_patches.clear()

    @staticmethod
    def _car_color(vtype, spd: int) -> str:
        c = _VCOLOR_TYPE.get(vtype)
        if c:
            return c
        if spd == 0: return "#e63946"
        if spd == 1: return "#f4a261"
        if spd <= 3: return "#ffd166"
        return "#06d6a0"

    def _draw_vehicles(self):
        """Disegna i veicoli come rettangoli arrotondati dimensionati per tipo.
        Pull-over=True sposta il rettangolo verso il bordo destro della corsia."""
        for (r, c, vtype, pull_over, dr, dc, spd) in self.sim.vehicle_list():
            size  = _VSIZE.get(vtype, _VSIZE_DEFAULT)
            color = self._car_color(vtype, spd)
            pad   = (1.0 - size) / 2.0
            shift = _PULL_OVER_SHIFT if pull_over else 0.0
            if   dc == +1: ro, co = +shift, 0.0
            elif dc == -1: ro, co = -shift, 0.0
            elif dr == +1: ro, co =  0.0, +shift
            else:          ro, co =  0.0, -shift
            rect = FancyBboxPatch(
                (c - 0.5 + pad + co, r - 0.5 + pad + ro),
                size, size,
                boxstyle="round,pad=0.03",
                linewidth=0, facecolor=color, alpha=0.95, zorder=3,
            )
            self.ax.add_patch(rect)
            self._veh_patches.append(rect)

    def update_frame(self, frame: int):
        """Callback FuncAnimation."""
        self.sim.update()
        s = self.sim.stats()

        # Griglia infrastruttura + veicoli come patch dimensionate
        self.im.set_array(self.sim.render_grid())
        self._clear_vehicle_patches()
        self._draw_vehicles()
        if getattr(self.sim, "debug", False):
            self._draw_ipr_reservations()
            self._draw_entry_blocks()
            self._draw_stop_reasons()

        # Composizione veicoli per tipo
        bt = s.get("by_type", {})
        type_str = (
            f"M:{bt.get('MOTORCYCLE',0)} "
            f"A:{bt.get('CAR',0)} "
            f"V:{bt.get('VAN',0)} "
            f"B:{bt.get('BUS',0)} "
            f"E:{bt.get('EMERGENCY',0)}"
        )
        platoon_str = f"Plotoni:{s['num_platoons']}({s['in_platoon']})"

        compliance = s.get('row_compliance_rate', 1.0)
        ipr_res = self.sim.reservation_map()
        ipr_cnt = len(ipr_res)
        spawn_icon = ("⏸ SPAWN OFF" if not self.sim.spawn_enabled
                       else f"SPAWN {self.sim.spawn_rate_mult:.2f}x")
        self.title.set_text(
            f"Step {s['step']:4d}  |  Auto:{s['cars']:3d}  [{type_str}]  "
            f"|  Vel:{s['avg_speed']:.2f}  |  Sem:{s['light_phase']}  "
            f"|  {platoon_str}  |  Acc:{s['total_acc']}  "
            f"|  Rosso:{s['total_rr']}  "
            f"|  ROW ced:{s.get('total_row_yld', 0)} viol:{s.get('total_row_vio', 0)}  "
            f"|  WaitingROW:{s.get('waiting_row', 0)}  IPRres:{ipr_cnt}  "
            f"|  Compliance:{compliance:.0%}  |  [{spawn_icon}]"
        )

        # Grafici
        self._hist_cars.append(s["cars"] / 2)
        self._hist_spd.append(s["avg_speed"] * 10)
        self._hist_rr.append(s["total_rr"] / 10)
        self._hist_row.append(s["total_row_vio"] / 5)
        self._hist_plat.append(s["num_platoons"] * 3)
        # Frequenza spawn effettiva: 0 se pausa, altrimenti prob*mult*100
        self._hist_spawn.append(s.get("spawn_rate", 0.0) * 100)

        xs = list(range(len(self._hist_cars)))
        self.line_cars.set_data(xs, self._hist_cars)
        self.line_spd.set_data(xs, self._hist_spd)
        self.line_rr.set_data(xs, self._hist_rr)
        self.line_row.set_data(xs, self._hist_row)
        self.line_plat.set_data(xs, self._hist_plat)
        self.line_spawn.set_data(xs, self._hist_spawn)

        # Aggiorna etichetta frequenza (potrebbe essere cambiata da bottone)
        self._lbl_freq.set_text(self._freq_label())

        self.ax_s.set_xlim(0, max(self.cfg.steps, len(self._hist_cars)))
        top = max(100.0,
                  max(self._hist_rr)   if self._hist_rr   else 100,
                  max(self._hist_row)  if self._hist_row  else 100,
                  max(self._hist_spawn) if self._hist_spawn else 100)
        self.ax_s.set_ylim(0, top * 1.1)

        return (self.im, self.title, self.line_cars, self.line_spd,
                self.line_rr, self.line_row, self.line_plat, self.line_spawn)

    # ── Build e save ──────────────────────────────────────────────────

    def build_animation(self) -> animation.FuncAnimation:
        return animation.FuncAnimation(
            self.fig,
            self.update_frame,
            frames=self.cfg.steps,
            interval=self.cfg.interval_ms,
            blit=False,
        )

    def save(self, ani: animation.FuncAnimation):
        ani.save(
            self.cfg.output_file,
            writer="pillow",
            fps=self.cfg.fps,
            dpi=self.cfg.dpi,
        )
        print(f"\nSimulazione salvata: {self.cfg.output_file}")
        s = self.sim.stats()
        print(f"  Auto spawned totali  : {s['total_spawned']}")
        print(f"  Emergenze spawned    : {s['total_em']}")
        print(f"  Incidenti totali     : {s['total_acc']}")
        print(f"  Passaggi col rosso   : {s['total_rr']}")
        print(f"  Plotoni formati      : {s['total_platoon_formed']}")
