from collections import Counter
from dataclasses import replace
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from analitica.catalogo import TIPOS_NOTIFICACION
from analitica.esquema import TABLAS
from analitica.origenes.base import OrigenNoDisponible, crear_origen, verificar_lectura, verificar_relaciones
from analitica.origenes.simulado import OrigenSimulado
from analitica.origenes.vacio import OrigenVacio
from analitica.parametros_simulacion import PARAMETROS

REF = date(2026, 10, 15)


@pytest.fixture(scope="module")
def origen():
    return OrigenSimulado(8, hasta=REF)


@pytest.fixture(scope="module")
def lectura(origen):
    return origen.leer()


def test_cumple_el_contrato_y_es_reproducible(lectura):
    verificar_lectura(lectura)
    otra = OrigenSimulado(8, hasta=REF).leer()
    for t in TABLAS:
        pd.testing.assert_frame_equal(lectura.tabla(t), otra.tabla(t))
    assert not lectura.tabla("usuarios").equals(OrigenSimulado(9, hasta=REF).leer().tabla("usuarios"))


def test_los_supuestos_a_la_fecha_de_referencia(lectura):
    assert lectura.origen == "simulado" and lectura.leido_en == datetime(2026, 10, 15, 23, 59, 59)
    assert lectura.tabla("etapas")["id_solicitud"].nunique() == 120
    assert len(lectura.tabla("organizaciones")) == 12
    assert lectura.tabla("solicitudes_organizacion")["estado"].value_counts().to_dict() == {
        "Aprobada": 12, "Rechazada": 2, "Pendiente": 2}
    roles = lectura.tabla("usuarios")["rol"].value_counts().to_dict()
    assert {r: roles[r] for r in ("TECNICO", "OPERADOR", "ARQUITECTO", "ADMIN")} == {
        "TECNICO": 6, "OPERADOR": 2, "ARQUITECTO": 1, "ADMIN": 1}
    assert lectura.tabla("integrantes")["id_usuario"].notna().sum() == 24
    assert verificar_relaciones(lectura) == []


def test_otro_corte_ve_el_mismo_mundo_antes(origen, lectura):
    antes = origen.leer_al(REF - timedelta(days=30))
    assert len(antes.tabla("solicitudes")) < len(lectura.tabla("solicitudes"))
    assert set(antes.tabla("etapas")["id_etapa_obra"]) <= set(lectura.tabla("etapas")["id_etapa_obra"])
    assert antes.tabla("fotos_etapa")["fecha_subida"].max() <= pd.Timestamp(REF - timedelta(days=29))


def test_corte_antes_del_mundo_da_tablas_vacias(origen):
    assert set(origen.leer_al(date(2020, 1, 1)).filas().values()) == {0}


def test_mundo_sin_obras():
    lectura = OrigenSimulado(8, hasta=REF, parametros=replace(PARAMETROS, obras_previas=0)).leer()
    assert lectura.filas()["etapas"] == 0 and lectura.filas()["organizaciones"] == 12


def test_corte_en_medio_de_una_ronda_sin_conexion(origen):
    envio = next(x for x in origen.verdad()
                 if x.accion == "enviar_etapa" and x.momento_registrado - x.momento_real >= timedelta(days=1))
    id_etapa = envio.datos["id_etapa_obra"]
    antes = origen.leer_al(envio.momento_real + timedelta(hours=1)).tabla("etapas").set_index("id_etapa_obra")
    assert antes.loc[id_etapa, "estado"] != "EN_REVISION"
    despues = origen.leer_al(envio.momento_registrado).tabla("etapas").set_index("id_etapa_obra")
    assert despues.loc[id_etapa, "estado"] == "EN_REVISION"
    assert despues.loc[id_etapa, "fecha_envio"] == pd.Timestamp(envio.momento_registrado.replace(second=0))


def test_la_lectura_coincide_con_la_verdad(origen, lectura):
    hechos = [x for x in origen.verdad() if x.momento_registrado <= lectura.leido_en]
    fotos = sum(x.accion == "subir_foto" for x in hechos) - sum(x.accion == "borrar_foto" for x in hechos)
    assert fotos == len(lectura.tabla("fotos_etapa"))


def test_las_notificaciones_del_mundo_simulado(origen, lectura):
    hechos = [x for x in origen.verdad() if x.momento_registrado <= lectura.leido_en]
    cuenta = Counter(x.accion for x in hechos)
    a_la_organizacion = sum(cuenta[a] for a in ("iniciar_obra", "aprobar_etapa", "observar_etapa",
                                               "prorrogar_etapa", "rechazar_etapa"))
    notificaciones = lectura.tabla("notificaciones")
    assert len(notificaciones) == 2 * a_la_organizacion + cuenta["enviar_etapa"] > 0
    assert set(notificaciones["tipo"]) <= set(TIPOS_NOTIFICACION)
    assert not notificaciones["leida"].any()


def test_el_desfase_de_las_notificaciones():
    corrido = OrigenSimulado(8, hasta=REF, parametros=replace(PARAMETROS, desfase_notificaciones_horas=3)).leer()
    normal = OrigenSimulado(8, hasta=REF).leer()
    diferencia = corrido.tabla("notificaciones")["fecha"] - normal.tabla("notificaciones")["fecha"]
    assert len(diferencia) > 0 and (diferencia == pd.Timedelta(hours=3)).all()


def test_avance_real(origen, lectura):
    etapas = lectura.tabla("etapas")
    terminada = int(etapas[(etapas["etapa"] == "ETAPA_6") & (etapas["estado"] == "APROBADA")]["id_solicitud"].iloc[0])
    assert origen.avance_real(terminada, REF) == pytest.approx(100)
    assert origen.avance_real(terminada, date(2020, 1, 1)) == 0
    iniciadas = {x.datos["id_solicitud"] for x in origen.verdad() if x.accion == "iniciar_obra"}
    sin_obra = set(lectura.tabla("solicitudes")["id_solicitud"]) - iniciadas
    assert sin_obra and all(origen.avance_real(int(i), REF) is None for i in sin_obra)


def test_crear_origen(monkeypatch):
    assert isinstance(crear_origen("vacio"), OrigenVacio)
    assert isinstance(crear_origen("simulado"), OrigenSimulado)
    with pytest.raises(OrigenNoDisponible, match="mysql"):
        crear_origen("mysql")
    monkeypatch.setenv("ANALITICA_ORIGEN", "vacio")
    assert isinstance(crear_origen(), OrigenVacio)
