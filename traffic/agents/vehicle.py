"""
agents/vehicle.py — Agente veicolo autonomo.

Vehicle è un agente autonomo che:
    1. Mantiene il proprio stato (posizione, velocità, intenzione, ecc.)
    2. Decide autonomamente come comportarsi tramite i behavior iniettati
    3. Espone metodi atomici che il SimEngine chiama in sequenza

Principio: il veicolo SA COSA FARE. Il motore SA QUANDO chiamarlo.

Behavior iniettati:
    movement   : MovementBehavior  — come accelerare/frenare
    lane_change: LaneChangeBehavior — quando/come cambiare corsia
    stop       : StopBehavior       — quando fermarsi (es. bus stop)
    pull_over  : PullOverBehavior   — quando cedere il passo

Separation of concerns:
    - Vehicle: stato + decisioni delegate ai behavior
    - SimEngine: ordinamento degli step, coordination IPR
    - Behaviors: logica pura, ricevono SimContext read-only
"""
from __future__ import annotations
import random
from typing import TYPE_CHECKING, Optional, Set

from ..core.types     import VehicleType
from ..core.constants import VEHICLE_LENGTH, IDM_BASE

if TYPE_CHECKING:
    from ..core.config        import SimConfig, PersonalityProfile
    from ..world.geometry     import GridGeometry
    from ..behaviors.interfaces import MovementBehavior, LaneChangeBehavior, StopBehavior, PullOverBehavior
    from ..simulation.context   import SimContext


