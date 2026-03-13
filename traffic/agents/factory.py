"""
agents/factory.py — VehicleFactory: crea veicoli con i behavior corretti.

Responsabilità:
    - Selezionare il MovementBehavior giusto (IDM o NaSch)
    - Selezionare il LaneChangeBehavior (MOBIL o Heuristic)
    - Selezionare StopBehavior (BusStop o Null)
    - Selezionare PullOverBehavior (Emergency o Null)
    - Iniettare tutto nel costruttore di Vehicle

Questo è il pattern Factory + Dependency Injection:
    - Chi usa i veicoli non sa quale behavior è attivo
    - Per aggiungere un nuovo behavior basta creare una nuova classe
      e registrarla qui, senza toccare il Vehicle
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import random

from ..core.types       import VehicleType
from ..behaviors.idm    import IDMBehavior
from ..behaviors.nasch  import NaSchBehavior
from ..behaviors.mobil  import MOBILBehavior
from ..behaviors.heuristic_lane import HeuristicLaneBehavior
from ..behaviors.bus_stop       import BusStopBehavior, NullStopBehavior
from ..behaviors.emergency      import EmergencyPullOverBehavior, NullPullOverBehavior
from .vehicle import Vehicle, _assign_intent

if TYPE_CHECKING:
    from ..core.config    import SimConfig
    from ..world.geometry import GridGeometry


class VehicleFactory:
    """
    Crea istanze di Vehicle con i behavior appropriati.

    I behavior sono creati una sola volta per factory e condivisi tra
    tutti i veicoli dello stesso tipo (sono stateless).
    """

    def __init__(self, cfg: "SimConfig"):
        self._cfg = cfg

        # Movement behavior (condiviso, è stateless)
        self._movement = IDMBehavior() if cfg.use_idm else NaSchBehavior()

        # Lane change behavior
        self._lane_change = MOBILBehavior() if cfg.use_mobil else HeuristicLaneBehavior()

        # Stop behavior per tipo
        self._bus_stop = BusStopBehavior()
        self._null_stop = NullStopBehavior()

        # Pull-over behavior
        pull_over_active = cfg.emergency_pull_over_dist > 0
        self._pull_over = EmergencyPullOverBehavior() if pull_over_active else NullPullOverBehavior()
        self._null_pull_over = NullPullOverBehavior()

        # Pesi normalizzati per spawn
        weights = [p.spawn_weight for p in cfg.personalities]
        total   = sum(weights)
        self._pers_weights  = [w / total for w in weights]
        self._pers_indices  = list(range(len(cfg.personalities)))

        vw = cfg.vehicle_weights
        raw = [vw.motorcycle, vw.car, vw.van, vw.bus, vw.emergency]
        tot = sum(raw) or 1.0
        self._vtype_weights = [w / tot for w in raw]
        self._vtype_list    = list(VehicleType)

    def create(
        self,
        r: int, c: int,
        dr: int, dc: int,
        geo: "GridGeometry",
        vtype:         VehicleType = None,
        profile_index: int         = None,
    ) -> Vehicle:
        """
        Crea un nuovo veicolo con posizione, tipo e profilo specificati.
        Se non forniti, li sceglie casualmente secondo i pesi configurati.
        """
        if profile_index is None:
            profile_index = random.choices(self._pers_indices, weights=self._pers_weights)[0]
        if vtype is None:
            vtype = random.choices(self._vtype_list, weights=self._vtype_weights)[0]

        stop_behavior = self._bus_stop if vtype == VehicleType.BUS else self._null_stop
        # I veicoli di emergenza non fanno pull-over
        pull_behavior = self._null_pull_over if vtype == VehicleType.EMERGENCY else self._pull_over

        return Vehicle(
            r=r, c=c, dr=dr, dc=dc,
            profile_index=profile_index,
            cfg=self._cfg,
            geo=geo,
            vtype=vtype,
            movement=self._movement,
            lane_change=self._lane_change,
            stop=stop_behavior,
            pull_over=pull_behavior,
        )

    def random_type(self) -> VehicleType:
        return random.choices(self._vtype_list, weights=self._vtype_weights)[0]

    def random_profile(self) -> int:
        return random.choices(self._pers_indices, weights=self._pers_weights)[0]
