from collections import Counter
from dataclasses import replace
from datetime import datetime, time, timedelta

import numpy as np
import pytest
from faker import Faker

from analitica.catalogo import CLASIFICACIONES, TIPOS_DOCUMENTO, TIPOS_VIVIENDA
from analitica.origenes.simulado_organizaciones import generar_organizaciones
from analitica.origenes.simulado_proyeccion import asignar_ids, proyectar
from analitica.origenes.simulado_solicitudes import generar_solicitudes
from analitica.parametros_simulacion import LIMITES_PROVINCIA, PARAMETROS

FIN = datetime(2030, 1, 1)
TIPOS_FAMILIA = {t.codigo for t in TIPOS_DOCUMENTO.values() if t.ambito == "familia"}


def faker_con_semilla(n):
    fake = Faker("es_AR")
    fake.seed_instance(n)
    return fake


def generar(parametros=PARAMETROS):
    orgs = generar_organizaciones(np.random.default_rng(8), faker_con_semilla(8), parametros)
    return orgs, generar_solicitudes(np.random.default_rng(9), faker_con_semilla(9), parametros, orgs)


@pytest.fixture(scope="module")
def mundo():
    return generar()


@pytest.fixture(scope="module")
def sols(mundo):
    return mundo[1]


@pytest.fixture(scope="module")
def filas(mundo):
    orgs, sols = mundo
    con_ids, _ = asignar_ids(orgs.hechos + sols.hechos)
    return proyectar(con_ids, FIN)


def momentos(sols, accion):
    return {x.datos["id_solicitud"]: x.momento_registrado for x in sols.hechos if x.accion == accion}


def test_cuantas_obras_y_solicitudes(sols):
    fin_de_referencia = datetime.combine(PARAMETROS.fecha_referencia, time(23, 59, 59))
    assert len(sols.obras) == 300
    assert sum(o.inicio <= fin_de_referencia for o in sols.obras) == 120
    assert Counter(x.accion for x in sols.hechos)["registrar_solicitud"] == 400


def test_orden_y_plazos_del_tramite(sols):
    registro, expediente = momentos(sols, "registrar_solicitud"), momentos(sols, "asignar_expediente")
    visita, aprobacion = momentos(sols, "visita_inicial"), momentos(sols, "aprobar_solicitud")
    semi, confirmacion = momentos(sols, "semiaprobar_solicitud"), momentos(sols, "confirmar_correccion")
    dias = lambda a, b: (b.date() - a.date()).days
    for sol, reg in registro.items():
        if sol in expediente:
            assert reg < expediente[sol] and 2 <= dias(reg, expediente[sol]) <= 15
        if sol in visita:
            assert reg < visita[sol] and 3 <= dias(reg, visita[sol]) <= 30
        if sol in aprobacion:
            assert expediente[sol] < aprobacion[sol] and visita[sol] < aprobacion[sol]
            assert dias(visita[sol], aprobacion[sol]) >= 5
        if sol in confirmacion:
            assert semi[sol] < confirmacion[sol] < aprobacion.get(sol, FIN)
    for obra in sols.obras:
        assert aprobacion[obra.id_solicitud] < obra.inicio
        assert 0 <= dias(aprobacion[obra.id_solicitud], obra.inicio) <= 9


def test_las_organizaciones_estaban_aprobadas(mundo):
    orgs, sols = mundo
    aprobada_en = {o.cuit: o.aprobada_en for o in orgs.organizaciones}
    for x in sols.hechos:
        if x.accion == "registrar_solicitud":
            assert aprobada_en[x.datos["cuit_org"]] is not None and aprobada_en[x.datos["cuit_org"]] < x.momento_registrado


def test_familias_y_documentos(sols):
    for x in (h for h in sols.hechos if h.accion == "registrar_solicitud"):
        assert 1 <= x.datos["cantidad_familiares"] <= 8 and 5 <= x.datos["antiguedad_rancho"] <= 40
        tipos = [d["tipo"] for d in x.datos["documentos"]]
        assert 5 <= len(tipos) <= 7 and len(set(tipos)) == len(tipos) and set(tipos) <= TIPOS_FAMILIA


def test_visitas_y_ubicacion(sols):
    (lat_min, lat_max), (lon_min, lon_max) = LIMITES_PROVINCIA["latitud"], LIMITES_PROVINCIA["longitud"]
    for x in (h for h in sols.hechos if h.accion == "visita_inicial"):
        assert x.datos["clasificacion"] in CLASIFICACIONES
        assert lat_min <= x.datos["latitud"] <= lat_max and lon_min <= x.datos["longitud"] <= lon_max
    assert all(x.momento_real == x.momento_registrado for x in sols.hechos)


def test_la_proyeccion_no_viola_reglas_de_java(filas):
    aprobadas = {s["id_solicitud"]: s for s in filas["solicitudes"] if s["estado"] == "Aprobada"}
    familias_aprobadas = {s["id_familia"] for s in aprobadas.values()}
    assert not [d for d in filas["documentos"] if d["id_familia"] in familias_aprobadas and d["estado"] == "A_CORREGIR"]
    completadas = [v for v in filas["viviendas"] if v["tipo_vivienda"] is not None]
    assert 0.60 <= len(completadas) / len(aprobadas) <= 0.80
    for v in completadas:
        assert v["tipo_vivienda"] in TIPOS_VIVIENDA and 40 <= v["superficie"] <= 60 and v["cant_dormitorios"] in (2, 3)
    # Java no deja iniciar ni revisar una obra sin técnico asignado: el simulador lo asigna al aprobar ([E19]).
    assert all(s["id_tecnico_asignado"] is not None for s in aprobadas.values())


def test_sin_la_vista_del_arquitecto_no_hay_tecnico_asignado():
    orgs, sols = generar(replace(PARAMETROS, asignar_tecnico=False))
    con_ids, _ = asignar_ids(orgs.hechos + sols.hechos)
    aprobadas = [s for s in proyectar(con_ids, FIN)["solicitudes"] if s["estado"] == "Aprobada"]
    assert aprobadas and all(s["id_tecnico_asignado"] is None for s in aprobadas)
