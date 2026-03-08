"""
Pacchetto traffic — simulatore di traffico urbano a automi cellulari.

Moduli:
    config      — SimConfig: dataclass con tutti i parametri
    geometry    — GridGeometry: coordinate e helper geometrici
    entities    — Personality, Car, Obstacle
    traffic_light — TrafficLight + politiche di ciclo
    simulation  — Sim: motore principale
    renderer    — Renderer: visualizzazione matplotlib
    scenarios   — configurazioni preset pronte all'uso
"""
from .config        import SimConfig, PersonalityProfile, LightPolicy, ManualObstacle
from .entities      import Personality, Car, Obstacle
from .geometry      import GridGeometry, SlipEntry
from .traffic_light import TrafficLight
from .right_of_way  import RightOfWayChecker
from .simulation    import Sim
from .renderer      import Renderer
from .scenarios     import SCENARIOS, list_scenarios
from .topology      import TopologyConfig, RoadSegment, TOPOLOGIES, list_topologies

__all__ = [
    # Config
    "SimConfig", "PersonalityProfile", "LightPolicy", "ManualObstacle",
    # Topology
    "TopologyConfig", "RoadSegment", "TOPOLOGIES", "list_topologies",
    # Entities
    "Personality", "Car", "Obstacle",
    # Geometry
    "GridGeometry", "SlipEntry",
    # Core
    "TrafficLight",
    "RightOfWayChecker",
    "Sim",
    "Renderer",
    # Scenarios
    "SCENARIOS", "list_scenarios",
]
