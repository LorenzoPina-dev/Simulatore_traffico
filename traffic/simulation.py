"""
simulation.py — Motore principale della simulazione.

Sim esegue gli step del modello Nagel-Schreckenberg esteso.
Riceve SimConfig al costruttore e non dipende da variabili globali.

Ordine operazioni per step:
    1. Spawn nuove auto ai bordi
    2. Genera incidenti stocastici
    3. Per ogni auto (ordine casuale):
        a. Reaction delay
        b. Cambio corsia / sorpasso
        c. NaSch 1: accelerazione
        d. NaSch 2: frenata per ostacolo o semaforo
        e. NaSch 3: dawdling (solo fuori incrocio)
        f. Velocita' minima garantita nell'incrocio
        g. Frustrazione e reaction time
        h. NaSch 4: movimento
        i. Svolta all'incrocio
    4. Tick ostacoli (decrementa durata)
"""

from __future__ import annotations
import random
from typing import Dict, List, Set, TYPE_CHECKING

from .config       import SimConfig, ManualObstacle
from .entities     import Car, Obstacle, _assign_intent
from .geometry     import GridGeometry
from .traffic_light import TrafficLight
from .right_of_way  import RightOfWayChecker

if TYPE_CHECKING:
    pass


class Sim:
    """
    Motore della simulazione.

    Utilizzo:
        cfg = SimConfig(...)
        sim = Sim(cfg)
        for _ in range(cfg.steps):
            sim.update()
            grid = sim.render()
    """

    def __init__(self, cfg: SimConfig):
        self.cfg   = cfg
        self.geo   = GridGeometry(cfg)
        self.light = TrafficLight(cfg, self.geo)

        self.cars:  List[Car]      = []
        self.obs:   List[Obstacle] = []
        self.step   = 0

        # Statistiche cumulative
        self.total_spawned        = 0
        self.total_accidents      = 0
        self.total_red_runners    = 0
        self.total_row_violations = 0   # precedenze ignorate
        self.total_row_yields     = 0   # precedenze rispettate

        # Checker precedenza
        self.row_checker = RightOfWayChecker(cfg, self.geo)

        # Pesi personalita' (normalizzati una volta sola)
        weights = [p.spawn_weight for p in cfg.personalities]
        total   = sum(weights)
        self._pers_weights = [w / total for w in weights]
        self._pers_indices = list(range(len(cfg.personalities)))

        # Piazza ostacoli manuali
        self._place_manual_obstacles()

    # ── Inizializzazione ──────────────────────────────────────────────

    def _place_manual_obstacles(self):
        """Piazza gli ostacoli definiti in cfg.manual_obstacles."""
        for mo in self.cfg.manual_obstacles:
            self.obs.append(Obstacle(mo.row, mo.col, mo.duration, mo.label))

    # ── Mappe di supporto (ricalcolate ogni step) ─────────────────────

    def _occ_map(self) -> Dict:
        """Dizionario {(r,c): Car} — accesso O(1) alla posizione."""
        return {(car.r, car.c): car for car in self.cars}

    def _obs_set(self) -> Set:
        """Set {(r,c)} di posizioni occupate da ostacoli."""
        return {(o.r, o.c) for o in self.obs}

    # ── Calcolo gap ───────────────────────────────────────────────────

    def gap_ahead(
        self,
        r: int, c: int, dr: int, dc: int,
        occ: Dict, obs_s: Set, extra: Set,
        lookahead: int = 0,
    ) -> int:
        """
        Celle libere davanti a (r,c) nella direzione (dr,dc).
        Si ferma al primo: altra auto, ostacolo fisico, blocco extra,
        bordo griglia.

        Args:
            extra     : celle di blocco aggiuntive (es. stop line semaforo)
            lookahead : quante celle guardare avanti (default: max_speed+3)
        """
        if lookahead == 0:
            lookahead = self.cfg.max_speed + 3
        geo = self.geo
        for d in range(1, lookahead + 1):
            nr = r + dr * d
            nc = c + dc * d
            if not geo.in_bounds(nr, nc): return lookahead
            if (nr, nc) in occ:          return d - 1
            if (nr, nc) in obs_s:        return d - 1
            if (nr, nc) in extra:        return d - 1
        return lookahead

    def gap_rear(
        self,
        r: int, c: int, dr: int, dc: int,
        occ: Dict,
        lookbehind: int = 0,
    ) -> int:
        """Celle libere dietro a (r,c) nella direzione (dr,dc)."""
        if lookbehind == 0:
            lookbehind = self.cfg.max_speed + 2
        geo = self.geo
        for d in range(1, lookbehind + 1):
            nr = r - dr * d
            nc = c - dc * d
            if not geo.in_bounds(nr, nc): return lookbehind
            if (nr, nc) in occ:           return d - 1
        return lookbehind

    # ── Spawn ─────────────────────────────────────────────────────────

    def _spawn(self, occ: Dict):
        """Genera nuove auto ai bordi della griglia."""
        cfg  = self.cfg
        geo  = self.geo
        n    = len(self.cars)
        cap  = cfg.density_cap * geo.size * geo.size * 0.1  # celle stradali ~10%
        if n > cap:
            return

        for r, c, dr, dc, direction in geo.spawn_entries():
            if random.random() < cfg.spawn_for(direction):
                if (r, c) not in occ:
                    pi  = random.choices(self._pers_indices,
                                         weights=self._pers_weights)[0]
                    car = Car(r, c, dr, dc, pi, cfg, geo)
                    self.cars.append(car)
                    occ[(r, c)] = car
                    self.total_spawned += 1

    # ── Cambio corsia / sorpasso ──────────────────────────────────────

    def _try_lane_change(self, car: Car, occ: Dict, obs_s: Set) -> bool:
        """
        Tenta un cambio corsia sicuro per sorpasso o per aggirare un ostacolo.
        Controlla: gap avanti nella corsia target >= ms-1, gap dietro >= 1.

        Non eseguito dentro l'incrocio.
        Ritorna True se il cambio e' avvenuto.
        """
        if car.in_inter:
            return False

        gap = self.gap_ahead(car.r, car.c, car.dr, car.dc, occ, obs_s, set())
        if gap >= car.ms:
            return False   # strada libera, nessun incentivo

        geo = self.geo
        if car.dc != 0:   # auto orizzontale
            candidates = [(car.r + 1, car.c), (car.r - 1, car.c)]
        else:             # auto verticale
            candidates = [(car.r, car.c + 1), (car.r, car.c - 1)]

        random.shuffle(candidates)  # evita bias sistematico

        for nr, nc in candidates:
            if not geo.in_bounds(nr, nc):
                continue
            if not geo.valid_lane_cell(nr, nc, car.dr, car.dc):
                continue
            if (nr, nc) in occ or (nr, nc) in obs_s:
                continue
            gf = self.gap_ahead(nr, nc, car.dr, car.dc, occ, obs_s, set())
            gr = self.gap_rear(nr, nc, car.dr, car.dc, occ)
            if gf < max(1, car.ms - 1) or gr < 1:
                continue

            # Esegui cambio corsia
            occ.pop((car.r, car.c), None)
            car.r  = nr
            car.c  = nc
            car.li = geo.lane_index(nr, nc, car.dr, car.dc)
            occ[(car.r, car.c)] = car
            car.frus = max(0, car.frus - 2)
            return True

        return False

    # ── Svolta all'incrocio ───────────────────────────────────────────

    def _apply_turn(self, car: Car, occ: Dict) -> bool:
        """
        Esegue la svolta prevista dall'intent quando la macchina
        raggiunge il punto di svolta nell'incrocio.

        Svolta DESTRA : alla fine dell'incrocio (lato opposto)
        Svolta SINISTRA: a meta' dell'incrocio

        Ritorna True se la svolta e' stata eseguita.
        """
        if car.turned or car.intent == "straight":
            return False

        geo = self.geo
        r, c, dr, dc = car.r, car.c, car.dr, car.dc
        intent = car.intent
        triggered = False
        nr, nc, ndr, ndc = r, c, dr, dc

        if dc == 1:    # -> (EST)
            if intent == "right" and c >= geo.ic1:
                nr = geo.ir1 + 1; nc = geo.center;     ndr = 1;  ndc = 0; triggered = True
            elif intent == "left" and c >= geo.center:
                nr = geo.ir0 - 1; nc = geo.center - 1; ndr = -1; ndc = 0; triggered = True

        elif dc == -1: # <- (OVEST)
            if intent == "right" and c <= geo.ic0:
                nr = geo.ir0 - 1; nc = geo.center - 1; ndr = -1; ndc = 0; triggered = True
            elif intent == "left" and c <= geo.center:
                nr = geo.ir1 + 1; nc = geo.center;     ndr = 1;  ndc = 0; triggered = True

        elif dr == 1:  # v (SUD)
            if intent == "right" and r >= geo.ir1:
                nr = geo.center - geo.half; nc = geo.ic0 - 1; ndr = 0; ndc = -1; triggered = True
            elif intent == "left" and r >= geo.center:
                nr = geo.center + geo.half - 1; nc = geo.ic1 + 1; ndr = 0; ndc = 1; triggered = True

        else:          # ^ (NORD)
            if intent == "right" and r <= geo.ir0:
                nr = geo.center + geo.half - 1; nc = geo.ic1 + 1; ndr = 0; ndc = 1;  triggered = True
            elif intent == "left" and r <= geo.center:
                nr = geo.center - geo.half;     nc = geo.ic0 - 1; ndr = 0; ndc = -1; triggered = True

        if triggered and geo.in_bounds(nr, nc) and (nr, nc) not in occ:
            occ.pop((car.r, car.c), None)
            car.r = nr; car.c = nc
            car.dr = ndr; car.dc = ndc
            car.turned   = True
            car.in_inter = False
            car.li = geo.lane_index(nr, nc, ndr, ndc)
            occ[(car.r, car.c)] = car
            return True

        return False

    # ── Step principale ───────────────────────────────────────────────

    def update(self):
        """
        Esegue un singolo step della simulazione.
        Modifica lo stato interno di self.cars e self.obs.
        """
        self.step += 1
        cfg  = self.cfg
        geo  = self.geo

        # Tick semaforo (passa la lista auto per ADAPTIVE)
        self.light.tick(self.cars)

        occ   = self._occ_map()
        obs_s = self._obs_set()

        # ── 1. Spawn ──────────────────────────────────────────────────
        self._spawn(occ)

        # ── 2. Incidenti stocastici ───────────────────────────────────
        dead: Set[int] = set()
        for car in self.cars:
            if random.random() < cfg.accident_prob:
                dur = random.randint(cfg.accident_dur_min, cfg.accident_dur_max)
                self.obs.append(Obstacle(car.r, car.c, dur, "incidente"))
                dead.add(car.id)
                self.total_accidents += 1

        if dead:
            for car in self.cars:
                if car.id in dead:
                    occ.pop((car.r, car.c), None)
            self.cars = [c for c in self.cars if c.id not in dead]
            obs_s = self._obs_set()

        # ── 3. Aggiornamento auto (ordine casuale) ────────────────────
        random.shuffle(self.cars)
        new_cars: List[Car] = []

        for car in self.cars:

            # a. Reaction delay
            if car.delay > 0:
                car.delay -= 1
                new_cars.append(car)
                continue

            # b. Stato incrocio e cambio corsia
            car.in_inter = geo.in_intersection(car.r, car.c)
            if not car.in_inter:
                self._try_lane_change(car, occ, obs_s)

            # Blocchi semaforo (vuoto se verde o se l'auto passa col rosso)
            rblocks = self.light.red_block_cells(car, self.step, geo)
            if rblocks and car._rr_val:
                self.total_red_runners += 1   # conta solo al primo step della decisione

            # b2. Precedenza (right-of-way): blocco virtuale per chi svolta a sinistra
            #     senza cedere la precedenza al traffico opposto.
            row_block: Set = set()
            if car.intent == "left" and not car.in_inter:
                prev_row_val = car._row_val
                prev_row_step = car._row_step
                yields = self.row_checker.should_yield(car, occ, self.step)
                if yields:
                    # Il guidatore cede: blocca l'entrata nell'incrocio
                    row_block = self.row_checker.yield_block_cell(car)
                    # Conta solo alla prima decisione di cedere (cambio False->True)
                    if not prev_row_val or prev_row_step != self.step:
                        self.total_row_yields += 1
                else:
                    # Controlla se c'era una minaccia reale ma ha scelto di ignorare
                    if (self.row_checker.is_approaching(car)
                            and self.row_checker.oncoming_threat(car, occ)
                            and car._row_step == self.step
                            and not car._row_val):
                        self.total_row_violations += 1

            # c. NaSch 1 — Accelerazione
            eff_max = min(car.ms, cfg.max_speed)
            if car.in_inter:
                eff_max = min(eff_max, cfg.inter_max_speed)
            car.spd = min(car.spd + 1, eff_max)

            # d. NaSch 2 — Frenata per ostacolo / semaforo / precedenza
            #    I tre blocchi si sommano: rosso, precedenza e ostacoli fisici.
            extra = set() if car.in_inter else (rblocks | row_block)
            gap   = self.gap_ahead(car.r, car.c, car.dr, car.dc,
                                    occ, obs_s, extra)
            car.spd = min(car.spd, gap)

            # e. NaSch 3 — Dawdling (solo fuori incrocio)
            if not car.in_inter:
                eff_dw = min(
                    car.dw + car.frus * cfg.frustration_dawdle_factor,
                    0.60,
                )
                if random.random() < eff_dw:
                    car.spd = max(0, car.spd - 1)

            # f. Velocita' minima nell'incrocio
            if car.in_inter and car.spd == 0 and gap > 0:
                car.spd = 1

            # g. Frustrazione e reaction time
            if car.spd == 0:
                car.t_stop += 1
                car.frus = min(car.frus + 1, cfg.frustration_max)
                if car.t_stop == 1:
                    car.delay = car.rt
            else:
                car.t_stop = 0
                car.frus   = max(0, car.frus - 1)

            # h. NaSch 4 — Movimento
            nr = car.r + car.dr * car.spd
            nc = car.c + car.dc * car.spd

            if not geo.in_bounds(nr, nc):
                occ.pop((car.r, car.c), None)
                continue   # uscita dalla griglia

            occ.pop((car.r, car.c), None)
            car.dist += car.spd
            car.r, car.c = nr, nc
            occ[(car.r, car.c)] = car

            # i. Svolta incrocio
            if geo.in_intersection(car.r, car.c):
                car.in_inter = True
                self._apply_turn(car, occ)

            new_cars.append(car)

        self.cars = new_cars

        # ── 4. Tick ostacoli ──────────────────────────────────────────
        self.obs = [o for o in self.obs if o.tick()]

    # ── Statistiche ───────────────────────────────────────────────────

    def stats(self) -> dict:
        """Metriche dello step corrente."""
        n   = len(self.cars)
        spd = sum(c.spd  for c in self.cars) / n if n else 0.0
        fru = sum(c.frus for c in self.cars) / n if n else 0.0
        # Auto in attesa per precedenza in questo step
        waiting_row = sum(
            1 for c in self.cars
            if c.intent == "left" and c._row_val and c._row_step == self.step
        )
        return dict(
            step          = self.step,
            cars          = n,
            obstacles     = len(self.obs),
            avg_speed     = spd,
            avg_frus      = fru,
            total_spawned = self.total_spawned,
            total_acc     = self.total_accidents,
            total_rr      = self.total_red_runners,
            total_row_vio = self.total_row_violations,
            total_row_yld = self.total_row_yields,
            waiting_row   = waiting_row,
            light_phase   = self.light.phase_label(),
        )

    # ── Render griglia ────────────────────────────────────────────────

    def render_grid(self):
        """
        Costruisce la matrice numpy [GRID_SIZE x GRID_SIZE] con valori
        interi pronti per la colormap del Renderer.

        Valori:
            0  vuoto
            1  strada
            2  incrocio
            3  auto ferma (v=0)
            4  auto lenta (v=1)
            5  auto media (v=2-3)
            6  auto veloce (v=4+)
            7  ostacolo / incidente
            8  stop line ROSSO
            9  stop line VERDE
           10  stop line GIALLO
        """
        import numpy as np
        geo = self.geo
        g   = np.zeros((geo.size, geo.size), dtype=float)

        # Strade
        g[geo.ir0:geo.ir1 + 1, :] = 1
        g[:, geo.ic0:geo.ic1 + 1] = 1
        # Incrocio (sovrascrive)
        g[geo.ir0:geo.ir1 + 1, geo.ic0:geo.ic1 + 1] = 2

        # Stop lines
        col_h, col_v = self.light.stop_line_colors()
        sl = geo.ic0 - 1; sr = geo.ic1 + 1
        st = geo.ir0 - 1; sb = geo.ir1 + 1

        if 0 <= sl < geo.size:
            g[geo.center:geo.ir1 + 1, sl] = col_h
        if 0 <= sr < geo.size:
            g[geo.ir0:geo.center, sr] = col_h
        if 0 <= st < geo.size:
            g[st, geo.center:geo.ic1 + 1] = col_v
        if 0 <= sb < geo.size:
            g[sb, geo.ic0:geo.center] = col_v

        # Ostacoli
        for o in self.obs:
            if geo.in_bounds(o.r, o.c):
                g[o.r, o.c] = 7

        # Auto
        for car in self.cars:
            if geo.in_bounds(car.r, car.c):
                if car.spd == 0:    g[car.r, car.c] = 3
                elif car.spd == 1:  g[car.r, car.c] = 4
                elif car.spd <= 3:  g[car.r, car.c] = 5
                else:               g[car.r, car.c] = 6

        return g