class Vehicle:
    """
    Agente veicolo sulla griglia.

    Stato immutabile dopo la costruzione:
        id, vtype, length, pers, ms, dw, rt, rr, il, ir
        idm_a, idm_b, idm_T, idm_s0, v_desired

    Stato mutabile (aggiornato ogni step):
        r, c, dr, dc, li       — posizione e corsia
        spd, v_float            — velocità discreta e continua
        delay, frus, t_stop    — comportamento reattivo
        in_inter, turned, dist — stato incrocio
        intent                  — intenzione di svolta

    Stato IPR (gestito da IntersectionPathReservation):
        inter_path, inter_path_idx, inter_exit_*

    Stato slip lane:
        slip_path, slip_path_idx, slip_exit_*

    Stato specifico tipo:
        siren, pull_over         (EMERGENCY)
        bus_stop_timer, next_stop_idx (BUS)
        platoon_id, platoon_role, ...  (tutti)

    Cache per evitare ricalcoli:
        _rr_val/_rr_step   — pass-red sampling
        _row_val/_row_step — right-of-way sampling
    """

    _next_id: int = 0

    def __init__(
        self,
        r: int, c: int,
        dr: int, dc: int,
        profile_index: int,
        cfg: "SimConfig",
        geo: "GridGeometry",
        vtype: VehicleType = VehicleType.CAR,
        movement:    "MovementBehavior"   = None,
        lane_change: "LaneChangeBehavior" = None,
        stop:        "StopBehavior"        = None,
        pull_over:   "PullOverBehavior"    = None,
    ):
        Vehicle._next_id += 1
        self.id = Vehicle._next_id

        # ── Posizione e direzione ──────────────────────────────────────
        self.r  = r
        self.c  = c
        self.dr = dr
        self.dc = dc

        # ── Tipo e dimensioni ─────────────────────────────────────────
        self.vtype  = vtype
        self.length = VEHICLE_LENGTH[vtype]

        # ── Profilo personalità ───────────────────────────────────────
        prof: "PersonalityProfile" = cfg.personalities[profile_index]
        self.pers = profile_index
        self.ms   = prof.max_speed
        self.dw   = prof.dawdle_prob
        self.rt   = prof.react_time
        self.rr   = prof.run_red_prob
        self.il   = prof.ignore_lane
        self.ir   = prof.ignore_row_prob

        # ── Parametri IDM ─────────────────────────────────────────────
        base = IDM_BASE[vtype]
        if vtype == VehicleType.EMERGENCY:
            self.v_desired = base["v_factor"] * cfg.max_speed
            self.idm_a     = base["a"]
            self.idm_b     = base["b"]
            self.idm_T     = base["T"]
        else:
            speed_ratio    = prof.max_speed / 3.0
            self.v_desired = float(prof.max_speed) * base["v_factor"]
            self.idm_a     = base["a"] * (0.6 + 0.4 * speed_ratio)
            self.idm_b     = base["b"]
            self.idm_T     = max(0.4, base["T"] * (1.8 - 0.6 * speed_ratio))
        self.idm_s0  = base["s0"]
        self.v_float = 0.0

        # ── Stato dinamico ────────────────────────────────────────────
        self.spd    = 0
        self.delay  = 0
        self.frus   = 0
        self.t_stop = 0
        self.dist   = 0

        # ── Stato incrocio ────────────────────────────────────────────
        self.li       = geo.lane_index(r, c, dr, dc)
        self.intent   = _assign_intent(self.li, cfg.num_lanes, prof.ignore_lane)
        self.in_inter = False
        self.turned   = False

        # ── IPR ───────────────────────────────────────────────────────
        self.inter_path:     tuple = ()
        self.inter_path_idx: int   = 0
        self.inter_exit_r:   int   = 0
        self.inter_exit_c:   int   = 0
        self.inter_exit_dr:  int   = 0
        self.inter_exit_dc:  int   = 0

        # ── Slip lane ─────────────────────────────────────────────────
        self.slip_path:     tuple = ()
        self.slip_path_idx: int   = 0
        self.slip_exit_dr:  int   = 0
        self.slip_exit_dc:  int   = 0

        # ── Platooning ────────────────────────────────────────────────
        self.platoon_id:        int = -1
        self.platoon_role:      str = ""
        self.platoon_leader_id: int = -1
        self.platoon_gap:       int = 1

        # ── Emergenza ─────────────────────────────────────────────────
        self.siren     = (vtype == VehicleType.EMERGENCY)
        self.pull_over = False

        # ── Bus ───────────────────────────────────────────────────────
        self.bus_stop_timer: int = 0
        self.next_stop_idx:  int = 0

        # ── Cache ─────────────────────────────────────────────────────
        self._rr_val:   bool = False
        self._rr_step:  int  = -1
        self._row_val:  bool = False
        self._row_step: int  = -1

        # ── Behavior iniettati ────────────────────────────────────────
        self._movement    = movement
        self._lane_change = lane_change
        self._stop        = stop
        self._pull_over_b = pull_over

    # ─────────────────────────────────────────────────────────────────
    # API AUTONOMA — chiamata dal SimEngine
    # ─────────────────────────────────────────────────────────────────

    def decide_lane_change(self, context: "SimContext") -> bool:
        """
        Il veicolo decide autonomamente se e dove cambiare corsia.
        Restituisce True se il cambio è stato eseguito.
        """
        if self.in_inter or self._lane_change is None:
            return False

        # Pull-over: priorità su cambio corsia normale
        if self._pull_over_b is not None and self._pull_over_b.should_pull_over(self, context):
            if self.li > 0:  # solo se non già in corsia destra
                return self._lane_change.execute(self, -1, context)
            return False

        direction = self._lane_change.evaluate(self, context)
        if direction == 0:
            return False
        return self._lane_change.execute(self, direction, context)

    def compute_velocity(self, context: "SimContext", extra_blocks: Set = None) -> float:
        """
        Il veicolo calcola la propria velocità target tramite il movement behavior.
        Restituisce la nuova v_float.
        """
        if self._movement is None:
            return 0.0
        return self._movement.compute_velocity(self, context, extra_blocks or set())

    def is_at_bus_stop(self, context: "SimContext") -> bool:
        """Controlla se il veicolo deve fermarsi per la fermata bus."""
        if self._stop is None:
            return False
        return self._stop.check_stop(self, context)

    def update_frustration(self, cfg) -> None:
        """Aggiorna frustrazione e stato di attesa."""
        if self.spd == 0:
            self.t_stop += 1
            self.frus    = min(self.frus + 1, cfg.frustration_max)
            if self.t_stop == 1:
                self.delay = self.rt
        else:
            self.t_stop = 0
            self.frus   = max(0, self.frus - 1)

    # ─────────────────────────────────────────────────────────────────
    # Rappresentazione
    # ─────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"Vehicle(id={self.id}, type={self.vtype.name}, "
            f"pos=({self.r},{self.c}), dir=({self.dr},{self.dc}), "
            f"v={self.v_float:.2f}→spd={self.spd})"
        )


# ─────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────

def _assign_intent(lane_idx: int, num_lanes: int, ignore_lane_prob: float) -> str:
    """Assegna il piano di svolta in base alla corsia e alla personalità."""
    if random.random() < ignore_lane_prob or num_lanes == 1:
        return random.choices(["straight", "right", "left"], [50, 25, 25])[0]
    if lane_idx == 0:
        return random.choices(["straight", "right"], [60, 40])[0]
    if lane_idx == num_lanes - 1:
        return random.choices(["straight", "left"], [55, 45])[0]
    return random.choices(["straight", "left"], [68, 32])[0]


# Alias backward-compat
Car = Vehicle
