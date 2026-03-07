"""
Simulatore Traffico Urbano - Incrocio a + con Semaforo
Modello: Nagel-Schreckenberg esteso

Strade: 2 assi (H e V) che formano un incrocio a +
Corsie: NUM_LANES per senso di marcia (es. 3 -> 6 corsie totali per asse)

Regole di corsia all'incrocio:
  Corsia destra  (lane_idx=0): dritto o svolta a destra
  Corsia centrale(lane_idx=1): dritto o svolta a sinistra
  Corsia sinistra(lane_idx=2): svolta a sinistra o dritto

Comportamenti guidatori:
  - Personalita': CAUTIOUS, NORMAL, AGGRESSIVE, RUSHER
  - Semaforo: possibilita' di passare col rosso (dipende dalla personalita')
  - Regole corsia: possibilita' di ignorarle (guidatori pericolosi)
  - Sorpassi, incidenti, frustrazione, reaction time
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as mpatches
import random
from enum import IntEnum
from typing import List, Optional, Dict, Set
from matplotlib.colors import ListedColormap

# =====================================================================
# CONFIGURAZIONE
# =====================================================================

GRID_SIZE  = 90       # dimensione griglia quadrata (celle)
NUM_LANES  = 3        # corsie per senso di marcia
MAX_SPEED  = 4        # velocita' massima globale (celle/step)
STEPS      = 600      # frame totali animazione
INTERVAL   = 80       # millisecondi tra frame
SPAWN_PROB = 0.32     # prob. spawn auto per corsia per step

LIGHT_GREEN  = 45     # step fase verde per direzione
LIGHT_YELLOW = 6      # step fase gialla

BASE_ACCIDENT_PROB = 0.00045   # probabilita' incidente per auto per step
ACC_DUR_MIN = 12
ACC_DUR_MAX = 55

OUTPUT_FILE = "traffic_simulation_intersection.gif"

# ── Geometria ─────────────────────────────────────────────────────────
CENTER = GRID_SIZE // 2
HALF   = NUM_LANES

# Bounds incrocio (rows e cols che formano la zona a +)
IR0 = CENTER - HALF        # prima riga incrocio
IR1 = CENTER + HALF - 1    # ultima riga incrocio
IC0 = CENTER - HALF        # prima col incrocio
IC1 = CENTER + HALF - 1    # ultima col incrocio

# =====================================================================
# PERSONALITA' GUIDATORI
# =====================================================================

class P(IntEnum):
    CAUTIOUS   = 0   # prudente
    NORMAL     = 1   # normale
    AGGRESSIVE = 2   # aggressivo
    RUSHER     = 3   # frettoloso / spericolato

# ms=max_speed, dw=dawdle, rt=react_time, rr=run_red, il=ignore_lane
CFG = {
    P.CAUTIOUS:   dict(ms=2, dw=0.28, rt=3, rr=0.02, il=0.03),
    P.NORMAL:     dict(ms=3, dw=0.12, rt=1, rr=0.05, il=0.08),
    P.AGGRESSIVE: dict(ms=4, dw=0.04, rt=0, rr=0.28, il=0.40),
    P.RUSHER:     dict(ms=5, dw=0.02, rt=0, rr=0.58, il=0.68),
}
PW = [10, 55, 25, 10]   # pesi spawn personalita'

# =====================================================================
# FUNZIONI HELPER GEOMETRICHE
# =====================================================================

def in_inter(r, c):
    """True se la cella e' nella zona incrocio."""
    return IR0 <= r <= IR1 and IC0 <= c <= IC1


def on_road(r, c):
    """True se la cella appartiene a una qualsiasi strada."""
    on_h = IR0 <= r <= IR1
    on_v = IC0 <= c <= IC1
    return on_h or on_v


