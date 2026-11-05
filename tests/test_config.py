import socket
from pathlib import Path

import pytest

from analitica.config import VARIABLES, ConfiguracionInvalida, cargar_configuracion

RAIZ = Path(__file__).resolve().parents[1]


def test_las_pruebas_no_usan_la_red():
    with pytest.raises(RuntimeError, match="no usan la red"):
        socket.create_connection(("example.com", 80), timeout=1)


def test_valores_por_defecto():
    cfg = cargar_configuracion({})
    assert cfg.origen == "simulado"
    assert cfg.db_url == "sqlite:///datos_locales/analitica.db"
    assert cfg.intervalo_min == 30
    assert cfg.feriados_url == "https://api.argentinadatos.com/v1/feriados/{año}"
    assert cfg.feriados_tipos == ("inamovible", "trasladable", "puente")
    assert cfg.cors_origenes == () and cfg.mysql_url is None and cfg.api_url is None


def test_el_origen_se_normaliza():
    assert cargar_configuracion({"ANALITICA_ORIGEN": " Vacio "}).origen == "vacio"


def test_un_origen_desconocido_da_un_error_claro():
    with pytest.raises(ConfiguracionInvalida, match="simulado, mysql, api, vacio"):
        cargar_configuracion({"ANALITICA_ORIGEN": "planilla"})


@pytest.mark.parametrize("valor", ["0", "-5", "media hora"])
def test_un_intervalo_invalido_da_un_error_claro(valor):
    with pytest.raises(ConfiguracionInvalida, match="ANALITICA_INTERVALO_MIN"):
        cargar_configuracion({"ANALITICA_INTERVALO_MIN": valor})


def test_listas_separadas_por_coma_y_vacios_como_none():
    cfg = cargar_configuracion({"ANALITICA_CORS_ORIGENES": "https://a.ar, https://b.ar,",
                                "ANALITICA_FERIADOS_TIPOS": "inamovible", "ANALITICA_API_URL": "  "})
    assert cfg.cors_origenes == ("https://a.ar", "https://b.ar")
    assert cfg.feriados_tipos == ("inamovible",)
    assert cfg.api_url is None


def test_las_claves_no_aparecen():
    cfg = cargar_configuracion({"ANALITICA_MYSQL_URL": "mysql+pymysql://lector:secreta1@h:1/vivso3",
                                "ANALITICA_VIVSO_API_CLAVE": "secreta2", "ANALITICA_CLAVE_LECTURA": "secreta3",
                                "ANALITICA_CLAVE_ADMIN": "secreta4"})
    assert "secreta" not in repr(cfg)


def test_las_claves_dentro_de_urls_no_aparecen():
    cfg = cargar_configuracion({"ANALITICA_DB_URL": "mysql+pymysql://analitica:clave-db-123@db:3306/analitica",
                                "ANALITICA_VIVSO_API_URL": "https://usuario:clave-api-456@vivso.example/api",
                                "ANALITICA_API_URL": "https://x:clave-789@tablero.example"})
    assert "clave-" not in repr(cfg) and "clave-" not in str(cfg)
    assert "analitica:***@db:3306" in repr(cfg)
    assert cfg.db_url == "mysql+pymysql://analitica:clave-db-123@db:3306/analitica"   # el valor real no cambia


def test_env_example_lista_todas_las_variables_sin_secretos():
    lineas = [l for l in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines()
              if "=" in l and not l.startswith("#")]
    valores = dict(l.split("=", 1) for l in lineas)
    assert set(valores) == set(VARIABLES)
    for secreta in ("ANALITICA_MYSQL_URL", "ANALITICA_VIVSO_API_CLAVE", "ANALITICA_CLAVE_LECTURA", "ANALITICA_CLAVE_ADMIN"):
        assert valores[secreta].strip() == ""
