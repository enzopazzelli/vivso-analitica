"""Configuración del servicio: todo sale de variables de entorno ANALITICA_* (ver .env.example).

Cambiar de origen (simulado, base real, API o vacío) es cambiar variables, nunca código.
"""
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from urllib.parse import urlsplit, urlunsplit

ORIGENES = ("simulado", "mysql", "api", "vacio")

VARIABLES = (
    "ANALITICA_ORIGEN",
    "ANALITICA_MYSQL_URL",
    "ANALITICA_MYSQL_SSL_CA",
    "ANALITICA_VIVSO_API_URL",
    "ANALITICA_VIVSO_API_USUARIO",
    "ANALITICA_VIVSO_API_CLAVE",
    "ANALITICA_DB_URL",
    "ANALITICA_INTERVALO_MIN",
    "ANALITICA_CLAVE_LECTURA",
    "ANALITICA_CLAVE_ADMIN",
    "ANALITICA_CORS_ORIGENES",
    "ANALITICA_API_URL",
    "ANALITICA_FERIADOS_URL",
    "ANALITICA_FERIADOS_TIPOS",
)

DB_URL_POR_DEFECTO = "sqlite:///datos_locales/analitica.db"
FERIADOS_URL_POR_DEFECTO = "https://api.argentinadatos.com/v1/feriados/{año}"
FERIADOS_TIPOS_POR_DEFECTO = ("inamovible", "trasladable", "puente")


class ConfiguracionInvalida(ValueError):
    """Una variable ANALITICA_* tiene un valor que el servicio no puede usar."""


@dataclass(frozen=True)
class Configuracion:
    origen: str
    mysql_ssl_ca: str | None
    vivso_api_url: str | None
    vivso_api_usuario: str | None
    db_url: str
    intervalo_min: int
    cors_origenes: tuple[str, ...]
    api_url: str | None
    feriados_url: str
    feriados_tipos: tuple[str, ...]
    # Las que llevan contraseñas o claves no se muestran nunca (repr=False): ni en un print ni en un error.
    mysql_url: str | None = field(default=None, repr=False)
    vivso_api_clave: str | None = field(default=None, repr=False)
    clave_lectura: str | None = field(default=None, repr=False)
    clave_admin: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        """Sin las claves: las de repr=False no aparecen, y en las URLs la contraseña se cambia por ***."""
        partes = []
        for campo in fields(self):
            if not campo.repr:
                continue
            valor = getattr(self, campo.name)
            if campo.name.endswith("_url"):
                valor = _sin_clave(valor)
            partes.append(f"{campo.name}={valor!r}")
        return f"Configuracion({', '.join(partes)})"


def _sin_clave(url: str | None) -> str | None:
    if not url:
        return url
    partes = urlsplit(url)
    if partes.password is None:
        return url
    servidor = partes.netloc.rsplit("@", 1)[1]
    return urlunsplit(partes._replace(netloc=f"{partes.username or ''}:***@{servidor}"))


def _texto(entorno: Mapping[str, str], nombre: str) -> str | None:
    valor = entorno.get(nombre)
    if valor is None or not valor.strip():
        return None
    return valor.strip()


def _lista(entorno: Mapping[str, str], nombre: str, por_defecto: tuple[str, ...]) -> tuple[str, ...]:
    valor = _texto(entorno, nombre)
    if valor is None:
        return por_defecto
    return tuple(parte.strip() for parte in valor.split(",") if parte.strip())


def _origen(entorno: Mapping[str, str]) -> str:
    origen = (_texto(entorno, "ANALITICA_ORIGEN") or "simulado").lower()
    if origen not in ORIGENES:
        raise ConfiguracionInvalida(
            f"ANALITICA_ORIGEN={origen!r} no es válido; tiene que ser uno de: {', '.join(ORIGENES)}")
    return origen


def _intervalo(entorno: Mapping[str, str]) -> int:
    valor = _texto(entorno, "ANALITICA_INTERVALO_MIN")
    if valor is None:
        return 30
    try:
        minutos = int(valor)
    except ValueError:
        minutos = 0
    if minutos <= 0:
        raise ConfiguracionInvalida(f"ANALITICA_INTERVALO_MIN={valor!r} tiene que ser un número entero de minutos mayor que 0")
    return minutos


def cargar_configuracion(entorno: Mapping[str, str] | None = None) -> Configuracion:
    """Lee la configuración de `entorno` (por defecto, las variables de entorno del proceso)."""
    entorno = os.environ if entorno is None else entorno
    return Configuracion(
        origen=_origen(entorno),
        mysql_url=_texto(entorno, "ANALITICA_MYSQL_URL"),
        mysql_ssl_ca=_texto(entorno, "ANALITICA_MYSQL_SSL_CA"),
        vivso_api_url=_texto(entorno, "ANALITICA_VIVSO_API_URL"),
        vivso_api_usuario=_texto(entorno, "ANALITICA_VIVSO_API_USUARIO"),
        vivso_api_clave=_texto(entorno, "ANALITICA_VIVSO_API_CLAVE"),
        db_url=_texto(entorno, "ANALITICA_DB_URL") or DB_URL_POR_DEFECTO,
        intervalo_min=_intervalo(entorno),
        clave_lectura=_texto(entorno, "ANALITICA_CLAVE_LECTURA"),
        clave_admin=_texto(entorno, "ANALITICA_CLAVE_ADMIN"),
        cors_origenes=_lista(entorno, "ANALITICA_CORS_ORIGENES", ()),
        api_url=_texto(entorno, "ANALITICA_API_URL"),
        feriados_url=_texto(entorno, "ANALITICA_FERIADOS_URL") or FERIADOS_URL_POR_DEFECTO,
        feriados_tipos=_lista(entorno, "ANALITICA_FERIADOS_TIPOS", FERIADOS_TIPOS_POR_DEFECTO),
    )
