"""
core/types.py — Enumerazioni fondamentali del dominio.

Unica sorgente di verità per VehicleType, LightPolicy, Personality.
Nessuna dipendenza da altri moduli del pacchetto.
"""
from enum import Enum, IntEnum


class VehicleType(IntEnum):
    """Tipo fisico del veicolo. Determina lunghezza e parametri IDM."""
    MOTORCYCLE = 0   # moto  : lunghezza 1, veloce, gap minimo ridotto
    CAR        = 1   # auto  : lunghezza 1, parametri standard
    VAN        = 2   # furgone: lunghezza 2, più lento
    BUS        = 3   # bus   : lunghezza 3, si ferma alle fermate
    EMERGENCY  = 4   # sirena: lunghezza 2, precedenza assoluta


class LightPolicy(Enum):
    """Politica di ciclo del semaforo."""
    FIXED          = "fixed"
    ADAPTIVE       = "adaptive"
    ALWAYS_GREEN_H = "always_green_h"
    ALWAYS_GREEN_V = "always_green_v"
    NO_LIGHT       = "no_light"


class Personality(IntEnum):
    """Indice del profilo personalità nel lista cfg.personalities."""
    CAUTIOUS   = 0
    NORMAL     = 1
    AGGRESSIVE = 2
    RUSHER     = 3
