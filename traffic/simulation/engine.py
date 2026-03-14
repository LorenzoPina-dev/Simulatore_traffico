"""
simulation/engine.py — SimEngine: orchestratore dello step di simulazione.

Il SimEngine è un thin orchestrator: sa QUANDO chiamare i componenti,
non SA COSA fanno. Tutto il "cosa fare" è delegato a:
    - Vehicle.decide_lane_change(context)    — cambio corsia autonomo
    - Vehicle.compute_velocity(context)      — velocità autonoma
    - Vehicle.is_at_bus_stop(context)        — fermata autonoma
    - IntersectionPathReservation.advance()  — avanzamento IPR
    - Spawner, AccidentManager               — servizi dedicati

Ordine operazioni per step:
    1.  Emergency preemption semaforo
    2.  Tick semaforo
    3.  Build occ + obs_set
    4.  Spawn (via VehicleSpawner)
    5.  Incidenti (via AccidentManager)
    6.  occ_snap (snapshot per ROW e pull-over)
    7.  Ordina: veicoli IPR prima, poi per id
    8.  Per ogni veicolo:
         a) Se in transito IPR → ipr.advance() + timeout anti-gridlock
         b) Se in slip path    → avanza slip
         c) Reaction delay
         d) Aggiorna in_inter
         e) vehicle.decide_lane_change(ctx)  ← AUTONOMO
         f) Check slip lane entry
         g) Calcola extra_blocks (semaforo + ROW + IPR entry)
         h) Bus stop check → vehicle.is_at_bus_stop(ctx)  ← AUTONOMO
         i) vehicle.compute_velocity(ctx, extra_blocks)   ← AUTONOMO
         j) Discrettizza spd, applica sicurezza
         k) vehicle.update_frustration(cfg)               ← AUTONOMO
         l) Movimento fisico
         m) Aggiorna in_inter
    9.  Tick ostacoli
    10. Cleanup IPR orfane
"""
from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from ..core.config             import SimConfig, LightPolicy
from ..core.types              import VehicleType as _VehicleType
from ..world.geometry          import GridGeometry
from ..agents.vehicle          import Vehicle
from ..agents.obstacle         import Obstacle
from ..agents.factory          import VehicleFactory
from ..infrastructure.gap_calculator import GapCalculator
from ..infrastructure.ipr            import IntersectionPathReservation
from ..infrastructure.traffic_light  import TrafficLight
from ..infrastructure.right_of_way   import RightOfWayChecker
from .context                  import SimContext
from .spawner                  import VehicleSpawner
from .accident_manager         import AccidentManager
from .statistics               import SimStatistics


