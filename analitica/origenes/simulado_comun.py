"""Ayudas que comparten las partes del simulador: momentos, días, personas inventadas y el username de Java."""
import re
import unicodedata
from datetime import date, datetime, time, timedelta

import numpy as np
from faker import Faker

from analitica.calendario import CALENDARIO_JAVA


def mes(n: int) -> timedelta:
    """Un mes del simulador son 30 días."""
    return timedelta(days=30 * n)


def entero(rng: np.random.Generator, rango: tuple[int, int]) -> int:
    """Un entero al azar del rango, con los dos extremos incluidos."""
    return int(rng.integers(rango[0], rango[1] + 1))


def momento_habil(dia: date, rng: np.random.Generator, desde_hora: int = 8, hasta_hora: int = 18) -> datetime:
    """Un momento al azar de ese día entre las dos horas, con segundos y sin microsegundos."""
    segundos = int(rng.integers(desde_hora * 3600, hasta_hora * 3600))
    return datetime.combine(dia, time()) + timedelta(seconds=segundos)


def dia_habil(dia: date) -> date:
    """El mismo día si es hábil para Java; si no, el siguiente hábil."""
    while not CALENDARIO_JAVA.es_habil(dia):
        dia += timedelta(days=1)
    return dia


def _sin_tildes(texto: str) -> str:
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode("ascii"))


def persona(fake: Faker, rng: np.random.Generator) -> dict:
    """Una persona inventada. El DNI es único dentro de cada Faker, y el correo lo lleva para ser único también."""
    nombre, apellido = fake.first_name(), fake.last_name()
    dni = str(fake.unique.random_int(min=10_000_000, max=49_999_999))
    return {
        "dni": dni,
        "nombre": nombre,
        "apellido": apellido,
        "correo": f"{_sin_tildes(nombre)}.{_sin_tildes(apellido)}.{dni}@example.com",
        "telefono": f"385{int(rng.integers(4_000_000, 6_000_000))}",
        "domicilio": fake.street_address(),
    }


def username_java(nombre: str, apellido: str, existentes: set[str]) -> str:
    """Como SolicitudOrganizacionService: nombre.apellido en minúsculas sin lo que no sea [a-z0-9.]; si ya existe,
    Java le agrega un contador a la base SIN limpiar («josé luis.pérez1»)."""
    base = nombre.lower() + "." + apellido.lower()
    username = re.sub(r"[^a-z0-9.]", "", base)
    contador = 1
    while username in existentes:
        username = base + str(contador)
        contador += 1
    return username
