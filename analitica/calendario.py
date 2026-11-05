"""Días hábiles con la regla de `CalendarioService.java` del sistema de Desarrollo, más un conjunto de feriados.

`CALENDARIO_JAVA` no tiene feriados: es lo que hace Java hoy, y con él se calculan y se verifican los límites que guarda
Java. Los indicadores usan un `Calendario` con los feriados de ArgentinaDatos (ver `analitica/feriados.py`).
"""
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

# Todas las fechas del sistema de Desarrollo están en esta zona (EtapaObraService usa `LocalDateTime.now(ZONA)`).
# En Windows, zoneinfo necesita el paquete tzdata.
ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
_UN_DIA = timedelta(days=1)


def ahora_local() -> datetime:
    """La hora de Buenos Aires, sin zona y sin microsegundos (como la guarda el servicio)."""
    return datetime.now(ZONA).replace(tzinfo=None, microsecond=0)


def fecha_local(momento: datetime) -> date:
    """La fecha en Buenos Aires de un momento. Sin zona, se asume que ya está en hora de Buenos Aires (así lo guarda Java)."""
    if momento.tzinfo is None:
        return momento.date()
    return momento.astimezone(ZONA).date()


def _dia(valor: date) -> date:
    return fecha_local(valor) if isinstance(valor, datetime) else valor


class Calendario:
    def __init__(self, feriados: Iterable[date] = ()):
        self.feriados = frozenset(feriados)
        self._feriados_numpy = np.array(sorted(self.feriados), dtype="datetime64[D]")

    def es_habil(self, fecha: date) -> bool:
        fecha = _dia(fecha)
        return fecha.weekday() < 5 and fecha not in self.feriados

    def sumar_habiles(self, desde: date, n: int) -> date:
        """El día `desde` no cuenta: el día 1 es el siguiente día hábil. Como Java: habilitada un viernes con 2 días,
        vence el martes. Un datetime se pasa antes a su fecha en Buenos Aires."""
        if n < 0:
            raise ValueError("Los días no pueden ser negativos")
        fecha, restantes = _dia(desde), n
        while restantes > 0:
            fecha += _UN_DIA
            if self.es_habil(fecha):
                restantes -= 1
        return fecha

    def habiles_entre(self, a: date, b: date) -> int:
        """Días hábiles d con a < d <= b (H en la especificación): 0 si a == b, y negativo si b es anterior a a.
        Un datetime se pasa antes a su fecha en Buenos Aires."""
        a, b = _dia(a), _dia(b)
        if b < a:
            return -self.habiles_entre(b, a)
        # busday_count cuenta [inicio, fin): corriendo un día los dos extremos queda (a, b].
        return int(np.busday_count(a + _UN_DIA, b + _UN_DIA, holidays=self._feriados_numpy))

    def habiles_restantes(self, hoy: date, limite: date) -> int:
        """Como `diasHabilesRestantes` de Java: no cuenta hoy, cuenta el día del límite; 0 si el límite es hoy o ya pasó."""
        return max(0, self.habiles_entre(hoy, limite))


CALENDARIO_JAVA = Calendario()
