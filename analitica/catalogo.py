"""El dominio del sistema de Desarrollo, copiado de sus enums.

Fuente: `Model/*.java` del repositorio PaganiB/vivso (revisado el 21/10/2026). La base guarda el nombre del enum
(`TIPO_1A`) y la API de Java devuelve su valor (`"1a"`); todo el servicio guarda el nombre, como la base.
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import NamedTuple


@dataclass(frozen=True)
class Etapa:
    codigo: str            # como lo guarda la base: "ETAPA_1" … "ETAPA_6"
    numero: int
    nombre: str
    descripcion: str
    dias_estimados: int    # días hábiles


# EtapaConstruccion.java (commit «Feature-18 | AFO -> EtapaObra»): el AFO son estas 6 etapas.
ETAPAS = (
    Etapa("ETAPA_1", 1, "Replanteo y cimientos",
          "Replanteo, excavación y llenado de cimientos", 2),
    Etapa("ETAPA_2", 2, "Mampostería de cimientos",
          "Mampostería de cimientos, encadenado inferior c/tronco de columna y capa aisladora", 2),
    Etapa("ETAPA_3", 3, "Elevación y techo",
          "Mampostería de elevación, columnas de encadenado, encadenado superior, techo completo c/aislante, apretada "
          "y colocación de aberturas", 10),
    Etapa("ETAPA_4", 4, "Revoques y contrapiso",
          "Revoque grueso y fino interior y exterior, contrapiso y carpeta de nivelación", 8),
    Etapa("ETAPA_5", 5, "Instalaciones",
          "Instalación eléctrica, instalación sanitaria, colocación de mesada, cámaras y pozo", 5),
    Etapa("ETAPA_6", 6, "Pintura y artefactos",
          "Pintura interior y exterior, colocación de artefactos eléctricos, colocación de artefactos sanitarios", 2),
)
TOTAL_DIAS_ESTIMADOS = sum(e.dias_estimados for e in ETAPAS)

_ETAPA_POR_CODIGO = {e.codigo: e for e in ETAPAS}


def etapa(codigo: str) -> Etapa:
    try:
        return _ETAPA_POR_CODIGO[codigo]
    except KeyError:
        raise KeyError(f"Etapa desconocida: {codigo}") from None


def siguiente(codigo: str) -> Etapa | None:
    """La etapa que se activa cuando se aprueba esta, o None si es la última (obra finalizada)."""
    numero = etapa(codigo).numero
    return ETAPAS[numero] if numero < len(ETAPAS) else None


# EstadoEtapa.java. La etapa «activa» es la que le toca a la obra ahora: ya empezó y todavía no está aprobada.
ESTADOS_ETAPA = ("PENDIENTE", "EN_CURSO", "EN_REVISION", "PRORROGADA", "OBSERVADA", "APROBADA")
ESTADOS_ACTIVOS = ("EN_CURSO", "EN_REVISION", "PRORROGADA", "OBSERVADA")

# EstadoSolicitud.java: lo usan la solicitud de vivienda y el alta de organizaciones.
ESTADOS_SOLICITUD = ("Pendiente", "SemiAprobada", "Aprobada", "Rechazada")

# Roles de Security/SecurityConfig.java.
ROLES = ("ADMIN", "OPERADOR", "ARQUITECTO", "TECNICO", "INTEGRANTE")

# ClasificacionPreeliminar.java (así, con «ee»): nombre del enum → valor.
CLASIFICACIONES = {
    "TIPO_1A": "1a", "TIPO_2A": "2a", "TIPO_2B": "2b", "TIPO_3A": "3a", "TIPO_4A": "4a", "TIPO_4B": "4b",
    "TIPO_4C": "4c", "TIPO_5A": "5a", "TIPO_5B": "5b", "TIPO_5C": "5c", "TIPO_5D": "5d",
    "DERRUMBE": "DERRUMBE", "OTRA": "OTRA",
}

# TipoVivienda.java: es el prototipo (presupuesto y planos), no la ubicación.
TIPOS_VIVIENDA = {"URBANA": "Urbana", "RURAL": "Rural", "ECONOMICA": "Económica"}

# EstadoDocumento.java. APROBADO y RECHAZADO solo existen en el alta de organizaciones.
ESTADOS_DOCUMENTO = {"PENDIENTE": "Pendiente", "A_CORREGIR": "A corregir", "APROBADO": "Aprobado",
                     "RECHAZADO": "Rechazado"}

# TipoCargo.java.
TIPOS_CARGO = {"PRESIDENTE": "Presidente", "VICEPRESIDENTE": "Vicepresidente", "TESORERO": "Tesorero",
               "SECRETARIO": "Secretario", "VOCAL": "Vocal", "INTEGRANTE": "Integrante"}


@dataclass(frozen=True)
class TipoDocumento:
    codigo: str
    valor: str
    ambito: str    # "organizacion", "familia", "obra" u "otro", según los comentarios de TipoDocumento.java


# TipoDocumento.java, con sus valores tal cual (los dos espacios de «Residencia  de familia» son de Java).
TIPOS_DOCUMENTO = {t.codigo: t for t in (
    TipoDocumento("ACTA_COMPROMISO_ONG", "Acta Compromiso de la organizacion", "organizacion"),
    TipoDocumento("NOTA_SOLICITUD", "Nota de solicitud", "organizacion"),
    TipoDocumento("ALTA_AFIP", "Alta de AFIP", "organizacion"),
    TipoDocumento("ACTA_ASAMBLEA", "Acta de Asamblea Actual", "organizacion"),
    TipoDocumento("CONSTANCIA_VIGENCIA", "Constancia de vigencia", "organizacion"),
    TipoDocumento("CONSTANCIA_CUENTA_BANCARIA", "Constancia de cuenta bancaria (BSE)", "organizacion"),
    TipoDocumento("DNI_PRESIDENTE", "DNI PRESIDENTE", "organizacion"),
    TipoDocumento("DNI_TESORERO", "DNI TESORERO", "organizacion"),
    TipoDocumento("CERTIFICADO_RESIDENCIA_PRESIDENTE", "Certificado de Residencia del Presidente", "organizacion"),
    TipoDocumento("CERTIFICADO_RESIDENCIA_TESORERO", "Certificado de Residencia de tesorero", "organizacion"),
    TipoDocumento("DNI_FAMILIARES", "DNI FAMILIAR", "familia"),
    TipoDocumento("CERTIFICADO_DISCAPACIDAD", "Certificado de Discapacidad", "familia"),
    TipoDocumento("ESCRITURA_PROPIEDAD", "Escritura de la propiedad", "familia"),
    TipoDocumento("ACTA_COMPROMISO_FAMILIA", "Acta Compromiso", "familia"),
    TipoDocumento("FOTOS_TERRENO", "Foto del Terreno", "familia"),
    TipoDocumento("CERTIFICADO_RESIDENCIA_FAMILIA", "Certificado de Residencia  de familia", "familia"),
    TipoDocumento("DECLARACION_JURADA", "Declaración Jurada", "familia"),
    TipoDocumento("FOTO_OBRA", "Foto de avance de obra", "obra"),
    TipoDocumento("OTRO", "Otro", "otro"),
)}


# Organizaciones en dos grupos, con la regla del informe OG/ONG: en Java el tipo es texto libre.
GRUPOS_ORGANIZACION = ("OG", "ONG")


class GrupoOrganizacion(NamedTuple):
    grupo: str        # "OG" u "ONG"
    categoria: str    # "Comisión Municipal", "Municipio" u "ONG"


_COMISION_MUNICIPAL = re.compile(r"\bCOM\.?\s*MUN\b|\bCOMISION\s+MUNICIPAL\b|\bCOMISIONADO\s+MUNICIPAL\b")
# \b antes de MUN es obligatorio: sin eso, «ASOC.CIV.SOC.COMUN.DE ACCION» se colaba como Municipio.
_MUNICIPIO = re.compile(r"\bMUNICIPALID|\bMUN\.\s*DE\b|\bMUNICIPIO\b|\bINTENDENCIA\b")
_TIPOS_GENERICOS = {"OTRO", "OTRA", "OTROS"}
_ONG = GrupoOrganizacion("ONG", "ONG")


def _normalizar(texto: str | None) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return sin_tildes.upper().strip()


def _grupo_del_texto(texto: str) -> GrupoOrganizacion | None:
    if _COMISION_MUNICIPAL.search(texto):
        return GrupoOrganizacion("OG", "Comisión Municipal")
    if _MUNICIPIO.search(texto):
        return GrupoOrganizacion("OG", "Municipio")
    return None


def grupo_organizacion(tipo: str | None, nombre: str | None) -> GrupoOrganizacion:
    """OG (Municipio y Comisión Municipal) u ONG (el resto, incluidas las Comisiones de Fomento, que en Santiago del
    Estero son organizaciones civiles). Decide el tipo; el nombre solo se mira si el tipo está vacío o es genérico."""
    tipo_normalizado = _normalizar(tipo)
    por_tipo = _grupo_del_texto(tipo_normalizado)
    if por_tipo:
        return por_tipo
    if not tipo_normalizado or tipo_normalizado in _TIPOS_GENERICOS:
        return _grupo_del_texto(_normalizar(nombre)) or _ONG
    return _ONG
