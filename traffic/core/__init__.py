"""core — tipi primitivi, costanti fisiche, configurazione."""
from .types     import VehicleType, LightPolicy, Personality
from .constants import VEHICLE_LENGTH, IDM_BASE
from .config    import (
    SimConfig, PersonalityProfile, DEFAULT_PROFILES,
    VehicleTypeWeights, BusStop, ManualObstacle,
)

__all__ = [
    "VehicleType", "LightPolicy", "Personality",
    "VEHICLE_LENGTH", "IDM_BASE",
    "SimConfig", "PersonalityProfile", "DEFAULT_PROFILES",
    "VehicleTypeWeights", "BusStop", "ManualObstacle",
]