def lane_idx(r, c, dr, dc):
    """
    Indice di corsia relativo alla direzione di marcia.
      0  = corsia destra  (lenta, svolta destra)
      ... 
      N-1= corsia sinistra(veloce, svolta sinistra)
    """
    if dc == 1:   return (CENTER + HALF - 1) - r   # vai DESTRA: r=C+H-1 -> 0
    if dc == -1:  return r - (CENTER - HALF)        # vai SINISTRA: r=C-H -> 0
    if dr == 1:   return c - CENTER                 # vai GIU': c=C -> 0
    if dr == -1:  return (CENTER - 1) - c           # vai SU': c=C-1 -> 0
    return 0


def assign_intent(li, cfg):
    """
    Assegna turn_intent in base alla corsia (li) e alla personalita'.
    I guidatori pericolosi (AGGRESSIVE/RUSHER) possono ignorare le regole.
    """
    if random.random() < cfg['il']:
        # Ignora regola di corsia: scelta casuale
        return random.choices(['straight', 'right', 'left'], [50, 25, 25])[0]
    if HALF == 1:
        return random.choices(['straight', 'right', 'left'], [50, 25, 25])[0]
    if li == 0:           # corsia destra -> dritto o destra
        return random.choices(['straight', 'right'], [60, 40])[0]
    if li == HALF - 1:    # corsia sinistra -> dritto o sinistra
        return random.choices(['straight', 'left'], [55, 45])[0]
    return random.choices(['straight', 'left'], [68, 32])[0]  # corsie centrali


def turn_right_dir(dr, dc):
    """Restituisce la direzione dopo una svolta a destra."""
    # destra rispetto alla direzione di marcia
    if dc == 1:  return 1,  0   # -> vado giu'
    if dc == -1: return -1, 0   # <- vado su
    if dr == 1:  return 0,  -1  # v vado sinistra
    return 0, 1                  # ^ vado destra


def turn_left_dir(dr, dc):
    """Restituisce la direzione dopo una svolta a sinistra."""
    if dc == 1:  return -1, 0   # -> vado su
    if dc == -1: return 1,  0   # <- vado giu'
    if dr == 1:  return 0,  1   # v vado destra
    return 0, -1                 # ^ vado sinistra


# =====================================================================
# CLASSI
# =====================================================================

class Car:
    _nid = 0

    def __init__(self, r, c, dr, dc, pers):
        Car._nid += 1
        self.id   = Car._nid
        self.r    = r
        self.c    = c
        self.dr   = dr   # direzione riga:  -1=su,  0=orizontale, +1=giu'
        self.dc   = dc   # direzione colonna: -1=sx, 0=verticale,  +1=dx
        self.pers = pers

        cf = CFG[pers]
        self.ms    = cf['ms']   # max speed personale
        self.dw    = cf['dw']   # dawdle probability
        self.rt    = cf['rt']   # reaction time (steps)
        self.rr    = cf['rr']   # run-red probability
        self.il    = cf['il']   # ignore-lane probability

        self.spd        = 1
        self.delay      = 0
        self.frus       = 0     # frustrazione [0-20]
        self.t_stop     = 0     # step consecutivi a velocita' 0
        self.dist       = 0     # distanza totale percorsa

        self.li         = lane_idx(r, c, dr, dc)
        self.intent     = assign_intent(self.li, cf)
        self.in_inter   = False
        self.turned     = False  # gia' eseguito il cambio direzione

        # Caching decisione passaggio col rosso (una volta per step)
        self._rr_val    = False
        self._rr_step   = -1


class Obstacle:
    def __init__(self, r, c, dur):
        self.r = r; self.c = c; self.dur = dur
    def tick(self):
        self.dur -= 1
        return self.dur > 0


