"""
traffic/__init__.py — Pacchetto principale.

Re-esporta tutto dalla nuova struttura a submoduli.
Garantisce backward-compatibility con il codice esistente.
"""
# Core
from .core.types     import VehicleType, LightPolicy, Personality
from .core.constants import VEHICLE_LENGTH, IDM_BASE
from .core.config    import (
    SimConfig, PersonalityProfile, DEFAULT_PROFILES,
    VehicleTypeWeights, BusStop, ManualObstacle,
)
# World
from .world.geometry import GridGeometry, SlipEntry
from .world.topology import TopologyConfig, RoadSegment, TOPOLOGIES, list_topologies
# Agents
from .agents.vehicle  import Vehicle, Car
from .agents.obstacle import Obstacle
from .agents.platoon  import Platoon
from .agents.factory  import VehicleFactory
# Infrastructure
from .infrastructure.gap_calculator import GapCalculator
from .infrastructure.ipr            import IntersectionPathReservation
from .infrastructure.traffic_light  import TrafficLight
from .infrastructure.right_of_way   import RightOfWayChecker
# Behaviors
from .behaviors import (
    MovementBehavior, LaneChangeBehavior, StopBehavior, PullOverBehavior,
    IDMBehavior, NaSchBehavior,
    MOBILBehavior, HeuristicLaneBehavior,
    BusStopBehavior, NullStopBehavior,
    EmergencyPullOverBehavior, NullPullOverBehavior,
)
# Simulation
from .simulation.engine  import SimEngine, Sim
from .simulation.context import SimContext
# Renderer
from .renderer import Renderer
# Scenarios
from .scenarios import SCENARIOS, list_scenarios

__all__ = [
    # Core
    "VehicleType", "LightPolicy", "Personality",
    "VEHICLE_LENGTH", "IDM_BASE",
    "SimConfig", "PersonalityProfile", "DEFAULT_PROFILES",
    "VehicleTypeWeights", "BusStop", "ManualObstacle",
    # World
    "GridGeometry", "SlipEntry",
    "TopologyConfig", "RoadSegment", "TOPOLOGIES", "list_topologies",
    # Agents
    "Vehicle", "Car", "Obstacle", "Platoon", "VehicleFactory",
    # Infrastructure
    "GapCalculator", "IntersectionPathReservation",
    "TrafficLight", "RightOfWayChecker",
    # Behaviors
    "MovementBehavior", "LaneChangeBehavior", "StopBehavior", "PullOverBehavior",
    "IDMBehavior", "NaSchBehavior",
    "MOBILBehavior", "HeuristicLaneBehavior",
    "BusStopBehavior", "NullStopBehavior",
    "EmergencyPullOverBehavior", "NullPullOverBehavior",
    # Simulation
    "SimEngine", "Sim", "SimContext",
    # Renderer
    "Renderer",
    # Scenarios
    "SCENARIOS", "list_scenarios",
]
