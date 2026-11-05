from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from analitica.esquema import TABLAS, columnas_prohibidas, nombres, valor_valido
from analitica.origenes.base import Lectura, LecturaInvalida, armar_tabla, tabla_vacia, verificar_lectura, verificar_relaciones
from analitica.origenes.vacio import OrigenVacio


def _lectura(origen="simulado", **reemplazos):
    tablas = {t: tabla_vacia(t) for t in TABLAS} | reemplazos
    return Lectura(origen=origen, leido_en=datetime(2026, 10, 19, 12, 0), tablas=tablas)


def test_las_13_tablas_en_orden():
    assert TABLAS == ("solicitudes", "familias", "viviendas", "etapas", "fotos_etapa", "visitas_iniciales",
                      "fotos_visita", "visitas_obra", "organizaciones", "solicitudes_organizacion", "integrantes",
                      "usuarios", "documentos")
    assert nombres("familias") == ["id_familia", "cantidad_familiares", "antiguedad_rancho"]
    assert nombres("usuarios") == ["id_usuario", "username", "rol", "email", "activo"]
    assert len(nombres("etapas")) == 15 and len(nombres("solicitudes_organizacion")) == 29
    assert all(columnas_prohibidas(nombres(t)) == [] for t in TABLAS)


def test_columnas_prohibidas():
    assert columnas_prohibidas(["token_edicion", "password_hash", "Contraseña", "clave_api", "client_secret", "nombre"]) == [
        "token_edicion", "password_hash", "Contraseña", "clave_api", "client_secret"]


@pytest.mark.parametrize("valor, tipo, esperado", [
    (3, "int", True), (np.int64(3), "int", True), (True, "int", False), (3.5, "int", False),
    (2.5, "float", True), ("x", "str", True), (3, "str", False), (True, "bool", True),
    (date(2026, 10, 19), "date", True), (datetime(2026, 10, 19, 9), "date", False),
    (pd.Timestamp("2026-10-19"), "date", False),
    (datetime(2026, 10, 19, 9), "datetime", True), (pd.Timestamp("2026-10-19 09:00"), "datetime", True),
    (date(2026, 10, 19), "datetime", False),
    (None, "date", True), (float("nan"), "int", True), (pd.NaT, "datetime", True), (pd.NA, "str", True),
])
def test_valor_valido(valor, tipo, esperado):
    assert valor_valido(valor, tipo) is esperado


def test_armar_tabla_conserva_tipos_ordena_y_descarta_lo_que_sobra():
    usuarios = armar_tabla("usuarios", [{"id_usuario": 1, "username": "a", "rol": "TECNICO", "activo": True},
                                        {"activo": None, "id_usuario": 2, "password_hash": "x"}])
    assert list(usuarios.columns) == nombres("usuarios")
    assert str(usuarios["id_usuario"].dtype) == "Int64" and usuarios["id_usuario"].tolist() == [1, 2]
    fotos = armar_tabla("fotos_etapa", [{"id_foto": 1, "fecha_subida": datetime(2026, 10, 20, 2, 30, tzinfo=timezone.utc)}])
    assert fotos["fecha_subida"][0] == pd.Timestamp("2026-10-19 23:30")


def test_el_origen_vacio_cumple_el_contrato():
    lectura = OrigenVacio().leer()
    verificar_lectura(lectura)
    assert lectura.origen == "vacio" and set(lectura.filas().values()) == {0}


@pytest.mark.parametrize("lectura, problema", [
    (_lectura(origen="planilla"), "origen"),
    (Lectura("simulado", datetime(2026, 10, 19), {t: tabla_vacia(t) for t in TABLAS if t != "usuarios"}), "usuarios"),
    (_lectura(organizaciones=tabla_vacia("organizaciones")[list(reversed(nombres("organizaciones")))]), "organizaciones"),
    (_lectura(usuarios=tabla_vacia("usuarios").assign(token_edicion=pd.Series(dtype="string"))), "token_edicion"),
    (_lectura(etapas=armar_tabla("etapas", [{"id_etapa_obra": 1, "fecha_inicio": datetime(2026, 10, 19, 9)}])), "fecha_inicio"),
])
def test_lo_que_no_cumple_el_contrato(lectura, problema):
    with pytest.raises(LecturaInvalida, match=problema):
        verificar_lectura(lectura)


def test_relaciones_informa_huerfanas_sin_fallar():
    lectura = _lectura(etapas=armar_tabla("etapas", [{"id_etapa_obra": 1, "id_solicitud": 99}]),
                       documentos=armar_tabla("documentos", [{"id_documento": 1, "tipo": "OTRO", "estado": "PENDIENTE"}]))
    advertencias = verificar_relaciones(lectura)
    assert any("etapas.id_solicitud" in a for a in advertencias)
    assert any("documentos sin dueño" in a for a in advertencias)
    assert verificar_relaciones(_lectura()) == []