class TrafficLight:
    """
    Ciclo semaforo:
      fase 0: H verde / V rosso   (LIGHT_GREEN steps)
      fase 1: giallo               (LIGHT_YELLOW steps)
      fase 2: H rosso / V verde   (LIGHT_GREEN steps)
      fase 3: giallo               (LIGHT_YELLOW steps)
    """
    def __init__(self):
        self._t = 0
        self._period = 2 * LIGHT_GREEN + 2 * LIGHT_YELLOW

    def tick(self):
        self._t = (self._t + 1) % self._period

    def _phase(self):
        t = self._t
        if t < LIGHT_GREEN:
            return 'HG'
        if t < LIGHT_GREEN + LIGHT_YELLOW:
            return 'Y'
        if t < 2 * LIGHT_GREEN + LIGHT_YELLOW:
            return 'VG'
        return 'Y'

    def h_go(self):   return self._phase() == 'HG'
    def v_go(self):   return self._phase() == 'VG'
    def yellow(self): return self._phase() == 'Y'

    def phase_label(self):
        ph = self._phase()
        if ph == 'HG': return 'H:VERDE  V:ROSSO'
        if ph == 'VG': return 'H:ROSSO  V:VERDE'
        return 'GIALLO'

    def h_timer(self):
        """Step rimanenti per H-verde (0 se non in H-verde)."""
        if self.h_go():
            return LIGHT_GREEN - self._t
        return 0

    def v_timer(self):
        if self.v_go():
            return (2 * LIGHT_GREEN + LIGHT_YELLOW) - self._t
        return 0


# =====================================================================
# SIMULAZIONE
# =====================================================================

