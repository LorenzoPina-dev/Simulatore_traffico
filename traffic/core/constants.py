"""
core/constants.py — Costanti fisiche dei veicoli.

Scala di riferimento:
    1 cella  ≈ 7 m       (larghezza corsia + veicolo)
    1 step   ≈ 1 s       (timestep di simulazione)
    max_speed=4 ≈ 28 m/s ≈ 100 km/h

IDM_BASE: parametri del Intelligent Driver Model per tipo veicolo.
    a  = accelerazione massima   [celle/step²]
    b  = decelerazione comfort   [celle/step²]
    T  = time headway desiderato [step]
    s0 = gap minimo stazionario  [celle]
    v_factor = moltiplicatore su max_speed della personalità

Valori realistici (strada urbana, T calibrato per 1 step = 1 s):
    auto:  a≈1.5, b≈2.0, T≈1.5 s, s0≈7 m (1 cella)
    moto:  a≈2.5, b≈2.5, T≈1.0 s, s0≈7 m
    bus:   a≈0.8, b≈1.5, T≈2.0 s, s0≈14 m (2 celle)
"""
from .types import VehicleType

VEHICLE_LENGTH: dict[VehicleType, int] = {
    VehicleType.MOTORCYCLE: 1,
    VehicleType.CAR:        1,
    VehicleType.VAN:        2,
    VehicleType.BUS:        3,
    VehicleType.EMERGENCY:  2,
}

IDM_BASE: dict[VehicleType, dict] = {
    VehicleType.MOTORCYCLE: dict(a=2.5, b=2.5, T=1.0, s0=1, v_factor=1.25),
    VehicleType.CAR:        dict(a=1.5, b=2.0, T=1.5, s0=1, v_factor=1.00),
    VehicleType.VAN:        dict(a=1.0, b=1.8, T=1.8, s0=2, v_factor=0.85),
    VehicleType.BUS:        dict(a=0.8, b=1.5, T=2.0, s0=2, v_factor=0.70),
    VehicleType.EMERGENCY:  dict(a=3.0, b=2.8, T=0.6, s0=1, v_factor=1.60),
}
