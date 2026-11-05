from collections import Counter
from datetime import datetime, time, timedelta

import numpy as np
import pytest
from faker import Faker

from analitica.catalogo import grupo_organizacion
from analitica.origenes.simulado_comun import username_java
from analitica.origenes.simulado_organizaciones import generar_organizaciones
from analitica.origenes.simulado_proyeccion import asignar_ids, proyectar
from analitica.parametros_simulacion import PARAMETROS

FIN = datetime(2030, 1, 1)


def faker_con_semilla(n):
    fake = Faker("es_AR")
    fake.seed_instance(n)
    return fake


def _generar(semilla=8):
    return generar_organizaciones(np.random.default_rng(semilla), faker_con_semilla(semilla), PARAMETROS)


@pytest.fixture(scope="module")
def mundo():
    return _generar()


@pytest.mark.parametrize("nombre, apellido, existentes, esperado", [
    ("Ana", "Paz", set(), "ana.paz"),
    ("José Luis", "Pérez", set(), "josluis.prez"),                 # Java borra todo lo que no es [a-z0-9.]
    ("José Luis", "Pérez", {"josluis.prez"}, "josé luis.pérez1"),  # y al repetir usa la base sin limpiar
    ("Ana", "Paz", {"ana.paz", "ana.paz1"}, "ana.paz2"),
])
def test_username_como_java(nombre, apellido, existentes, esperado):
    assert username_java(nombre, apellido, existentes) == esperado


def test_personal_y_altas(mundo):
    assert (len(mundo.tecnicos), len(mundo.operadores), len(mundo.arquitectos), len(mundo.administradores)) == (6, 2, 1, 1)
    acciones = Counter(x.accion for x in mundo.hechos)
    assert (acciones["registrar_alta"], acciones["aprobar_alta"], acciones["rechazar_alta"]) == (16, 12, 2)
    assert acciones["observar_alta"] == acciones["corregir_alta"]


def test_el_grupo_inventado_es_el_que_deduce_el_catalogo(mundo):
    altas = [x.datos for x in mundo.hechos if x.accion == "registrar_alta"]
    por_cuit = {o.cuit: o for o in mundo.organizaciones}
    assert {a["tipo"] for a in altas} <= {"Municipio", "Comisión Municipal", "Asociación civil", "Cooperativa"}
    assert all(grupo_organizacion(a["tipo"], a["nombre"]).grupo == por_cuit[a["cuit"]].grupo for a in altas)


def test_las_fechas_de_las_altas(mundo):
    ref = datetime.combine(PARAMETROS.fecha_referencia, time())
    aprobadas = [o.aprobada_en for o in mundo.organizaciones if o.aprobada_en]
    assert len(aprobadas) == 12 and all(ref - timedelta(days=510) <= a <= ref - timedelta(days=420) for a in aprobadas)
    assert all(x.momento_real == x.momento_registrado for x in mundo.hechos)


def test_la_proyeccion_no_viola_reglas_de_java(mundo):
    con_ids, _ = asignar_ids(mundo.hechos)
    filas = proyectar(con_ids, FIN)
    assert len(filas["organizaciones"]) == 12
    con_usuario = [i for i in filas["integrantes"] if i["id_usuario"] is not None]
    assert len(con_usuario) == 24
    usuarios = filas["usuarios"]
    assert len({u["username"] for u in usuarios}) == len(usuarios) == len({u["email"] for u in usuarios})
    de_integrantes = {i["id_usuario"] for i in con_usuario}
    assert {u["rol"] for u in usuarios if u["id_usuario"] in de_integrantes} == {"INTEGRANTE"}


def test_reproducible(mundo):
    assert _generar().hechos == mundo.hechos
    assert _generar(9).hechos != mundo.hechos