class Sim:
    def __init__(self):
        self.cars:  List[Car]      = []
        self.obs:   List[Obstacle] = []
        self.light  = TrafficLight()
        self.step   = 0

        self.total_spawned      = 0
        self.total_accidents    = 0
        self.total_red_runners  = 0

    # ── Mappe di supporto ─────────────────────────────────────────────
    def occ_map(self) -> Dict:
        return {(car.r, car.c): car for car in self.cars}

    def obs_set(self) -> Set:
        return {(o.r, o.c) for o in self.obs}

    # ── Gap ──────────────────────────────────────────────────────────
    def gap_ahead(self, r, c, dr, dc, occ, obs_s, extra_blocks,
                  lookahead=MAX_SPEED + 3) -> int:
        for d in range(1, lookahead + 1):
            nr = r + dr * d
            nc = c + dc * d
            if nr < 0 or nr >= GRID_SIZE or nc < 0 or nc >= GRID_SIZE:
                return lookahead
            if (nr, nc) in occ:          return d - 1
            if (nr, nc) in obs_s:        return d - 1
            if (nr, nc) in extra_blocks: return d - 1
        return lookahead

    def gap_rear(self, r, c, dr, dc, occ, lookbehind=MAX_SPEED + 2) -> int:
        for d in range(1, lookbehind + 1):
            nr = r - dr * d
            nc = c - dc * d
            if nr < 0 or nr >= GRID_SIZE or nc < 0 or nc >= GRID_SIZE:
                return lookbehind
            if (nr, nc) in occ: return d - 1
        return lookbehind

    # ── Blocchi semaforo rosso ────────────────────────────────────────
    def red_blocks(self, car) -> Set:
        """
        Restituisce le celle bloccate dal semaforo rosso per questa auto.
        I guidatori spericolati possono decidere di ignorarlo.
        """
        is_h  = (car.dc != 0)
        go    = self.light.h_go() if is_h else self.light.v_go()
        if go:
            return set()

        # Decide una volta per step se passare col rosso
        if car._rr_step != self.step:
            car._rr_step = self.step
            car._rr_val  = (random.random() < car.rr)
            if car._rr_val:
                self.total_red_runners += 1

        if car._rr_val:
            return set()  # passa col rosso!

        # Blocca una cella PRIMA della stop line, cosi' la stop line rimane visibile
        if car.dc == 1:  return {(car.r, IC0 - 1)}   # ->  ferma a IC0-2, stop line a IC0-1
        if car.dc == -1: return {(car.r, IC1 + 1)}   # <-  ferma a IC1+2, stop line a IC1+1
        if car.dr == 1:  return {(IR0 - 1, car.c)}   # v   ferma a IR0-2, stop line a IR0-1
        return {(IR1 + 1, car.c)}                     # ^   ferma a IR1+2, stop line a IR1+1

    # ── Cambio corsia ─────────────────────────────────────────────────
    def valid_lane_row_col(self, r, c, dr, dc) -> bool:
        """True se (r,c) e' una corsia valida per la direzione (dr,dc)."""
        if dc == 1:  return CENTER <= r <= IR1
        if dc == -1: return IR0 <= r < CENTER
        if dr == 1:  return CENTER <= c <= IC1
        if dr == -1: return IC0 <= c < CENTER
        return False

    def try_lane_change(self, car, occ, obs_s) -> bool:
        """
        Tenta un sorpasso/cambio corsia fuori dall'incrocio.
        Controlla sicurezza (gap avanti e dietro nella corsia target).
        """
        if car.in_inter:
            return False

        gap = self.gap_ahead(car.r, car.c, car.dr, car.dc, occ, obs_s, set())
        if gap >= car.ms:
            return False  # strada libera, non serve cambiare

        if car.dc != 0:  # orizzontale
            candidates = [(car.r + 1, car.c), (car.r - 1, car.c)]
        else:            # verticale
            candidates = [(car.r, car.c + 1), (car.r, car.c - 1)]

        random.shuffle(candidates)

        for nr, nc in candidates:
            if nr < 0 or nr >= GRID_SIZE or nc < 0 or nc >= GRID_SIZE:
                continue
            if not self.valid_lane_row_col(nr, nc, car.dr, car.dc):
                continue
            if (nr, nc) in occ or (nr, nc) in obs_s:
                continue
            gf = self.gap_ahead(nr, nc, car.dr, car.dc, occ, obs_s, set())
            gr = self.gap_rear(nr, nc, car.dr, car.dc, occ)
            # Sicurezza: gap sufficiente avanti e dietro
            if gf < max(1, car.ms - 1) or gr < 1:
                continue
            # Esegui cambio corsia
            occ.pop((car.r, car.c), None)
            car.r = nr
            car.c = nc
            car.li = lane_idx(car.r, car.c, car.dr, car.dc)
            occ[(car.r, car.c)] = car
            car.frus = max(0, car.frus - 2)
            return True

        return False

    # ── Spawn ─────────────────────────────────────────────────────────
    def spawn(self, occ):
        # Punti di spawn: bordi della griglia per ogni corsia/direzione
        entries = []
        for r in range(CENTER, IR1 + 1):          # corsie ->
            entries.append((r, 0,             0,  1))
        for r in range(IR0, CENTER):              # corsie <-
            entries.append((r, GRID_SIZE - 1, 0, -1))
        for c in range(CENTER, IC1 + 1):          # corsie v
            entries.append((0, c,             1,  0))
        for c in range(IC0, CENTER):              # corsie ^
            entries.append((GRID_SIZE - 1, c, -1, 0))

        for r, c, dr, dc in entries:
            if random.random() < SPAWN_PROB:
                if (r, c) not in occ:
                    pers = random.choices(list(P), weights=PW)[0]
                    car  = Car(r, c, dr, dc, pers)
                    self.cars.append(car)
                    occ[(r, c)] = car
                    self.total_spawned += 1

    # ── Logica svolta incrocio ────────────────────────────────────────
    def apply_turn(self, car, occ) -> bool:
        """
        Controlla se la macchina ha raggiunto il punto di svolta.
        Se si', aggiorna posizione e direzione.
        Svolta DESTRA: alla fine dell'incrocio (lato opposto).
        Svolta SINISTRA: a meta' dell'incrocio (meno invasiva).
        """
        if car.turned or car.intent == 'straight':
            return False

        r, c, dr, dc = car.r, car.c, car.dr, car.dc
        intent = car.intent
        triggered = False

        # Coordinate di uscita (target dopo la svolta)
        nr, nc, ndr, ndc = r, c, dr, dc

        if dc == 1:    # va DESTRA ->
            if intent == 'right' and c >= IC1:
                # Esce a sud, corsia destra di giu' = col=CENTER (lane_idx=0)
                nr = IR1 + 1; nc = CENTER; ndr = 1; ndc = 0; triggered = True
            elif intent == 'left' and c >= CENTER:
                # Esce a nord, corsia destra di su' = col=CENTER-1 (lane_idx=0)
                nr = IR0 - 1; nc = CENTER - 1; ndr = -1; ndc = 0; triggered = True

        elif dc == -1: # va SINISTRA <-
            if intent == 'right' and c <= IC0:
                nr = IR0 - 1; nc = CENTER - 1; ndr = -1; ndc = 0; triggered = True
            elif intent == 'left' and c <= CENTER:
                nr = IR1 + 1; nc = CENTER;     ndr =  1; ndc = 0; triggered = True

        elif dr == 1:  # va GIU' v
            if intent == 'right' and r >= IR1:
                # Esce a ovest, corsia destra di <- = row=CENTER-HALF (lane_idx=0)
                nr = CENTER - HALF; nc = IC0 - 1; ndr = 0; ndc = -1; triggered = True
            elif intent == 'left' and r >= CENTER:
                # Esce a est, corsia destra di -> = row=CENTER+HALF-1 (lane_idx=0)
                nr = CENTER + HALF - 1; nc = IC1 + 1; ndr = 0; ndc = 1; triggered = True

        else:          # va SU' ^
            if intent == 'right' and r <= IR0:
                nr = CENTER + HALF - 1; nc = IC1 + 1; ndr = 0; ndc =  1; triggered = True
            elif intent == 'left' and r <= CENTER:
                nr = CENTER - HALF;     nc = IC0 - 1; ndr = 0; ndc = -1; triggered = True

        if triggered:
            if (0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE
                    and (nr, nc) not in occ):
                occ.pop((car.r, car.c), None)
                car.r = nr; car.c = nc
                car.dr = ndr; car.dc = ndc
                car.turned   = True
                car.in_inter = False
                car.li = lane_idx(nr, nc, ndr, ndc)
                occ[(car.r, car.c)] = car
                return True
        return False

    # ── Step principale ───────────────────────────────────────────────
    def update(self):
        self.step += 1
        self.light.tick()

        occ   = self.occ_map()
        obs_s = self.obs_set()

        # 1. Spawn
        self.spawn(occ)

        # 2. Incidenti stocastici
        dead = set()
        for car in self.cars:
            if random.random() < BASE_ACCIDENT_PROB:
                self.obs.append(
                    Obstacle(car.r, car.c,
                             random.randint(ACC_DUR_MIN, ACC_DUR_MAX)))
                dead.add(car.id)
                self.total_accidents += 1
        if dead:
            for cid in dead:
                co = next((x for x in self.cars if x.id == cid), None)
                if co:
                    occ.pop((co.r, co.c), None)
            self.cars = [c for c in self.cars if c.id not in dead]
            obs_s = self.obs_set()

        # 3. Aggiornamento auto
        random.shuffle(self.cars)   # evita bias nell'ordine
        new_cars = []

        for car in self.cars:

            # ── Reaction delay ────────────────────────────────────
            if car.delay > 0:
                car.delay -= 1
                new_cars.append(car)
                continue

            # ── Flag in_intersection ──────────────────────────────
            car.in_inter = in_inter(car.r, car.c)

            # ── Sorpasso / cambio corsia (solo fuori incrocio) ────
            if not car.in_inter:
                self.try_lane_change(car, occ, obs_s)

            # ── Blocchi semaforo rosso ────────────────────────────
            rblocks = self.red_blocks(car)

            # ── NaSch 1: Accelerazione ────────────────────────────
            eff_max = min(car.ms, MAX_SPEED)
            if car.in_inter:
                eff_max = min(eff_max, 2)  # velocita' moderata in incrocio
            car.spd = min(car.spd + 1, eff_max)

            # ── NaSch 2: Frenata per ostacolo ─────────────────────
            # Dentro l'incrocio ignoriamo i blocchi semaforo (gia' passato)
            # e consideriamo solo ostacoli fisici reali (altre auto, incidenti)
            if car.in_inter:
                gap = self.gap_ahead(car.r, car.c, car.dr, car.dc,
                                      occ, obs_s, set())   # NO rblocks dentro l'incrocio
            else:
                gap = self.gap_ahead(car.r, car.c, car.dr, car.dc,
                                      occ, obs_s, rblocks)
            car.spd = min(car.spd, gap)

            # ── NaSch 3: Dawdling / distrazione ───────────────────
            # NON applicare dawdling dentro l'incrocio: chi e' gia' dentro
            # NON si ferma casualmente, altrimenti intasa l'incrocio.
            if not car.in_inter:
                eff_dw = min(car.dw + car.frus * 0.02, 0.60)
                if random.random() < eff_dw:
                    car.spd = max(0, car.spd - 1)

            # Dentro l'incrocio: velocita' minima garantita a 1
            # (a meno che non ci sia un ostacolo fisico immediatamente davanti)
            if car.in_inter and car.spd == 0 and gap > 0:
                car.spd = 1

            # ── Frustrazione e reaction time ──────────────────────
            if car.spd == 0:
                car.t_stop += 1
                car.frus = min(car.frus + 1, 20)
                if car.t_stop == 1:
                    car.delay = car.rt
            else:
                car.t_stop = 0
                car.frus   = max(0, car.frus - 1)

            # ── NaSch 4: Movimento ────────────────────────────────
            nr = car.r + car.dr * car.spd
            nc = car.c + car.dc * car.spd

            # Uscita dalla griglia -> rimuovi auto
            if nr < 0 or nr >= GRID_SIZE or nc < 0 or nc >= GRID_SIZE:
                occ.pop((car.r, car.c), None)
                continue

            occ.pop((car.r, car.c), None)
            car.dist += car.spd
            car.r = nr
            car.c = nc
            occ[(car.r, car.c)] = car

            # ── Svolta in incrocio ────────────────────────────────
            if in_inter(car.r, car.c):
                car.in_inter = True
                self.apply_turn(car, occ)

            new_cars.append(car)

        self.cars = new_cars

        # 4. Tick ostacoli
        self.obs = [o for o in self.obs if o.tick()]

    # ── Render ───────────────────────────────────────────────────────
    def render(self) -> np.ndarray:
        """
        Valori cella per la colormap:
          0  vuoto (erba/marciapiede)
          1  strada (asfalto)
          2  incrocio (asfalto chiaro)
          3  auto ferma        (speed = 0)
          4  auto lenta        (speed = 1)
          5  auto media        (speed = 2-3)
          6  auto veloce       (speed = 4+)
          7  incidente/ostacolo
          8  stop line ROSSO   (semaforo rosso)
          9  stop line VERDE   (semaforo verde)
         10  stop line GIALLO  (fase gialla)
        """
        g = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)

        # ── Strade ────────────────────────────────────────────────
        for r in range(IR0, IR1 + 1):
            g[r, :] = 1
        for c in range(IC0, IC1 + 1):
            g[:, c] = 1
        # Incrocio (sovrascrive)
        for r in range(IR0, IR1 + 1):
            for c in range(IC0, IC1 + 1):
                g[r, c] = 2

        # ── Stop lines (indicatori semaforo) ──────────────────────
        sl = IC0 - 1    # stop line per ->
        sr = IC1 + 1    # stop line per <-
        st = IR0 - 1    # stop line per v
        sb = IR1 + 1    # stop line per ^

        ph = self.light._phase()
        if ph == 'HG':
            sv_h = 9; sv_v = 8   # H verde, V rosso
        elif ph == 'VG':
            sv_h = 8; sv_v = 9   # H rosso, V verde
        else:
            sv_h = 10; sv_v = 10  # giallo per tutti

        # Stop line orizzontale (sx di -> e dx di <-)
        if 0 <= sl < GRID_SIZE:
            for r in range(CENTER, IR1 + 1): g[r, sl] = sv_h
        if 0 <= sr < GRID_SIZE:
            for r in range(IR0, CENTER):     g[r, sr] = sv_h
        # Stop line verticale (sopra v e sotto ^)
        if 0 <= st < GRID_SIZE:
            for c in range(CENTER, IC1 + 1): g[st, c] = sv_v
        if 0 <= sb < GRID_SIZE:
            for c in range(IC0, CENTER):     g[sb, c] = sv_v

        # ── Ostacoli / incidenti ───────────────────────────────────
        for o in self.obs:
            if 0 <= o.r < GRID_SIZE and 0 <= o.c < GRID_SIZE:
                g[o.r, o.c] = 7

        # ── Auto (sovrascrivono tutto il resto) ───────────────────
        for car in self.cars:
            if 0 <= car.r < GRID_SIZE and 0 <= car.c < GRID_SIZE:
                if car.spd == 0:   g[car.r, car.c] = 3
                elif car.spd == 1: g[car.r, car.c] = 4
                elif car.spd <= 3: g[car.r, car.c] = 5
                else:              g[car.r, car.c] = 6

        return g

    def stats(self) -> dict:
        n = len(self.cars)
        ac = len(self.obs)
        spd = sum(c.spd  for c in self.cars) / n if n else 0
        fru = sum(c.frus for c in self.cars) / n if n else 0
        return dict(n=n, ac=ac, spd=spd, fru=fru)


