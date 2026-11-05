"""Las 14 tablas que entrega todo origen: mismas columnas, mismo orden y mismos tipos.

Las columnas salen de las tablas de Java (sección 5 de docs/sistema-de-desarrollo.md), pasadas a minúsculas con guion
bajo. Tipos: int, float, str, bool, date (fecha sin hora) y datetime (fecha y hora de Buenos Aires, sin zona). Los
vacíos se aceptan en cualquier columna. Nunca hay columnas de tokens ni contraseñas, y de las familias solo hay conteos.
"""
import math
import unicodedata
from collections.abc import Mapping
from datetime import date, datetime

import numpy as np
import pandas as pd

_PERSONA = ("dni", "nombre", "apellido", "correo", "telefono", "fecha_alta_cargo", "domicilio")
_TIPOS_PERSONA = ("str", "str", "str", "str", "str", "date", "str")


def _persona(cargo: str) -> tuple[tuple[str, str], ...]:
    return tuple((f"{campo}_{cargo}", tipo) for campo, tipo in zip(_PERSONA, _TIPOS_PERSONA))


COLUMNAS: dict[str, tuple[tuple[str, str], ...]] = {
    "solicitudes": (
        ("id_solicitud", "int"), ("num_exp", "str"), ("estado", "str"), ("fecha_solicitud", "date"),
        ("fecha_activacion", "date"), ("cuit_org", "str"), ("id_familia", "int"), ("observacion", "str"),
        ("campos_observados", "str"), ("id_revisor", "int"), ("id_tecnico_asignado", "int"),
    ),
    "familias": (
        ("id_familia", "int"), ("cantidad_familiares", "int"), ("antiguedad_rancho", "int"),
    ),
    "viviendas": (
        ("id_vivienda", "int"), ("id_solicitud", "int"), ("id_familia", "int"), ("departamento", "str"),
        ("localidad", "str"), ("direccion", "str"), ("barrio", "str"), ("superficie", "float"),
        ("fecha_inicio", "date"), ("fecha_fin", "date"), ("latitud", "float"), ("longitud", "float"),
        ("tipo_vivienda", "str"), ("cant_dormitorios", "int"), ("avance_obra", "int"),
    ),
    "etapas": (
        ("id_etapa_obra", "int"), ("id_solicitud", "int"), ("etapa", "str"), ("numero", "int"), ("estado", "str"),
        ("fecha_inicio", "date"), ("fecha_limite", "date"), ("fecha_limite_original", "date"),
        ("motivo_prorroga", "str"), ("fecha_envio", "datetime"), ("observacion_organizacion", "str"),
        ("id_usuario_envio", "int"), ("id_revisor", "int"), ("fecha_revision", "datetime"),
        ("observacion_tecnico", "str"),
    ),
    "fotos_etapa": (
        ("id_foto", "int"), ("id_etapa_obra", "int"), ("nombre_archivo", "str"), ("ruta_archivo", "str"),
        ("fecha_subida", "datetime"), ("id_usuario_subida", "int"),
    ),
    "visitas_iniciales": (
        ("id_visita", "int"), ("id_solicitud", "int"), ("fecha_visita", "datetime"), ("id_tecnico", "int"),
        ("clasificacion", "str"), ("latitud", "float"), ("longitud", "float"), ("localidad", "str"),
        ("departamento", "str"), ("observaciones", "str"), ("habitantes", "int"), ("prioridad_social", "bool"),
    ),
    "fotos_visita": (
        ("id_visita", "int"), ("url_foto", "str"),
    ),
    "visitas_obra": (
        ("id_visita_obra", "int"), ("id_vivienda", "int"), ("fecha", "date"), ("afo", "int"),
        ("observaciones", "str"), ("id_tecnico", "int"),
    ),
    "organizaciones": (
        ("cuit", "str"), ("nombre", "str"), ("tipo", "str"), ("dom_legal", "str"), ("cpe", "str"),
        ("fecha_vencimiento_vigencia", "date"), ("fecha_ultima_asamblea", "date"),
    ),
    "solicitudes_organizacion": (
        ("id_solicitud_org", "int"), ("cuit", "str"), ("nombre", "str"), ("tipo", "str"), ("dom_legal", "str"),
        ("cpe", "str"), ("fecha_vencimiento_vigencia", "date"), ("fecha_ultima_asamblea", "date"),
        *_persona("presidente"), *_persona("tesorero"),
        ("estado", "str"), ("motivo", "str"), ("fecha_rechazo", "date"), ("fecha_aprobacion", "date"),
        ("fecha_solicitud", "date"), ("campos_observados", "str"), ("id_revisor", "int"),
    ),
    "integrantes": (
        ("id_integrante", "int"), ("cuit_org", "str"), ("dni", "str"), ("nombre", "str"), ("apellido", "str"),
        ("correo", "str"), ("telefono", "str"), ("cargo", "str"), ("domicilio", "str"), ("activo", "bool"),
        ("fecha_alta_cargo", "date"), ("id_usuario", "int"),
    ),
    "usuarios": (
        ("id_usuario", "int"), ("username", "str"), ("rol", "str"), ("email", "str"), ("activo", "bool"),
        ("nombre", "str"), ("apellido", "str"),
    ),
    "documentos": (
        ("id_documento", "int"), ("nombre_original", "str"), ("url", "str"), ("tipo", "str"), ("estado", "str"),
        ("motivo_observacion", "str"), ("fecha_subida", "datetime"), ("fecha_revision", "datetime"),
        ("id_familia", "int"), ("cuit_org", "str"), ("id_solicitud_org", "int"), ("id_revisor", "int"),
    ),
    # Una fila por destinatario; id_referencia es la solicitud. Título y mensaje no se leen (son el tipo y el expediente).
    "notificaciones": (
        ("id_notificacion", "int"), ("id_usuario", "int"), ("tipo", "str"), ("id_referencia", "int"),
        ("fecha", "datetime"), ("leida", "bool"),
    ),
}
TABLAS = tuple(COLUMNAS)

