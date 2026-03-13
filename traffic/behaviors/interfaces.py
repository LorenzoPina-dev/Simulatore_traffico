"""
behaviors/interfaces.py — ABC per i comportamenti dei veicoli.

Strategy Pattern: ogni comportamento è un'interfaccia intercambiabile.
I veicoli ricevono le implementazioni concrete via dependency injection.

Gerarchia:
    MovementBehavior    — calcola la velocità target
    LaneChangeBehavior  — decide e applica i cambi di corsia
    StopBehavior        — gestisce fermate programmate (bus stop)
    PullOverBehavior    — risposta ai veicoli di emergenza
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agents.vehicle   import Vehicle
    from ..simulation.context import SimContext


class MovementBehavior(ABC):
    """
    Calcola la velocità target del veicolo in base alla situazione.

    Responsabilità:
        - Leggere gap, velocità del leader, stato del veicolo
        - Restituire la nuova v_float (velocità continua)
        - NON modificare la posizione del veicolo
    """

    @abstractmethod
    def compute_velocity(self, vehicle: "Vehicle", context: "SimContext") -> float:
        """Restituisce la nuova velocità continua [celle/step]."""

    @property
    def name(self) -> str:
        return self.__class__.__name__


class LaneChangeBehavior(ABC):
    """
    Gestisce la logica di cambio corsia.

    Responsabilità:
        - Valutare se cambiare corsia (evaluate)
        - Tentare il cambio e aggiornare occ (execute)
        - NON toccare la velocità del veicolo
    """

    @abstractmethod
    def evaluate(self, vehicle: "Vehicle", context: "SimContext") -> int:
        """
        Direzione preferita:
            +1 = vorrei spostarmi a sinistra (sorpasso)
            -1 = vorrei spostarmi a destra (tieni destra)
             0 = resto nella corsia corrente
        """

    @abstractmethod
    def execute(
        self, vehicle: "Vehicle", direction: int, context: "SimContext"
    ) -> bool:
        """
        Tenta di cambiare corsia nella direzione indicata.
        Restituisce True se il cambio è stato eseguito.
        Aggiorna occ e vehicle.r/c/li come side effect.
        """

    @property
    def name(self) -> str:
        return self.__class__.__name__


class StopBehavior(ABC):
    """
    Gestisce fermate programmate (es. fermata bus).

    Responsabilità:
        - Verificare se il veicolo deve fermarsi
        - Gestire il countdown della sosta
        - Restituire True se il veicolo è in attesa
    """

    @abstractmethod
    def check_stop(self, vehicle: "Vehicle", context: "SimContext") -> bool:
        """
        Restituisce True se il veicolo deve rimanere fermo questo step.
        Può aggiornare il timer interno del veicolo.
        """

    @property
    def name(self) -> str:
        return self.__class__.__name__


class PullOverBehavior(ABC):
    """
    Risposta ai veicoli di emergenza.

    Responsabilità:
        - Rilevare se c'è un'emergenza nelle vicinanze
        - Segnalare al veicolo se deve spostarsi a destra
    """

    @abstractmethod
    def should_pull_over(self, vehicle: "Vehicle", context: "SimContext") -> bool:
        """
        Restituisce True se il veicolo deve cedere il passo
        spostandosi alla corsia destra.
        """

    @property
    def name(self) -> str:
        return self.__class__.__name__