# =====================================================================
# SETUP VISUALIZZAZIONE
# =====================================================================

PALETTE = [
    "#0f1117",   #  0  vuoto (erba/marciapiede)
    "#2a3a4a",   #  1  strada
    "#3a5060",   #  2  incrocio
    "#e63946",   #  3  auto ferma
    "#f4a261",   #  4  auto lenta
    "#ffd166",   #  5  auto media
    "#06d6a0",   #  6  auto veloce
    "#b548c6",   #  7  incidente/ostacolo
    "#ff2020",   #  8  stop line rosso
    "#20ff20",   #  9  stop line verde
    "#ffc300",   # 10  stop line giallo
]

LEGEND = [
    "Vuoto",
    "Strada",
    "Incrocio",
    "Auto ferma  (v=0)",
    "Auto lenta  (v=1)",
    "Auto media  (v=2-3)",
    "Auto veloce (v=4+)",
    "Incidente",
    "Stop: ROSSO",
    "Stop: VERDE",
    "Stop: GIALLO",
]

sim  = Sim()
cmap = ListedColormap(PALETTE)

fig, (ax, ax_s) = plt.subplots(
    2, 1,
    figsize=(10, 11),
    gridspec_kw={'height_ratios': [9, 2]},
)
fig.patch.set_facecolor("#0a0a12")

