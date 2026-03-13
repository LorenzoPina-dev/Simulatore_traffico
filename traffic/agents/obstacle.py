"""agents/obstacle.py — Ostacolo fisso sulla griglia."""


class Obstacle:
    """
    Blocco fisso su una cella (incidente, cantiere, panne).

    Attributi:
        r, c   : cella
        dur    : step rimanenti (-1 = permanente)
        label  : descrizione
    """

    def __init__(self, r: int, c: int, dur: int, label: str = "incidente"):
        self.r     = r
        self.c     = c
        self.dur   = dur
        self.label = label

    def tick(self) -> bool:
        """Avanza il timer. Restituisce True se l'ostacolo è ancora attivo."""
        if self.dur == -1:
            return True
        self.dur -= 1
        return self.dur > 0

    def is_permanent(self) -> bool:
        return self.dur == -1

    def __repr__(self) -> str:
        dur_str = "permanente" if self.dur == -1 else f"dur={self.dur}"
        return f"Obstacle({self.label!r}, pos=({self.r},{self.c}), {dur_str})"
