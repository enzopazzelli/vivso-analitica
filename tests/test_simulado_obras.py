from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta

import numpy as np
import pytest
from faker import Faker

from analitica.calendario import CALENDARIO_JAVA
from analitica.catalogo import ESTADOS_ACTIVOS, etapa
from analitica.origenes.simulado_obras import EtapaReal, avance_fisico, generar_obras
from analitica.origenes.simulado_organizaciones import generar_organizaciones
from analitica.origenes.simulado_proyeccion import asignar_ids, proyectar
from analitica.origenes.simulado_solicitudes import generar_solicitudes
from analitica.parametros_simulacion import PARAMETROS

FIN = datetime(2030, 1, 1)


def faker_con_semilla(n):
    fake = Faker("es_AR")
    fake.seed_instance(n)
    return fake


def generar(p):
    orgs = generar_organizaciones(np.random.default_rng(8), faker_con_semilla(8), p)
    sols = generar_solicitudes(np.random.default_rng(9), faker_con_semilla(9), p, orgs)
    return orgs, sols, generar_obras(np.random.default_rng(10), faker_con_semilla(10), p, sols.obras)


def mundo_con(**cambios):
    return generar(replace(PARAMETROS, obras_previas=10, meses_posteriores=0, **cambios))


def proyectar_mundo(orgs, sols, obras, error_prorroga_java=True):
    con_ids, mapa = asignar_ids(orgs.hechos + sols.hechos + obras.hechos)
    return proyectar(con_ids, FIN, error_prorroga_java=error_prorroga_java), mapa


def por_obra(filas):
    obras = defaultdict(list)
    for e in filas["etapas"]:
        obras[e["id_solicitud"]].append(e)
    return {k: sorted(v, key=lambda e: e["numero"]) for k, v in obras.items()}


@pytest.fixture(scope="module")
def completo():
    return generar(PARAMETROS)


@pytest.fixture(scope="module")
def obras(completo):
    return completo[2]


@pytest.fixture(scope="module")
def proyectado(completo):
    return proyectar_mundo(*completo)


@pytest.fixture(scope="module")
def filas(proyectado):
    return proyectado[0]


def test_avance_fisico():
    etapa1 = EtapaReal("ETAPA_1", inicio=date(2026, 10, 16), fin_fisico=date(2026, 10, 20))   # 2 días hábiles
    assert avance_fisico([etapa1], date(2026, 10, 15)) == 0
    assert avance_fisico([etapa1], date(2026, 10, 19)) == pytest.approx(100 * 1 / 29)
    assert avance_fisico([etapa1], date(2026, 10, 30)) == pytest.approx(100 * 2 / 29)


def test_nada_se_registra_antes_de_ocurrir(obras):
    assert all(x.momento_registrado >= x.momento_real for x in obras.hechos)


def test_los_limites_son_los_de_java_y_a_lo_sumo_tres_rondas(obras, filas):
    for e in filas["etapas"]:
        if e["fecha_inicio"]:
            est = etapa(e["etapa"]).dias_estimados
            assert e["fecha_limite_original"] == CALENDARIO_JAVA.sumar_habiles(e["fecha_inicio"], est)
    envios = Counter(x.datos["id_etapa_obra"] for x in obras.hechos if x.accion == "enviar_etapa")
    assert max(envios.values()) <= 3


def test_sin_conexion_las_fotos_llegan_en_rafaga():
    _, _, obras = mundo_con(prob_sin_conexion_urbano=1.0, prob_sin_conexion_resto=1.0, prob_prorroga=0.0)
    for envio in (x for x in obras.hechos if x.accion == "enviar_etapa"):
        demora = envio.momento_registrado - envio.momento_real
        assert timedelta(days=1) <= demora <= timedelta(days=5, hours=23)
        fotos = [x for x in obras.hechos if x.accion == "subir_foto"
                 and x.datos["id_etapa_obra"] == envio.datos["id_etapa_obra"]
                 and envio.momento_registrado - timedelta(minutes=1) <= x.momento_registrado < envio.momento_registrado]
        assert all(f.momento_real < f.momento_registrado for f in fotos)


def test_con_el_error_de_java_las_prorrogadas_quedan_trabadas():
    filas, _ = proyectar_mundo(*mundo_con(prob_prorroga=1.0, duracion_mediana=3.0))
    prorrogadas = 0
    for etapas in por_obra(filas).values():
        for n, e in enumerate(etapas):
            if e["fecha_limite"] != e["fecha_limite_original"]:
                prorrogadas += 1
                assert e["estado"] == "PRORROGADA"
                assert all(posterior["fecha_inicio"] is None for posterior in etapas[n + 1:])
    assert prorrogadas > 0
    sin_error, _ = proyectar_mundo(*mundo_con(prob_prorroga=1.0, duracion_mediana=3.0, error_prorroga_java=False),
                                   error_prorroga_java=False)
    assert not [e for e in sin_error["etapas"] if e["estado"] == "PRORROGADA"]
    assert all(etapas[-1]["estado"] == "APROBADA" for etapas in por_obra(sin_error).values())


def test_la_proyeccion_no_viola_reglas_de_java(filas):
    for etapas in por_obra(filas).values():
        assert len(etapas) == 6
        assert sum(e["estado"] in ESTADOS_ACTIVOS for e in etapas) <= 1


def test_etapas_reales(completo, proyectado):
    _, sols, obras = completo
    filas, mapa = proyectado
    etapas = por_obra(filas)
    assert set(obras.etapas_reales) == {o.id_solicitud for o in sols.obras}
    for ref, reales in obras.etapas_reales.items():
        de_la_obra = {e["etapa"]: e for e in etapas[mapa[ref]]}
        for real in reales:
            assert real.inicio == de_la_obra[real.codigo]["fecha_inicio"]
            assert real.fin_fisico >= real.inicio


def test_visitas_de_obra_solo_si_se_activan(obras):
    assert not [x for x in obras.hechos if x.accion == "visita_obra"]
    _, _, con_visitas = mundo_con(visitas_obra=True)
    visitas = [x for x in con_visitas.hechos if x.accion == "visita_obra"]
    assert len(visitas) == sum(x.accion == "aprobar_etapa" for x in con_visitas.hechos) > 0
    assert all(0 <= v.datos["afo"] <= 100 for v in visitas)
