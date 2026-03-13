"""agents/platoon.py — Gestione dei convogli coordinati."""
from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .vehicle import Vehicle


class Platoon:
    """
    Gruppo di veicoli in convoglio coordinato.

    Il leader mantiene la velocità IDM normale.
    I follower copiano la velocità del veicolo immediatamente davanti
    con gap target ridotto, ottenendo un convoglio compatto.

    Formazione:
        Solo veicoli CAR, MOTORCYCLE, VAN (non BUS né EMERGENCY).
        Velocità e direzione simili, distanza ≤ 3 celle.

    Scioglimento:
        Se gap supera platoon_max_gap, il legame viene sciolto.
    """

    _next_id: int = 0

    def __init__(self, leader: "Vehicle"):
        Platoon._next_id += 1
        self.id         = Platoon._next_id
        self.leader_id  = leader.id
        self.member_ids: List[int] = [leader.id]

        leader.platoon_id   = self.id
        leader.platoon_role = "leader"

    def add_follower(self, vehicle: "Vehicle", gap: int = 1) -> None:
        self.member_ids.append(vehicle.id)
        vehicle.platoon_id        = self.id
        vehicle.platoon_role      = "follower"
        vehicle.platoon_leader_id = self.leader_id
        vehicle.platoon_gap       = gap

    def remove_member(self, vehicle_id: int) -> None:
        self.member_ids = [m for m in self.member_ids if m != vehicle_id]

    def is_dissolved(self) -> bool:
        return len(self.member_ids) <= 1

    def size(self) -> int:
        return len(self.member_ids)

    def __repr__(self) -> str:
        return (
            f"Platoon(id={self.id}, leader={self.leader_id}, "
            f"members={self.member_ids})"
        )