# La clave de cada tabla: identifica una fila entre dos lecturas (la usan las versiones del sincronizador).
CLAVES: dict[str, tuple[str, ...]] = {
    "solicitudes": ("id_solicitud",), "familias": ("id_familia",), "viviendas": ("id_vivienda",),
    "etapas": ("id_etapa_obra",), "fotos_etapa": ("id_foto",), "visitas_iniciales": ("id_visita",),
    "fotos_visita": ("id_visita", "url_foto"), "visitas_obra": ("id_visita_obra",), "organizaciones": ("cuit",),
    "solicitudes_organizacion": ("id_solicitud_org",), "integrantes": ("id_integrante",),
    "usuarios": ("id_usuario",), "documentos": ("id_documento",), "notificaciones": ("id_notificacion",),
}


def clave_de(tabla: str, fila: Mapping) -> str:
    """Los valores de la clave de la fila unidos con «|» (un entero de numpy se escribe sin decimales)."""
    return "|".join(str(fila[columna].item() if isinstance(fila[columna], np.generic) else fila[columna])
                    for columna in CLAVES[tabla])

# El tipo de pandas de cada tipo del esquema. Los nulables (Int64, Float64, string, boolean) mantienen el tipo aunque
# haya vacíos; las fechas sin hora quedan como objetos `date`.
TIPOS_PANDAS = {"int": "Int64", "float": "Float64", "str": "string", "bool": "boolean", "date": "object",
                "datetime": "datetime64[ns]"}

PALABRAS_PROHIBIDAS = ("token", "password", "contrasena", "clave", "secret", "hash")


def nombres(tabla: str) -> list[str]:
    return [columna for columna, _ in COLUMNAS[tabla]]


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


def columnas_prohibidas(columnas) -> list[str]:
    """Las columnas que nunca pueden salir de un origen: tokens, contraseñas, claves, secretos y hashes."""
    return [c for c in columnas if any(palabra in _sin_tildes(str(c)) for palabra in PALABRAS_PROHIBIDAS)]


def es_vacio(valor) -> bool:
    if valor is None or valor is pd.NaT or valor is pd.NA:
        return True
    return isinstance(valor, (float, np.floating)) and math.isnan(valor)


def valor_valido(valor, tipo: str) -> bool:
    if es_vacio(valor):
        return True
    if tipo == "int":
        return isinstance(valor, (int, np.integer)) and not isinstance(valor, (bool, np.bool_))
    if tipo == "float":
        return isinstance(valor, (int, float, np.integer, np.floating)) and not isinstance(valor, (bool, np.bool_))
    if tipo == "str":
        return isinstance(valor, str)
    if tipo == "bool":
        return isinstance(valor, (bool, np.bool_))
    if tipo == "date":
        return isinstance(valor, date) and not isinstance(valor, datetime)
    if tipo == "datetime":
        return isinstance(valor, datetime)
    raise ValueError(f"Tipo desconocido en el esquema: {tipo}")
