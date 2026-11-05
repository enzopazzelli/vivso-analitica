"""Lo que comparten todos los orígenes: la `Lectura` con las 14 tablas y la verificación de su contrato."""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd

from analitica.calendario import ZONA
from analitica.config import ORIGENES
from analitica.esquema import COLUMNAS, TABLAS, TIPOS_PANDAS, columnas_prohibidas, es_vacio, nombres


class LecturaInvalida(ValueError):
    """La lectura de un origen no respeta el contrato: tablas, columnas, tipos o columnas prohibidas."""


@dataclass
class Lectura:
    origen: str
    leido_en: datetime                 # en hora de Buenos Aires, sin zona
    tablas: dict[str, pd.DataFrame]

    def tabla(self, nombre: str) -> pd.DataFrame:
        if nombre not in TABLAS or nombre not in self.tablas:
            raise KeyError(f"Tabla desconocida: {nombre}")
        return self.tablas[nombre]

    def filas(self) -> dict[str, int]:
        return {nombre: len(df) for nombre, df in self.tablas.items()}


class Origen(Protocol):
    codigo: str                         # "simulado" | "mysql" | "api" | "vacio"

    def leer(self) -> Lectura:
        """El estado completo actual, ya normalizado."""


class OrigenNoDisponible(NotImplementedError):
    """El origen configurado todavía no está implementado."""


def crear_origen(codigo: str | None = None) -> Origen:
    """El origen que dice ANALITICA_ORIGEN (o `codigo`). Con "vacio", el simulador queda apagado."""
    if codigo is None:
        from analitica.config import cargar_configuracion
        codigo = cargar_configuracion().origen
    codigo = codigo.strip().lower()
    if codigo == "vacio":
        from analitica.origenes.vacio import OrigenVacio
        return OrigenVacio()
    if codigo == "simulado":
        from analitica.origenes.simulado import OrigenSimulado
        return OrigenSimulado()
    if codigo in ("mysql", "api"):
        raise OrigenNoDisponible(f"El origen '{codigo}' todavía no está implementado")
    raise ValueError(f"Origen desconocido: {codigo!r}; tiene que ser uno de: {', '.join(ORIGENES)}")


def tabla_vacia(nombre: str) -> pd.DataFrame:
    return pd.DataFrame({columna: pd.Series(dtype=TIPOS_PANDAS[tipo]) for columna, tipo in COLUMNAS[nombre]})


def _a_hora_local(valor):
    if isinstance(valor, datetime) and valor.tzinfo is not None:
        return valor.astimezone(ZONA).replace(tzinfo=None)
    return valor


def _columna(valores: list, tipo: str) -> pd.Series:
    if tipo == "date":
        return pd.Series([None if es_vacio(v) else v for v in valores], dtype="object")
    if tipo == "datetime":
        return pd.Series([None if es_vacio(v) else _a_hora_local(v) for v in valores], dtype="datetime64[ns]")
    return pd.Series([None if es_vacio(v) else v for v in valores], dtype=TIPOS_PANDAS[tipo])


def armar_tabla(nombre: str, filas: Iterable[Mapping]) -> pd.DataFrame:
    """Una tabla con las columnas del esquema, en orden y con su tipo. Lo que traiga una fila de más se descarta y lo
    que le falte queda vacío."""
    filas = list(filas)
    if not filas:
        return tabla_vacia(nombre)
    datos = {}
    for columna, tipo in COLUMNAS[nombre]:
        try:
            datos[columna] = _columna([fila.get(columna) for fila in filas], tipo)
        except (TypeError, ValueError) as error:
            raise LecturaInvalida(f"{nombre}.{columna}: no se puede pasar a {tipo} ({error})") from error
    return pd.DataFrame(datos)


