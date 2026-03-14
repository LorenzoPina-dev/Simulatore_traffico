"""
infrastructure/ipr.py — Intersection Path Reservation.

Gestisce la prenotazione "slot-based" del percorso attraverso l'incrocio.
Ogni veicolo prenota il suo percorso completo prima di entrare,
garantendo l'assenza di collisioni all'interno dell'incrocio.

Responsabilità:
    - Calcolare il percorso IPR per una data manovra
    - Tentare la prenotazione (fail se celle già prenotate)
    - Aggiornare la prenotazione passo per passo
    - Rilasciare le celle già percorse
    - Anti-gridlock: timeout per auto bloccate all'uscita
    - "Don't block the box": verifica che l'uscita sia libera prima di entrare
"""
from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..agents.vehicle  import Vehicle
    from ..world.geometry  import GridGeometry
    from ..core.config     import SimConfig


_LOOKAHEAD_RESERVE  = 2   # celle prenotate in anticipo nel percorso
_EXIT_CLEARANCE     = 3   # celle da verificare dopo l'uscita
_GRIDLOCK_TIMEOUT   = 25  # step massimi di attesa all'uscita IPR


class IntersectionPathReservation:
    """
    Servizio di prenotazione del percorso attraverso l'incrocio.

    Interfaccia:
        try_enter(vehicle, occ_snap, obs_set)  → (entry_block, entered)
        advance(vehicle, occ)                  → bool (True = completato)
        release(vehicle)
    """

    def __init__(self, cfg: "SimConfig", geo: "GridGeometry"):
        self._cfg  = cfg
        self._geo  = geo
        # cell → car_id: mappa globale delle celle prenotate
        self._cell_res: Dict[Tuple[int,int], int] = {}
        # car_id → set of cells: celle prenotate da questo veicolo
        self._car_res:  Dict[int, Set[Tuple[int,int]]] = {}
        # car_id → step di attesa all'uscita
        self._exit_wait: Dict[int, int] = {}

    # ─────────────────────────────────────────────────────────────────
    # Entry
    # ─────────────────────────────────────────────────────────────────

    def try_enter(
        self,
        vehicle:   "Vehicle",
        occ_snap:  Dict,
        obs_set:   Set,
    ) -> Tuple[Set, bool]:
        """
        Tenta l'ingresso nell'incrocio.

        Returns:
            (entry_block, entered)
            entry_block : cella virtuale da bloccare se non può entrare
            entered     : True se l'ingresso è stato accettato
        """
        geo  = self._geo
        dist = self._dist_to_entry(vehicle)

        if dist <= 0:
            return set(), False

        path, ex_r, ex_c, ex_dr, ex_dc = self._compute_path(vehicle)
        if not path:
            return set(), False

        # Correggi la manovra se la direzione di uscita non è abilitata
        topo = self._cfg.topology
        if not topo.is_turn_possible(vehicle.dr, vehicle.dc, vehicle.intent):
            vehicle.intent = topo.fallback_intent(vehicle.dr, vehicle.dc, vehicle.intent)
            path, ex_r, ex_c, ex_dr, ex_dc = self._compute_path(vehicle)

        entry_cell = self._entry_cell(vehicle)

        # Se lontano dall'ingresso, non bloccare: lascia avanzare fino alla stop line
        if dist > 1:
            return set(), False

        # ── Don't block the box ───────────────────────────────────────
        if self._exit_is_blocked(ex_r, ex_c, ex_dr, ex_dc, occ_snap, obs_set):
            return {entry_cell}, False

        # Tenta la prenotazione
        ok = self._reserve(vehicle, path)
        if not ok:
            return {entry_cell}, False

        vehicle.inter_path     = path
        vehicle.inter_path_idx = 0
        vehicle.inter_exit_r   = ex_r
        vehicle.inter_exit_c   = ex_c
        vehicle.inter_exit_dr  = ex_dr
        vehicle.inter_exit_dc  = ex_dc
        return set(), True

    # ─────────────────────────────────────────────────────────────────
    # Avanzamento nel percorso
    # ─────────────────────────────────────────────────────────────────

    def advance(self, vehicle: "Vehicle", occ: Dict) -> bool:
        """
        Avanza il veicolo di un passo lungo il percorso IPR.

        Returns True quando il percorso è completato e il veicolo
        ha raggiunto la cella di uscita.
        """
        idx  = vehicle.inter_path_idx
        path = vehicle.inter_path

        if idx < len(path):
            nr, nc = path[idx]
            if occ.get((nr, nc), vehicle) is not vehicle and (nr, nc) in occ:
                return False
            occ.pop((vehicle.r, vehicle.c), None)
            vehicle.r, vehicle.c = nr, nc
            vehicle.inter_path_idx += 1
            vehicle.spd     = 1
            vehicle.v_float = 1.0
            vehicle.dist   += 1
            occ[(vehicle.r, vehicle.c)] = vehicle
            vehicle.in_inter = True
            self._release_passed(vehicle)
            self._extend_lookahead(vehicle)

        if vehicle.inter_path_idx >= len(path):
            return self._finalize(vehicle, occ)

        return False

    # ─────────────────────────────────────────────────────────────────
    # Release
    # ─────────────────────────────────────────────────────────────────

    def release(self, vehicle: "Vehicle"):
        """Rilascia tutte le celle prenotate dal veicolo."""
        reserved = self._car_res.pop(vehicle.id, set())
        for cell in reserved:
            if self._cell_res.get(cell) == vehicle.id:
                del self._cell_res[cell]
        self._exit_wait.pop(vehicle.id, None)

    def cleanup_orphans(self, live_ids: Set[int]):
        """Rimuove prenotazioni di veicoli non più presenti."""
        orphans = [cid for cid in list(self._car_res) if cid not in live_ids]
        for cid in orphans:
            reserved = self._car_res.pop(cid, set())
            for cell in reserved:
                if self._cell_res.get(cell) == cid:
                    del self._cell_res[cell]
            self._exit_wait.pop(cid, None)

    def is_gridlocked(self, vehicle_id: int) -> bool:
        return self._exit_wait.get(vehicle_id, 0) >= _GRIDLOCK_TIMEOUT

    def tick_exit_wait(self, vehicle_id: int):
        self._exit_wait[vehicle_id] = self._exit_wait.get(vehicle_id, 0) + 1

    # Debug helpers (no side effects)
    def dist_to_entry(self, vehicle: "Vehicle") -> int:
        return self._dist_to_entry(vehicle)

    def entry_cell(self, vehicle: "Vehicle") -> Tuple[int, int]:
        return self._entry_cell(vehicle)

    def exit_blocked(self, vehicle: "Vehicle", occ_snap: Dict, obs_set: Set) -> bool:
        path, ex_r, ex_c, ex_dr, ex_dc = self._compute_path(vehicle)
        if not path:
            return False
        return self._exit_is_blocked(ex_r, ex_c, ex_dr, ex_dc, occ_snap, obs_set)

    def reservation_conflict(self, vehicle: "Vehicle") -> bool:
        """True se il percorso ha celle già prenotate da altri veicoli."""
        path, _, _, _, _ = self._compute_path(vehicle)
        if not path:
            return False
        vid = vehicle.id
        for cell in path:
            owner = self._cell_res.get(cell)
            if owner is not None and owner != vid:
                return True
        return False

    # ─────────────────────────────────────────────────────────────────
    # Calcolo percorso
    # ─────────────────────────────────────────────────────────────────

    def _compute_path(self, vehicle: "Vehicle") -> Tuple:
        geo    = self._geo
        dr, dc = vehicle.dr, vehicle.dc
        intent = vehicle.intent
        ir0 = geo.ir0; ir1 = geo.ir1
        ic0 = geo.ic0; ic1 = geo.ic1

        if getattr(geo.topo, "roundabout", False):
            return self._compute_roundabout_path(vehicle)

        cells: List[Tuple[int,int]] = []
        ex_r = ex_c = ex_dr = ex_dc = 0

        def _lane_row(direction_dc: int, lane_idx: int) -> int:
            return (ir1 - lane_idx) if direction_dc == 1 else (ir0 + lane_idx)

        def _lane_col(direction_dr: int, lane_idx: int) -> int:
            return (ic0 + lane_idx) if direction_dr == 1 else (ic1 - lane_idx)

        def _exit_lane_idx() -> int:
            lanes = geo.lanes_for_direction(ex_dr, ex_dc)
            if lanes <= 0:
                return 0
            if intent == "right":
                return 0
            if intent == "left":
                return lanes - 1
            return max(0, min(vehicle.li, lanes - 1))

        if dc == 1:
            er = _lane_row(1, min(vehicle.li, geo.lanes_for_direction(0, 1) - 1))
            if intent == "straight":
                for c in range(ic0, ic1 + 1): cells.append((er, c))
                ex_dr, ex_dc = 0, 1
            elif intent == "right":
                ex_dr, ex_dc = 1, 0
                ec = _lane_col(1, _exit_lane_idx())
                for c in range(ic0, ec + 1): cells.append((er, c))
                for r in range(er + 1, ir1 + 1): cells.append((r, ec))
            else:
                ex_dr, ex_dc = -1, 0
                ec = _lane_col(-1, _exit_lane_idx())
                for c in range(ic0, ec + 1): cells.append((er, c))
                for r in range(er - 1, ir0 - 1, -1): cells.append((r, ec))

        elif dc == -1:
            er = _lane_row(-1, min(vehicle.li, geo.lanes_for_direction(0, -1) - 1))
            if intent == "straight":
                for c in range(ic1, ic0 - 1, -1): cells.append((er, c))
                ex_dr, ex_dc = 0, -1
            elif intent == "right":
                ex_dr, ex_dc = -1, 0
                ec = _lane_col(-1, _exit_lane_idx())
                for c in range(ic1, ec - 1, -1): cells.append((er, c))
                for r in range(er - 1, ir0 - 1, -1): cells.append((r, ec))
            else:
                ex_dr, ex_dc = 1, 0
                ec = _lane_col(1, _exit_lane_idx())
                for c in range(ic1, ec - 1, -1): cells.append((er, c))
                for r in range(er + 1, ir1 + 1): cells.append((r, ec))

        elif dr == 1:
            ec = _lane_col(1, min(vehicle.li, geo.lanes_for_direction(1, 0) - 1))
            if intent == "straight":
                for r in range(ir0, ir1 + 1): cells.append((r, ec))
                ex_dr, ex_dc = 1, 0
            elif intent == "right":
                ex_dr, ex_dc = 0, -1
                er = _lane_row(-1, _exit_lane_idx())
                for r in range(ir0, er + 1): cells.append((r, ec))
                for c in range(ec - 1, ic0 - 1, -1): cells.append((er, c))
            else:
                ex_dr, ex_dc = 0, 1
                er = _lane_row(1, _exit_lane_idx())
                for r in range(ir0, er + 1): cells.append((r, ec))
                for c in range(ec + 1, ic1 + 1): cells.append((er, c))

        else:  # dr == -1
            ec = _lane_col(-1, min(vehicle.li, geo.lanes_for_direction(-1, 0) - 1))
            if intent == "straight":
                for r in range(ir1, ir0 - 1, -1): cells.append((r, ec))
                ex_dr, ex_dc = -1, 0
            elif intent == "right":
                ex_dr, ex_dc = 0, 1
                er = _lane_row(1, _exit_lane_idx())
                for r in range(ir1, er - 1, -1): cells.append((r, ec))
                for c in range(ec + 1, ic1 + 1): cells.append((er, c))
            else:
                ex_dr, ex_dc = 0, -1
                er = _lane_row(-1, _exit_lane_idx())
                for r in range(ir1, er - 1, -1): cells.append((r, ec))
                for c in range(ec - 1, ic0 - 1, -1): cells.append((er, c))

        cells = [(r, c) for (r, c) in cells if geo.in_bounds(r, c)]
        ex_r, ex_c = self._exit_cell_for_lane(vehicle, ex_dr, ex_dc)
        return tuple(cells), ex_r, ex_c, ex_dr, ex_dc



    def _compute_roundabout_path(self, vehicle: "Vehicle") -> Tuple:
        """Calcola il percorso lungo l'anello della rotatoria (CCW)."""
        geo    = self._geo
        dr, dc = vehicle.dr, vehicle.dc
        intent = vehicle.intent

        ring_count = getattr(geo, "roundabout_ring_count", 0)
        if ring_count <= 0:
            return (), 0, 0, 0, 0

        # Mappa intent -> direzione uscita (come incrocio classico)
        if dc == 1:
            if intent == "straight": ex_dr, ex_dc = 0, 1
            elif intent == "right":  ex_dr, ex_dc = 1, 0
            else:                    ex_dr, ex_dc = -1, 0
        elif dc == -1:
            if intent == "straight": ex_dr, ex_dc = 0, -1
            elif intent == "right":  ex_dr, ex_dc = -1, 0
            else:                    ex_dr, ex_dc = 1, 0
        elif dr == 1:
            if intent == "straight": ex_dr, ex_dc = 1, 0
            elif intent == "right":  ex_dr, ex_dc = 0, -1
            else:                    ex_dr, ex_dc = 0, 1
        else:  # dr == -1
            if intent == "straight": ex_dr, ex_dc = -1, 0
            elif intent == "right":  ex_dr, ex_dc = 0, 1
            else:                    ex_dr, ex_dc = 0, -1

        # Bounds anello base (outer)
        rb_ir0 = geo._rb_ir0; rb_ir1 = geo._rb_ir1
        rb_ic0 = geo._rb_ic0; rb_ic1 = geo._rb_ic1

        # Seleziona corsia anello in base alla corsia di ingresso
        desired_idx = max(0, min(vehicle.li, ring_count - 1))
        entry_start = self._entry_cell(vehicle)
        if dc != 0:
            max_idx = min(entry_start[0] - rb_ir0, rb_ir1 - entry_start[0])
        else:
            max_idx = min(entry_start[1] - rb_ic0, rb_ic1 - entry_start[1])
        ring_idx = max(0, min(desired_idx, max_idx, ring_count - 1))

        # Bounds del ring selezionato
        ir0 = rb_ir0 + ring_idx; ir1 = rb_ir1 - ring_idx
        ic0 = rb_ic0 + ring_idx; ic1 = rb_ic1 - ring_idx

        def _clamp(v, lo, hi):
            return lo if v < lo else hi if v > hi else v

        # Cella di ingresso sull'anello
        if dc == 1:
            entry_ring = (_clamp(entry_start[0], ir0, ir1), ic0)
        elif dc == -1:
            entry_ring = (_clamp(entry_start[0], ir0, ir1), ic1)
        elif dr == 1:
            entry_ring = (ir0, _clamp(entry_start[1], ic0, ic1))
        else:
            entry_ring = (ir1, _clamp(entry_start[1], ic0, ic1))

        lanes_out = geo.lanes_for_direction(ex_dr, ex_dc)
        if lanes_out <= 0:
            return (), 0, 0, 0, 0
        exit_li = max(0, min(vehicle.li, lanes_out - 1))

        # Cella di uscita sull'anello
        if ex_dc == 1:
            row = _clamp(geo.ir1 - exit_li, ir0, ir1)
            exit_ring = (row, ic1)
            exit_target = (row, ic1)
        elif ex_dc == -1:
            row = _clamp(geo.ir0 + exit_li, ir0, ir1)
            exit_ring = (row, ic0)
            exit_target = (row, ic0)
        elif ex_dr == 1:
            col = _clamp(geo.ic0 + exit_li, ic0, ic1)
            exit_ring = (ir1, col)
            exit_target = (ir1, col)
        else:
            col = _clamp(geo.ic1 - exit_li, ic0, ic1)
            exit_ring = (ir0, col)
            exit_target = (ir0, col)

        ring_path = geo.roundabout_path(entry_ring, exit_ring, ring_idx=ring_idx)
        if not ring_path:
            return (), 0, 0, 0, 0

        # Connettore ingresso: entry_start -> entry_ring
        cells = []
        steps_in = abs(entry_ring[0] - entry_start[0]) + abs(entry_ring[1] - entry_start[1])
        for k in range(0, steps_in + 1):
            cells.append((entry_start[0] + dr * k, entry_start[1] + dc * k))

        # Percorso sull'anello
        if cells and ring_path[0] == cells[-1]:
            cells.extend(ring_path[1:])
        else:
            cells.extend(ring_path)

        # Connettore uscita: exit_ring -> exit_target
        steps_out = abs(exit_target[0] - exit_ring[0]) + abs(exit_target[1] - exit_ring[1])
        for k in range(1, steps_out + 1):
            cells.append((exit_ring[0] + ex_dr * k, exit_ring[1] + ex_dc * k))

        cells = [(r, c) for (r, c) in cells if geo.in_bounds(r, c)]
        ex_r, ex_c = self._exit_cell_for_lane(vehicle, ex_dr, ex_dc)
        return tuple(cells), ex_r, ex_c, ex_dr, ex_dc


    # Helper interni
    # ─────────────────────────────────────────────────────────────────

    def _dist_to_entry(self, vehicle: "Vehicle") -> int:
        geo = self._geo
        ir0, ir1, ic0, ic1 = geo.intersection_bounds()
        if vehicle.dc == 1:   return ic0 - vehicle.c
        if vehicle.dc == -1:  return vehicle.c - ic1
        if vehicle.dr == 1:   return ir0 - vehicle.r
        return vehicle.r - ir1

    def _entry_cell(self, vehicle: "Vehicle") -> Tuple[int,int]:
        geo = self._geo
        ir0, ir1, ic0, ic1 = geo.intersection_bounds()
        if vehicle.dc == 1:   return (vehicle.r, ic0)
        if vehicle.dc == -1:  return (vehicle.r, ic1)
        if vehicle.dr == 1:   return (ir0, vehicle.c)
        return (ir1, vehicle.c)

    def _exit_is_blocked(self, ex_r, ex_c, ex_dr, ex_dc, occ_snap, obs_set) -> bool:
        """
        True se l'uscita dell'incrocio è bloccata da ostacoli o da auto FERME.
        Auto in movimento (spd > 0) non contano: si sposteranno prima che
        il veicolo entrante arrivi all'uscita.
        """
        geo = self._geo
        for k in range(0, _EXIT_CLEARANCE + 1):
            cr = ex_r + ex_dr * k
            cc = ex_c + ex_dc * k
            if not geo.in_bounds(cr, cc):   break
            if geo.in_intersection(cr, cc): break
            if (cr, cc) in obs_set:         return True
            blocker = occ_snap.get((cr, cc))
            if blocker is not None and blocker.spd == 0:
                return True
        return False

    def _exit_cell_for_lane(self, vehicle: "Vehicle", ex_dr: int, ex_dc: int) -> Tuple[int, int]:
        geo = self._geo
        ir0, ir1, ic0, ic1 = geo.intersection_bounds()
        lanes = geo.lanes_for_direction(ex_dr, ex_dc)
        if lanes <= 0:
            return (vehicle.r, vehicle.c)
        li = max(0, min(vehicle.li, lanes - 1))
        if ex_dc == 1:
            return (geo.ir1 - li, ic1 + 1)
        if ex_dc == -1:
            return (geo.ir0 + li, ic0 - 1)
        if ex_dr == 1:
            return (ir1 + 1, geo.ic0 + li)
        return (ir0 - 1, geo.ic1 - li)

    def _reserve(self, vehicle: "Vehicle", path: tuple) -> bool:
        obs_s = set()   # ostacoli già verificati in try_enter
        for cell in path:
            owner = self._cell_res.get(cell)
            if owner is not None and owner != vehicle.id:
                return False
        self.release(vehicle)
        to_reserve = set(path[:_LOOKAHEAD_RESERVE])
        self._car_res[vehicle.id] = to_reserve
        for cell in to_reserve:
            self._cell_res[cell] = vehicle.id
        return True

    def _extend_lookahead(self, vehicle: "Vehicle"):
        path    = vehicle.inter_path
        idx     = vehicle.inter_path_idx
        car_res = self._car_res.setdefault(vehicle.id, set())
        end     = min(idx + _LOOKAHEAD_RESERVE, len(path))
        for i in range(idx, end):
            cell = path[i]
            if cell not in car_res:
                existing = self._cell_res.get(cell)
                if existing is None or existing == vehicle.id:
                    self._cell_res[cell] = vehicle.id
                    car_res.add(cell)

    def _release_passed(self, vehicle: "Vehicle"):
        path    = vehicle.inter_path
        idx     = vehicle.inter_path_idx
        car_res = self._car_res.get(vehicle.id, set())
        for i in range(idx - 1):
            cell = path[i]
            if self._cell_res.get(cell) == vehicle.id:
                del self._cell_res[cell]
            car_res.discard(cell)

    def _finalize(self, vehicle: "Vehicle", occ: Dict) -> bool:
        """Porta il veicolo nella cella di uscita e completa l'attraversamento."""
        geo   = self._geo
        ex_r  = vehicle.inter_exit_r
        ex_c  = vehicle.inter_exit_c

        if geo.in_bounds(ex_r, ex_c):
            if occ.get((ex_r, ex_c), vehicle) is not vehicle and (ex_r, ex_c) in occ:
                self.tick_exit_wait(vehicle.id)
                return False

            self._exit_wait.pop(vehicle.id, None)
            occ.pop((vehicle.r, vehicle.c), None)
            vehicle.r, vehicle.c = ex_r, ex_c
            vehicle.dist += 1
            occ[(vehicle.r, vehicle.c)] = vehicle
        else:
            self._exit_wait.pop(vehicle.id, None)

        vehicle.dr, vehicle.dc = vehicle.inter_exit_dr, vehicle.inter_exit_dc
        vehicle.in_inter       = False
        vehicle.turned         = True
        vehicle.li             = geo.lane_index(vehicle.r, vehicle.c, vehicle.dr, vehicle.dc)
        self.release(vehicle)
        vehicle.inter_path     = ()
        vehicle.inter_path_idx = 0
        return True
