"""world — geometria della griglia e topologia degli incroci."""
from .geometry import GridGeometry, SlipEntry
from .topology import TopologyConfig, RoadSegment, TOPOLOGIES, list_topologies

__all__ = [
    "GridGeometry", "SlipEntry",
    "TopologyConfig", "RoadSegment", "TOPOLOGIES", "list_topologies",
]