# ── Pannello principale ──────────────────────────────────────────────
ax.set_facecolor("#0a0a12")
im = ax.imshow(
    sim.render(), cmap=cmap, vmin=0, vmax=10,
    aspect='equal', interpolation='nearest',
)

# Linee divisorie tra corsie
ax.axhline(y=CENTER - 0.5, color='#ffffffcc', linewidth=1.5)   # divid. H
ax.axvline(x=CENTER - 0.5, color='#ffffffcc', linewidth=1.5)   # divid. V

for i in range(1, HALF):
    ax.axhline(y=CENTER + i - 0.5, color='white', linewidth=0.5,
               linestyle='--', alpha=0.35)
    ax.axhline(y=CENTER - HALF + i - 0.5, color='white', linewidth=0.5,
               linestyle='--', alpha=0.35)
    ax.axvline(x=CENTER + i - 0.5, color='white', linewidth=0.5,
               linestyle='--', alpha=0.35)
    ax.axvline(x=CENTER - HALF + i - 0.5, color='white', linewidth=0.5,
               linestyle='--', alpha=0.35)

# Bordi incrocio
for delta in (IC0 - 0.5, IC1 + 0.5):
    ax.axvline(x=delta, color='#ffffff50', linewidth=0.8)
for delta in (IR0 - 0.5, IR1 + 0.5):
    ax.axhline(y=delta, color='#ffffff50', linewidth=0.8)