def verificar_lectura(lectura: Lectura) -> None:
    problemas = []
    if lectura.origen not in ORIGENES:
        problemas.append(f"origen desconocido: {lectura.origen!r}")
    if not isinstance(lectura.leido_en, datetime) or lectura.leido_en.tzinfo is not None:
        problemas.append("leido_en tiene que ser un datetime sin zona (hora de Buenos Aires)")
    faltan = [t for t in TABLAS if t not in lectura.tablas]
    sobran = [t for t in lectura.tablas if t not in TABLAS]
    if faltan:
        problemas.append(f"faltan las tablas {faltan}")
    if sobran:
        problemas.append(f"sobran las tablas {sobran}")
    for tabla in TABLAS:
        if tabla not in lectura.tablas:
            continue
        df = lectura.tablas[tabla]
        prohibidas = columnas_prohibidas(df.columns)
        if prohibidas:
            problemas.append(f"{tabla}: columnas prohibidas {prohibidas}")
        if list(df.columns) != nombres(tabla):
            problemas.append(f"{tabla}: columnas {list(df.columns)} en vez de {nombres(tabla)}")
            continue
        for columna, tipo in COLUMNAS[tabla]:
            if str(df[columna].dtype) != TIPOS_PANDAS[tipo]:
                problemas.append(f"{tabla}.{columna}: tipo {df[columna].dtype} en vez de {TIPOS_PANDAS[tipo]}")
            elif tipo == "date":
                malo = next((v for v in df[columna] if not es_vacio(v)
                             and (not isinstance(v, date) or isinstance(v, datetime))), None)
                if malo is not None:
                    problemas.append(f"{tabla}.{columna}: el valor {malo!r} no es una fecha sin hora")
    if problemas:
        raise LecturaInvalida("; ".join(problemas))


# (tabla, columna, tabla destino, columna destino): cada valor no vacío de la columna tiene que existir en el destino.
RELACIONES = (
    ("solicitudes", "id_familia", "familias", "id_familia"),
    ("solicitudes", "cuit_org", "organizaciones", "cuit"),
    ("solicitudes", "id_revisor", "usuarios", "id_usuario"),
    ("viviendas", "id_solicitud", "solicitudes", "id_solicitud"),
    ("etapas", "id_solicitud", "solicitudes", "id_solicitud"),
    ("etapas", "id_usuario_envio", "usuarios", "id_usuario"),
    ("etapas", "id_revisor", "usuarios", "id_usuario"),
    ("fotos_etapa", "id_etapa_obra", "etapas", "id_etapa_obra"),
    ("fotos_etapa", "id_usuario_subida", "usuarios", "id_usuario"),
    ("visitas_iniciales", "id_solicitud", "solicitudes", "id_solicitud"),
    ("visitas_iniciales", "id_tecnico", "usuarios", "id_usuario"),
    ("fotos_visita", "id_visita", "visitas_iniciales", "id_visita"),
    ("visitas_obra", "id_vivienda", "viviendas", "id_vivienda"),
    ("integrantes", "cuit_org", "organizaciones", "cuit"),
    ("integrantes", "id_usuario", "usuarios", "id_usuario"),
    ("documentos", "id_familia", "familias", "id_familia"),
    ("documentos", "id_solicitud_org", "solicitudes_organizacion", "id_solicitud_org"),
    ("solicitudes", "id_tecnico_asignado", "usuarios", "id_usuario"),
    ("viviendas", "id_familia", "familias", "id_familia"),
    ("visitas_obra", "id_tecnico", "usuarios", "id_usuario"),
    ("solicitudes_organizacion", "id_revisor", "usuarios", "id_usuario"),
    ("documentos", "cuit_org", "organizaciones", "cuit"),
    ("documentos", "id_revisor", "usuarios", "id_usuario"),
    ("notificaciones", "id_usuario", "usuarios", "id_usuario"),
    ("notificaciones", "id_referencia", "solicitudes", "id_solicitud"),
)


def verificar_relaciones(lectura: Lectura) -> list[str]:
    """Las filas huérfanas, como advertencias: no hacen fallar la lectura (la base real puede tenerlas)."""
    advertencias = []
    for tabla, columna, destino, columna_destino in RELACIONES:
        valores = lectura.tabla(tabla)[columna].dropna()
        existentes = set(lectura.tabla(destino)[columna_destino].dropna())
        huerfanas = int((~valores.isin(existentes)).sum())
        if huerfanas:
            advertencias.append(f"{tabla}.{columna}: {huerfanas} filas con un valor que no está en {destino}.{columna_destino}")
    documentos = lectura.tabla("documentos")
    sin_duenio = int((documentos["id_familia"].isna() & documentos["cuit_org"].isna()
                      & documentos["id_solicitud_org"].isna()).sum())
    if sin_duenio:
        advertencias.append(f"documentos sin dueño: {sin_duenio} filas sin id_familia, cuit_org ni id_solicitud_org")
    return advertencias
