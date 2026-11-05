"""Feriados de ArgentinaDatos, la misma fuente que va a usar Desarrollo, guardados en un archivo por año para trabajar
sin conexión.

Por cada año: si está el archivo local y es válido, se usa; si no, se baja y se guarda; si no hay conexión ni archivo, se
usan los feriados nacionales del paquete `holidays` y se avisa.
"""
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import holidays
import httpx

from analitica.calendario import Calendario
from analitica.config import FERIADOS_TIPOS_POR_DEFECTO, FERIADOS_URL_POR_DEFECTO

CARPETA_POR_DEFECTO = Path("datos_locales/feriados")


@dataclass
class ResultadoFeriados:
    fechas: frozenset[date]
    fuentes: dict[int, str] = field(default_factory=dict)       # año → "archivo", "descarga" o "respaldo"
    advertencias: list[str] = field(default_factory=list)

    def calendario(self) -> Calendario:
        return Calendario(self.fechas)


def descargar_json(url: str) -> list[dict]:
    respuesta = httpx.get(url, timeout=10)
    respuesta.raise_for_status()
    return respuesta.json()


def _validar(datos) -> list[dict]:
    """El formato de ArgentinaDatos: una lista de {"fecha": "AAAA-MM-DD", "tipo": …, "nombre": …}."""
    if not isinstance(datos, list) or not datos:
        raise ValueError("la respuesta no es una lista de feriados")
    for item in datos:
        if not isinstance(item, dict) or not isinstance(item.get("tipo"), str) or not isinstance(item.get("fecha"), str):
            raise ValueError(f"un feriado sin fecha o sin tipo: {item!r}")
        date.fromisoformat(item["fecha"])
    return datos


def _fechas(datos: list[dict], tipos: tuple[str, ...]) -> set[date]:
    return {date.fromisoformat(item["fecha"]) for item in datos if item["tipo"] in tipos}


def cargar(anios: Iterable[int], *, carpeta: Path = CARPETA_POR_DEFECTO, url: str = FERIADOS_URL_POR_DEFECTO,
           tipos: tuple[str, ...] = FERIADOS_TIPOS_POR_DEFECTO,
           descargar: Callable[[str], list[dict]] | None = None) -> ResultadoFeriados:
    descargar = descargar or descargar_json      # se busca al llamar, para que las pruebas puedan reemplazarlo
    carpeta = Path(carpeta)
    resultado = ResultadoFeriados(fechas=frozenset())
    fechas: set[date] = set()
    for anio in anios:
        archivo = carpeta / f"{anio}.json"
        if archivo.exists():
            try:
                fechas |= _fechas(_validar(json.loads(archivo.read_text(encoding="utf-8"))), tipos)
                resultado.fuentes[anio] = "archivo"
                continue
            except (ValueError, KeyError, TypeError):
                resultado.advertencias.append(f"El archivo {archivo} está dañado; se vuelve a bajar")
        try:
            datos = _validar(descargar(url.format(**{"año": anio})))
        except Exception as error:   # sin conexión, error HTTP o formato inesperado: se usa el respaldo
            fechas |= set(holidays.country_holidays("AR", years=anio))
            resultado.fuentes[anio] = "respaldo"
            resultado.advertencias.append(
                f"Feriados de {anio}: no se pudieron leer ni bajar de ArgentinaDatos; se usan los nacionales del "
                f"paquete holidays ({error})")
            continue
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        fechas |= _fechas(datos, tipos)
        resultado.fuentes[anio] = "descarga"
    resultado.fechas = frozenset(fechas)
    return resultado