# Etichette assi
ax.set_xticks([]); ax.set_yticks([])
for sp in ax.spines.values():
    sp.set_edgecolor('#333')

legend_patches = [
    mpatches.Patch(color=PALETTE[i], label=LEGEND[i])
    for i in range(len(PALETTE))
]
ax.legend(
    handles=legend_patches, loc='upper right',
    fontsize=7, ncol=3,
    facecolor='#1a1a2e', edgecolor='#444', labelcolor='white',
)

title_obj = ax.set_title(
    "Simulatore Incrocio a + | Regole corsia + Semaforo",
    color='white', fontsize=11, pad=6,
)

# ── Pannello statistiche ─────────────────────────────────────────────
ax_s.set_facecolor("#0d0d1a")
ax_s.set_xlim(0, STEPS)
ax_s.set_ylim(0, 100)
ax_s.set_ylabel("Valori normalizzati", color='#aaa', fontsize=8)
ax_s.tick_params(colors='#666', labelsize=7)
for sp in ax_s.spines.values():
    sp.set_edgecolor('#333')

_dn_hist: List[float] = []
_sp_hist: List[float] = []
_rr_hist: List[float] = []

line_dn,  = ax_s.plot([], [], color='#06d6a0', linewidth=1.2,
                       label='Auto totali / 2')