class SimEngine:
    """
    Orchestratore della simulazione.

    Non contiene logica di fisica, cambio corsia, semaforo o precedenza.
    Delega tutto ai componenti dedicati.
    """

    def __init__(self, cfg: SimConfig):
        self.cfg   = cfg
        self.geo   = GridGeometry(cfg)
        self.light = TrafficLight(cfg, self.geo)
        self.debug = False

        # Veicoli e ostacoli
        self.cars:     List[Vehicle]  = []
        self.obs:      List[Obstacle] = []
        self.step:     int            = 0

        # Infrastruttura
        self._gap_calc  = GapCalculator(cfg, self.geo)
        self._ipr       = IntersectionPathReservation(cfg, self.geo)
        self._row       = RightOfWayChecker(cfg, self.geo)

        # Servizi
        self._factory = VehicleFactory(cfg)
        self._spawner = VehicleSpawner(cfg, self.geo, self._factory)
        self._acc_mgr = AccidentManager(cfg, self._ipr)
        self._stats   = SimStatistics()

        # ── Controlli spawn runtime (modificabili dal renderer via bottoni) ──
        self.spawn_enabled:   bool  = True   # True = spawn attivo
        self.spawn_rate_mult: float = 1.0    # moltiplicatore frequenza [0.25 – 4.0]

        # Set per contare ogni evento UNA SOLA VOLTA per veicolo per approccio.
        # Vengono svuotati (per quel veicolo) non appena entra nell'incrocio,
        # così ogni nuova traversata viene contata come evento indipendente.
        self._rr_counted:      Set[int] = set()   # id veicoli già contati come red-runner
        self._row_vio_counted: Set[int] = set()   # id veicoli già contati come viol. ROW
        self._row_yld_counted: Set[int] = set()   # id veicoli già contati come yield ROW

        # Piazza ostacoli manuali
        for mo in cfg.manual_obstacles:
            self.obs.append(Obstacle(mo.row, mo.col, mo.duration, mo.label))

    # ─────────────────────────────────────────────────────────────────
    # STEP PRINCIPALE
    # ─────────────────────────────────────────────────────────────────

    def update(self):
        """Avanza la simulazione di un passo."""
        cfg  = self.cfg
        geo  = self.geo

        self.step += 1

        # ── 1-2. Semaforo ─────────────────────────────────────────────
        self.light.emergency_preempt(self.cars, geo)
        self.light.tick(self.cars)

        # ── 3. Build occ + obs_set ────────────────────────────────────
        occ   = {(c.r, c.c): c for c in self.cars}
        obs_s = {(o.r, o.c) for o in self.obs}

        # ── 4. Spawn ──────────────────────────────────────────────────
        spawned = self._spawner.spawn(
            self.cars, occ,
            enabled=self.spawn_enabled,
            rate_mult=self.spawn_rate_mult,
        )
        self._stats.total_spawned += spawned
        # Salva la frequenza effettiva per il grafico del renderer
        self._stats.last_spawn_rate = (
            self.cfg.spawn_prob * self.spawn_rate_mult
            if self.spawn_enabled else 0.0
        )

        # ── 5. Incidenti ──────────────────────────────────────────────
        accidents = self._acc_mgr.process(self.cars, occ, obs_s, self.obs)
        self._stats.total_accidents += accidents

        # ── 6. Snapshot (read-only per ROW + pull-over) ───────────────
        occ_snap = dict(occ)

        # ── 7. Ordina: IPR-transit prima ──────────────────────────────
        ordered = sorted(self.cars, key=lambda c: (0 if c.inter_path else 1, c.id))

        # ── 8. Loop veicoli ───────────────────────────────────────────
        context = SimContext(
            occ       = occ,
            obs_set   = obs_s,
            occ_snap  = occ_snap,
            step      = self.step,
            cfg       = cfg,
            geo       = geo,
            light     = self.light,
            gap_calc  = self._gap_calc,
            ipr       = self._ipr,
            row_checker = self._row,
        )

        new_cars: List[Vehicle] = []
        for car in ordered:
            alive = self._step_vehicle(car, context)
            if alive:
                new_cars.append(car)

        self.cars = new_cars

        # ── 9. Tick ostacoli ──────────────────────────────────────────
        self.obs = [o for o in self.obs if o.tick()]

        # ── 10. Cleanup IPR ───────────────────────────────────────────
        live_ids = {c.id for c in self.cars}
        self._ipr.cleanup_orphans(live_ids)
        # Rimuovi dai set di conteggio i veicoli usciti dalla griglia,
        # evitando accumulo di id orfani in memoria.
        self._rr_counted      &= live_ids
        self._row_vio_counted &= live_ids
        self._row_yld_counted &= live_ids

    # ─────────────────────────────────────────────────────────────────
    # STEP SINGOLO VEICOLO
    # ─────────────────────────────────────────────────────────────────

    def _step_vehicle(self, car: Vehicle, ctx: SimContext) -> bool:
        """
        Elabora un passo per un singolo veicolo.
        Restituisce True se il veicolo è ancora vivo (in griglia).
        """
        geo = ctx.geo

        # ── a) In transito IPR ────────────────────────────────────────
        if car.inter_path:
            if self._ipr.is_gridlocked(car.id):
                ctx.occ.pop((car.r, car.c), None)
                self._ipr.release(car)
                return False
            self._ipr.advance(car, ctx.occ)
            return geo.in_bounds(car.r, car.c)

        # ── b) Slip path ──────────────────────────────────────────────
        if car.slip_path:
            self._advance_slip(car, ctx)
            return geo.in_bounds(car.r, car.c)

        # ── c) Reaction delay ─────────────────────────────────────────
        if car.delay > 0:
            car.delay -= 1
            return True

        # ── d) Aggiorna in_inter ──────────────────────────────────────
        car.in_inter = geo.in_intersection(car.r, car.c)

        # ── e) Cambio corsia autonomo ─────────────────────────────────
        car.decide_lane_change(ctx)

        # ── f) Slip lane entry ────────────────────────────────────────
        if self._check_slip_entry(car, ctx):
            return True

        # ── g) Calcola extra_blocks ───────────────────────────────────
        extra = self._compute_extra_blocks(car, ctx)

        # ── h) Bus stop autonomo ──────────────────────────────────────
        at_stop = car.is_at_bus_stop(ctx)

        # ── i) Velocità autonoma (IDM o NaSch) ────────────────────────
        if at_stop:
            car.v_float = 0.0
            car.spd     = 0
        elif car.in_inter:
            # In incrocio senza IPR: mantieni velocità ridotta
            car.spd     = min(1, car.spd)
            car.v_float = float(car.spd)
        else:
            new_v = car.compute_velocity(ctx, extra)
            if ctx.cfg.use_idm:
                car.v_float = new_v
                gap = ctx.gap_calc.gap_ahead(car, ctx.occ, ctx.obs_set, extra)
                car.spd = max(0, min(round(car.v_float), gap))
            else:
                car.v_float = new_v
                car.spd     = int(new_v)

        # ── j) Safety check ───────────────────────────────────────────
        gap = ctx.gap_calc.gap_ahead(car, ctx.occ, ctx.obs_set, extra)
        car.spd = min(car.spd, gap)

        # ── j+) Emergenza: bypassa i veicoli in cedenza per calcolare la velocità reale
        # I veicoli normali che si sono fermati/spostati (pull_over=True) non devono
        # bloccare il mezzo di emergenza. Si usa una occ temporanea che li esclude.
        if car.vtype == _VehicleType.EMERGENCY and car.siren:
            occ_no_yield = {
                pos: v for pos, v in ctx.occ.items()
                if not getattr(v, 'pull_over', False)
            }
            gap_em = ctx.gap_calc.gap_ahead(car, occ_no_yield, ctx.obs_set, extra)
            em_spd = min(gap_em, car.ms)
            if em_spd > car.spd:
                car.spd     = em_spd
                car.v_float = float(em_spd)

        # ── k) Frustrazione autonoma ──────────────────────────────────
        car.update_frustration(ctx.cfg)

        # ── l) Movimento ──────────────────────────────────────────────
        if not self._move(car, ctx):
            return False

        # ── m) Aggiorna in_inter  [reset conteggi approccio] ──────────────────────────────────────
        car.in_inter = geo.in_intersection(car.r, car.c)
        # Entrato nell'incrocio: approccio concluso. Reset flag di conteggio
        # così la prossima traversata viene trattata come evento distinto.
        if car.in_inter:
            self._rr_counted.discard(car.id)
            self._row_vio_counted.discard(car.id)
            self._row_yld_counted.discard(car.id)
        return True

    # ─────────────────────────────────────────────────────────────────
    # HELPER MOVIMENTI
    # ─────────────────────────────────────────────────────────────────

    def _compute_extra_blocks(self, car: Vehicle, ctx: SimContext) -> Set:
        """
        Calcola le celle virtuali bloccate da:
            - semaforo rosso
            - precedenza ROW  (saltata per emergenze con sirena)
            - cedenza a veicoli di emergenza (solo per veicoli normali)
            - mancanza prenotazione IPR  (emergenze entrano sempre)
        """
        geo = ctx.geo
        is_siren = (car.vtype == _VehicleType.EMERGENCY and car.siren)

        # ── Semaforo ──────────────────────────────────────────────────
        # red_block_cells restituisce set() per i veicoli con sirena attiva
        extra = ctx.light.red_block_cells(car, ctx.step, geo)
        # Conta il passaggio col rosso SOLO UNA VOLTA per approccio:
        # il campionamento _rr_val è già memoizzato per step dentro red_block_cells;
        # il set _rr_counted impedisce di riaumentare il contatore ogni step successivo.
        if (not ctx.light.go_for(car)
                and car._rr_step == ctx.step
                and car._rr_val
                and car.id not in self._rr_counted):
            self._stats.total_red_runners += 1
            self._rr_counted.add(car.id)

        # ── ROW — i veicoli di emergenza con sirena ignorano la precedenza ──
        if not car.in_inter and not is_siren:
            apply_row = (ctx.cfg.light_policy == LightPolicy.NO_LIGHT or not ctx.light.go_for(car))
            if apply_row:
                if ctx.row_checker.should_yield(car, ctx.occ_snap, ctx.step):
                    extra |= ctx.row_checker.yield_block_cell(car)
                    # Conta UN SOLO yield per approccio (non uno per step di attesa)
                    if car.id not in self._row_yld_counted:
                        self._stats.total_row_yields += 1
                        self._row_yld_counted.add(car.id)
                elif (
                    car._row_step == ctx.step
                    and not car._row_val
                    and car.t_stop < 25
                    and ctx.row_checker.oncoming_threat(car, ctx.occ_snap)
                    # Conta UNA SOLA violazione per approccio
                    and car.id not in self._row_vio_counted
                ):
                    self._stats.total_row_violations += 1
                    self._row_vio_counted.add(car.id)

        # ── Cedenza emergenza: veicoli normali si spostano e si fermano ──
        # La mossa laterale (“pull right”) è già avvenuta in decide_lane_change.
        # Qui aggiungiamo il blocco sulla cella avanti per fermare il veicolo.
        if not car.in_inter and not is_siren:
            pb = car._pull_over_b
            if pb is not None and pb.should_pull_over(car, ctx):
                car.pull_over = True
                block_r = car.r + car.dr
                block_c = car.c + car.dc
                if geo.in_bounds(block_r, block_c):
                    extra.add((block_r, block_c))
            else:
                car.pull_over = False

        # ── IPR entry block — emergenze entrano sempre (ignorano rosso) ──
        light_go    = ctx.light.go_for(car)
        can_ipr     = light_go or is_siren   # sirena ⇒ bypassa semaforo rosso
        yield_cells = ctx.row_checker.yield_block_cell(car)
        if not car.in_inter and can_ipr and not (extra & yield_cells):
            entry_block, entered = self._ipr.try_enter(car, ctx.occ_snap, ctx.obs_set)
            if entered:
                self._ipr.advance(car, ctx.occ)
                return set()   # veicolo in transito, no extra blocks
            extra |= entry_block

        return extra

    def _move(self, car: Vehicle, ctx: SimContext) -> bool:
        """Muove il veicolo di spd celle nella sua direzione. True = alive."""
        geo = ctx.geo

        nr = car.r + car.dr * car.spd
        nc = car.c + car.dc * car.spd

        if not geo.in_bounds(nr, nc):
            ctx.occ.pop((car.r, car.c), None)
            return False

        # Safety: evita intrusione nell'incrocio senza IPR
        if geo.in_intersection(nr, nc) and not car.inter_path:
            nr, nc, car.spd, car.v_float = self._safe_before_box(
                car, nr, nc, ctx
            )

        ctx.occ.pop((car.r, car.c), None)
        car.dist += car.spd if (nr, nc) != (car.r, car.c) else 0
        car.r, car.c = nr, nc
        ctx.occ[(car.r, car.c)] = car
        return True

    def _safe_before_box(
        self, car: Vehicle, nr: int, nc: int, ctx: SimContext
    ) -> Tuple:
        """Blocca il veicolo prima della box se non ha prenotazione IPR."""
        geo = ctx.geo
        ir0, ir1, ic0, ic1 = geo.intersection_bounds()
        if car.dc == 1:    sr, sc = nr, ic0 - 1
        elif car.dc == -1: sr, sc = nr, ic1 + 1
        elif car.dr == 1:  sr, sc = ir0 - 1, nc
        else:              sr, sc = ir1 + 1, nc

        if geo.in_bounds(sr, sc) and (sr, sc) not in ctx.occ:
            return sr, sc, 1, 1.0

        return car.r, car.c, 0, 0.0

    def _advance_slip(self, car: Vehicle, ctx: SimContext):
        """Avanza il veicolo lungo il percorso slip lane."""
        geo = ctx.geo
        idx = car.slip_path_idx

        if idx < len(car.slip_path):
            nr, nc = car.slip_path[idx]
            if geo.in_bounds(nr, nc) and (ctx.occ.get((nr, nc), car) is car or (nr, nc) not in ctx.occ):
                ctx.occ.pop((car.r, car.c), None)
                car.r, car.c = nr, nc
                car.slip_path_idx += 1
                car.spd, car.v_float = 1, 1.0
                car.dist += 1
                ctx.occ[(car.r, car.c)] = car
        else:
            # Completata slip: ripristina direzione di uscita
            car.dr, car.dc = car.slip_exit_dr, car.slip_exit_dc
            car.slip_path      = ()
            car.slip_path_idx  = 0
            car.turned         = True
            car.in_inter       = False
            car.li             = geo.lane_index(car.r, car.c, car.dr, car.dc)

    def _check_slip_entry(self, car: Vehicle, ctx: SimContext) -> bool:
        """Controlla se il veicolo deve entrare in uno slip lane."""
        geo = ctx.geo
        if car.intent != "right" or car.in_inter or car.slip_path:
            return False
        sl = geo.check_slip_entry(car.r, car.c, car.dr, car.dc)
        if sl is None or not sl.path:
            return False
        fr, fc = sl.path[0]
        if not geo.in_bounds(fr, fc) or (fr, fc) in ctx.occ:
            return False

        ctx.occ.pop((car.r, car.c), None)
        car.r, car.c = fr, fc
        car.slip_path     = sl.path
        car.slip_path_idx = 1
        car.slip_exit_dr  = sl.exit_dr
        car.slip_exit_dc  = sl.exit_dc
        car.spd, car.v_float = 1, 1.0
        ctx.occ[(car.r, car.c)] = car
        self._stats.total_slip_uses += 1
        return True

    # ─────────────────────────────────────────────────────────────────
    # API PUBBLICA
    # ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Statistiche correnti della simulazione."""
        return self._stats.snapshot(self.cars, self.step, self.light.phase_label())

    def print_reservations(self) -> None:
        """Debug: stampa le prenotazioni IPR attive."""
        res = self._ipr._cell_res
        car_res = self._ipr._car_res
        print(f"\n[IPR @ step {self.step}] celle prenotate: {len(res)}  veicoli con res: {len(car_res)}")
        for vid, cells in car_res.items():
            car = next((c for c in self.cars if c.id == vid), None)
            pos = f"({car.r},{car.c})" if car else "(uscito)"
            print(f"  veicolo #{vid} {pos}: {sorted(cells)}")

    def render_grid(self):
        """Matrice numpy [size x size] per il renderer (valori colore)."""
        import numpy as np
        geo  = self.geo
        topo = self.cfg.topology
        g    = np.zeros((geo.size, geo.size), dtype=float)
        cr   = geo.center_r; cc = geo.center_c
        ib_ir0, ib_ir1, ib_ic0, ib_ic1 = geo.intersection_bounds()

        # Strade
        if topo.west.enabled:  g[cr : geo.ir1+1, 0 : ib_ic0] = 1
        if topo.east.enabled:  g[geo.ir0 : cr,   0 : ib_ic0] = 1
        if topo.west.enabled:  g[cr : geo.ir1+1, ib_ic1+1 : geo.size] = 1
        if topo.east.enabled:  g[geo.ir0 : cr,   ib_ic1+1 : geo.size] = 1
        if topo.north.enabled: g[0 : ib_ir0,    geo.ic0 : cc] = 1
        if topo.south.enabled: g[0 : ib_ir0,    cc : geo.ic1+1] = 1
        if topo.north.enabled: g[ib_ir1+1 : geo.size, geo.ic0 : cc] = 1
        if topo.south.enabled: g[ib_ir1+1 : geo.size, cc : geo.ic1+1] = 1

        # Incrocio / Rotatoria
        if getattr(geo, "roundabout", False) and getattr(geo, "roundabout_cells", None):
            for (r, c) in geo.roundabout_cells:
                if geo.in_bounds(r, c):
                    g[r, c] = 2
        else:
            g[geo.ir0 : geo.ir1+1, geo.ic0 : geo.ic1+1] = 2

        # Corsie dedicate
        for (r, c), intent_type in geo.dedicated_road_cells().items():
            if geo.in_bounds(r, c):
                g[r, c] = 11 if intent_type == "left" else 12

        # Slip lanes
        for (r, c) in geo.slip_visual_cells:
            if geo.in_bounds(r, c) and g[r, c] == 0:
                g[r, c] = 13

        # Stop lines
        col_h, col_v = self.light.stop_line_colors()
        sl_w = ib_ic0 - 1; sl_e = ib_ic1 + 1
        sl_n = ib_ir0 - 1; sl_s = ib_ir1 + 1
        if topo.west.enabled  and 0 <= sl_w < geo.size: g[cr : geo.ir1+1, sl_w] = col_h
        if topo.east.enabled  and 0 <= sl_e < geo.size: g[geo.ir0 : cr,   sl_e] = col_h
        if topo.north.enabled and 0 <= sl_n < geo.size: g[sl_n, geo.ic0 : cc]   = col_v
        if topo.south.enabled and 0 <= sl_s < geo.size: g[sl_s, cc : geo.ic1+1] = col_v

        # Ostacoli
        for o in self.obs:
            if geo.in_bounds(o.r, o.c):
                g[o.r, o.c] = 7

        # Veicoli non più dipinti qui:
        # il renderer disegna rettangoli dimensionati via vehicle_list()

        # Celle prenotate IPR (solo debug)
        if self.debug and self._ipr._cell_res:
            occ_pos = {(c.r, c.c) for c in self.cars if geo.in_bounds(c.r, c.c)}
            for (r, c), _vid in self._ipr._cell_res.items():
                if not geo.in_bounds(r, c):
                    continue
                g[r, c] = 20 if (r, c) in occ_pos else 19

        return g

    def vehicle_list(self) -> list:
        """
        Restituisce la lista dei veicoli per il renderer con rettangoli dimensionati.
        Ogni elemento: (r, c, vtype, pull_over, dr, dc, spd)
        """
        geo = self.geo
        return [
            (c.r, c.c, c.vtype, getattr(c, 'pull_over', False), c.dr, c.dc, c.spd)
            for c in self.cars
            if geo.in_bounds(c.r, c.c)
        ]

    def reservation_map(self) -> Dict[Tuple[int, int], int]:
        """Mappa cella->id veicolo per le prenotazioni IPR (snapshot)."""
        return dict(self._ipr._cell_res) if self.debug else {}

    def debug_entry_blocks(self) -> List[Tuple[int, int, str, int]]:
        """
        Debug: celle di ingresso bloccate con motivo (RED/ROW/EXIT/IPR/OCC/PRE).
        Ritorna lista di (r, c, reason, vehicle_id).
        """
        if not self.debug:
            return []
        occ_snap = {(c.r, c.c): c for c in self.cars}
        obs_set  = {(o.r, o.c) for o in self.obs}
        out: List[Tuple[int, int, str, int]] = []
        for car in self.cars:
            if car.in_inter or car.inter_path or car.slip_path:
                continue
            dist = self._ipr.dist_to_entry(car)
            if dist > 1:
                er, ec = self._ipr.entry_cell(car)
                out.append((er, ec, "PRE", car.id))
                continue
            er, ec = self._ipr.entry_cell(car)
            occ_car = occ_snap.get((er, ec))
            if occ_car is not None and occ_car is not car:
                out.append((er, ec, "OCC", car.id))
                continue
            if not self.light.go_for(car):
                out.append((er, ec, "RED", car.id))
                continue
            if self._row.should_yield(car, occ_snap, self.step):
                out.append((er, ec, "ROW", car.id))
                continue
            if self._ipr.exit_blocked(car, occ_snap, obs_set):
                out.append((er, ec, "EXIT", car.id))
                continue
            if self._ipr.reservation_conflict(car):
                out.append((er, ec, "IPR", car.id))
                continue
        return out

    def debug_stop_reasons(self) -> List[Tuple[int, int, str, int]]:
        """
        Debug: veicoli fermi con motivo principale (RED/ROW/EXIT/IPR/OCC/PRE/SAFE/DELAY).
        Ritorna lista di (r, c, reason, vehicle_id).
        """
        if not self.debug:
            return []
        occ_snap = {(c.r, c.c): c for c in self.cars}
        obs_set  = {(o.r, o.c) for o in self.obs}
        out: List[Tuple[int, int, str, int]] = []
        for car in self.cars:
            if car.spd != 0:
                continue
            if car.delay > 0:
                out.append((car.r, car.c, "DELAY", car.id))
                continue
            if car.inter_path or car.slip_path:
                continue
            if not self.light.go_for(car):
                out.append((car.r, car.c, "RED", car.id))
                continue
            if self._row.should_yield(car, occ_snap, self.step):
                out.append((car.r, car.c, "ROW", car.id))
                continue
            dist = self._ipr.dist_to_entry(car)
            if dist > 1:
                out.append((car.r, car.c, "PRE", car.id))
                continue
            er, ec = self._ipr.entry_cell(car)
            occ_car = occ_snap.get((er, ec))
            if occ_car is not None and occ_car is not car:
                out.append((car.r, car.c, "OCC", car.id))
                continue
            if self._ipr.exit_blocked(car, occ_snap, obs_set):
                out.append((car.r, car.c, "EXIT", car.id))
                continue
            if self._ipr.reservation_conflict(car):
                out.append((car.r, car.c, "IPR", car.id))
                continue
            out.append((car.r, car.c, "SAFE", car.id))
        return out


# Alias per backward-compat con il vecchio nome
Sim = SimEngine