line_sp,  = ax_s.plot([], [], color='#ffd166', linewidth=1.2,
                       label='Vel.media x10')
line_rr,  = ax_s.plot([], [], color='#e63946', linewidth=1.0,
                       linestyle='--', label='Pass.rosso (cumulat./10)')
ax_s.legend(loc='upper left', fontsize=7,
            facecolor='#1a1a2e', edgecolor='#444', labelcolor='white')
ax_s.set_xlabel("Step", color='#aaa', fontsize=8)

plt.tight_layout(pad=1.2)

# =====================================================================
# LOOP DI AGGIORNAMENTO
# =====================================================================

def update_frame(frame: int):
    sim.update()
    s = sim.stats()

    im.set_array(sim.render())

    title_obj.set_text(
        f"Step {sim.step:4d}  |  "
        f"Auto: {s['n']:3d}  |  "
        f"Incidenti attivi: {s['ac']:2d}  |  "
        f"Vel.media: {s['spd']:.2f}  |  "
        f"Frustraz.: {s['fru']:.1f}  |  "
        f"Semaforo: {sim.light.phase_label()}  |  "
        f"Tot.acc.: {sim.total_accidents}  |  "
        f"Rosso passato: {sim.total_red_runners}"
    )

    _dn_hist.append(s['n'] / 2)
    _sp_hist.append(s['spd'] * 10)
    _rr_hist.append(sim.total_red_runners / 10)

    xs = list(range(len(_dn_hist)))
    line_dn.set_data(xs, _dn_hist)
    line_sp.set_data(xs, _sp_hist)
    line_rr.set_data(xs, _rr_hist)
    ax_s.set_xlim(0, max(STEPS, len(_dn_hist)))
    # Adatta asse Y se i valori crescono
    top = max(100.0, max(_rr_hist) if _rr_hist else 100)
    ax_s.set_ylim(0, top * 1.1)

    return im, title_obj, line_dn, line_sp, line_rr


# =====================================================================
# AVVIO
# =====================================================================

print("=" * 50)
print("  Simulatore Incrocio a +")
print(f"  Griglia : {GRID_SIZE}x{GRID_SIZE} celle")
print(f"  Corsie  : {NUM_LANES} per senso di marcia")
print(f"  Semaforo: verde={LIGHT_GREEN}s  giallo={LIGHT_YELLOW}s")
print(f"  Step    : {STEPS}   Spawn: {SPAWN_PROB*100:.0f}%")
print("=" * 50)

ani = animation.FuncAnimation(
    fig,
    update_frame,
    frames=STEPS,
    interval=INTERVAL,
    blit=False,
)

ani.save(OUTPUT_FILE, writer="pillow", fps=12, dpi=90)

print(f"\nSimulazione salvata in: {OUTPUT_FILE}")
print(f"  Auto totali spawned   : {sim.total_spawned}")
print(f"  Incidenti totali      : {sim.total_accidents}")
print(f"  Passaggi col rosso    : {sim.total_red_runners}")

plt.show()
