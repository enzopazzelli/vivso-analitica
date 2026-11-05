from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from analitica.esquema import TABLAS
from analitica.historia import (COLUMNAS_EVENTOS, elegir_historia_de_etapas, estimar_desfase_horas,
                                eventos_de_la_lectura, eventos_de_notificaciones, eventos_para_contexto,
                                obras_con_notificaciones_incompletas, tabla_eventos, vinculos)
from analitica.origenes.base import Lectura, armar_tabla, tabla_vacia
from analitica.origenes.simulado import OrigenSimulado


def lectura_de(leido_en=datetime(2026, 11, 4, 12), **tablas) -> Lectura:
    todas = {t: tabla_vacia(t) for t in TABLAS}
    todas.update({nombre: armar_tabla(nombre, filas) for nombre, filas in tablas.items()})
    return Lectura("simulado", leido_en, todas)


def etapa(id_etapa_obra, id_solicitud, numero, estado, **campos):
    return {"id_etapa_obra": id_etapa_obra, "id_solicitud": id_solicitud, "etapa": f"ETAPA_{numero}", "numero": numero,
            "estado": estado, **campos}


def notificacion(id_notificacion, id_usuario, tipo, fecha, id_referencia=1):
    return {"id_notificacion": id_notificacion, "id_usuario": id_usuario, "tipo": tipo, "id_referencia": id_referencia,
            "fecha": fecha, "leida": False}


ETAPAS_DE_EJEMPLO = [
    etapa(1, 1, 1, "APROBADA", fecha_inicio=date(2026, 10, 16), fecha_limite=date(2026, 10, 20),
          fecha_limite_original=date(2026, 10, 20), fecha_envio=datetime(2026, 10, 19, 15, 0),
          fecha_revision=datetime(2026, 10, 20, 11, 30), id_revisor=5, observacion_tecnico="falta la capa aisladora"),
    etapa(2, 1, 2, "EN_REVISION", fecha_inicio=date(2026, 10, 20), fecha_limite=date(2026, 10, 22),
          fecha_limite_original=date(2026, 10, 22), fecha_envio=datetime(2026, 10, 21, 16, 10)),
    *[etapa(n, 1, n, "PENDIENTE") for n in range(3, 7)],
]
NOTIFICACIONES_DE_EJEMPLO = [
    notificacion(1, 11, "ETAPA_HABILITADA", datetime(2026, 10, 16, 10, 15, 42)),
    notificacion(2, 12, "ETAPA_HABILITADA", datetime(2026, 10, 16, 10, 15, 42)),
    notificacion(3, 5, "ETAPA_ENVIADA", datetime(2026, 10, 19, 9, 5, 30)),
    notificacion(4, 11, "ETAPA_OBSERVADA", datetime(2026, 10, 19, 12, 0, 10)),
    notificacion(5, 12, "ETAPA_OBSERVADA", datetime(2026, 10, 19, 12, 0, 11)),
    notificacion(6, 5, "ETAPA_ENVIADA", datetime(2026, 10, 19, 15, 0, 20)),
    notificacion(7, 11, "ETAPA_APROBADA", datetime(2026, 10, 20, 11, 30, 59)),
    notificacion(8, 12, "ETAPA_APROBADA", datetime(2026, 10, 20, 11, 30, 59)),
    notificacion(9, 5, "ETAPA_ENVIADA", datetime(2026, 10, 21, 16, 10, 0)),
]
ESPERADOS = [  # (numero, tipo, ronda, momento)
    (1, "inicio", None, datetime(2026, 10, 16, 10, 15, 42)),
    (1, "envio", 1, datetime(2026, 10, 19, 9, 5, 30)),
    (1, "observacion", None, datetime(2026, 10, 19, 12, 0, 10)),
    (1, "envio", 2, datetime(2026, 10, 19, 15, 0, 20)),
    (1, "aprobacion", None, datetime(2026, 10, 20, 11, 30, 59)),
    (2, "inicio", None, datetime(2026, 10, 20, 11, 30, 59)),
    (2, "envio", 1, datetime(2026, 10, 21, 16, 10, 0)),
]


@pytest.fixture
def lectura_con_notificaciones():
    return lectura_de(etapas=ETAPAS_DE_EJEMPLO, notificaciones=NOTIFICACIONES_DE_EJEMPLO)


def con_fechas_corridas(lectura: Lectura, horas: int) -> Lectura:
    notificaciones = lectura.tabla("notificaciones").copy()
    notificaciones["fecha"] = notificaciones["fecha"] + pd.Timedelta(hours=horas)
    return Lectura(lectura.origen, lectura.leido_en, lectura.tablas | {"notificaciones": notificaciones})


def lectura_obra_avanzada() -> Lectura:
    etapas = [etapa(21, 2, 1, "APROBADA", fecha_inicio=date(2026, 9, 29), fecha_revision=datetime(2026, 10, 1, 10)),
              etapa(22, 2, 2, "APROBADA", fecha_inicio=date(2026, 10, 1), fecha_revision=datetime(2026, 10, 5, 10)),
              etapa(23, 2, 3, "EN_REVISION", fecha_inicio=date(2026, 10, 5), fecha_envio=datetime(2026, 11, 4, 10)),
              *[etapa(20 + n, 2, n, "PENDIENTE") for n in range(4, 7)]]
    return lectura_de(etapas=etapas,
                      notificaciones=[notificacion(1, 5, "ETAPA_ENVIADA", datetime(2026, 11, 4, 10), id_referencia=2)])


def lectura_vacia() -> Lectura:
    return lectura_de()


def _tuplas(eventos: pd.DataFrame) -> list[tuple]:
    return [(int(e.numero), e.tipo, None if pd.isna(e.ronda) else int(e.ronda), e.momento.to_pydatetime())
            for e in eventos.itertuples()]


def test_eventos_desde_notificaciones(lectura_con_notificaciones):
    eventos = eventos_de_notificaciones(lectura_con_notificaciones)
    assert list(eventos.columns) == list(COLUMNAS_EVENTOS)
    assert _tuplas(eventos) == ESPERADOS
    assert set(eventos["fuente"]) == {"notificaciones"} and set(eventos["precision"]) == {"exacto"}
    assert set(eventos["entidad"]) == {"etapas"} and set(eventos["id_solicitud"]) == {1}
    assert list(eventos["clave"]) == ["1", "1", "1", "1", "1", "2", "2"]
    assert eventos["detalle"].tolist()[5] == {"derivado_de": "aprobacion"}


def test_el_desfase_se_estima_y_se_corrige(lectura_con_notificaciones):
    assert estimar_desfase_horas(lectura_con_notificaciones) == 0
    corrida = con_fechas_corridas(lectura_con_notificaciones, horas=3)
    assert estimar_desfase_horas(corrida) == 3
    assert _tuplas(eventos_de_notificaciones(corrida)) == ESPERADOS
    assert _tuplas(eventos_de_notificaciones(corrida, desfase_horas=0))[0][3] == datetime(2026, 10, 16, 13, 15, 42)


def test_notificaciones_que_empiezan_con_la_obra_avanzada():
    eventos = eventos_de_notificaciones(lectura_obra_avanzada())
    assert [(int(e.numero), e.tipo, e.clave) for e in eventos.itertuples()] == [(3, "envio", "23")]


def test_sin_notificaciones_no_hay_eventos():
    vacios = eventos_de_notificaciones(lectura_vacia())
    assert vacios.empty and list(vacios.columns) == list(COLUMNAS_EVENTOS)
    assert estimar_desfase_horas(lectura_vacia()) == 0


def test_contra_la_verdad_del_simulador():
    origen = OrigenSimulado(8, hasta=date(2026, 10, 15))
    lectura = origen.leer()
    eventos = eventos_de_notificaciones(lectura)
    numero = dict(zip(lectura.tabla("etapas")["id_etapa_obra"], lectura.tabla("etapas")["numero"]))
    por_accion = {"enviar_etapa": "envio", "aprobar_etapa": "aprobacion", "observar_etapa": "observacion",
                  "prorrogar_etapa": "prorroga", "rechazar_etapa": "rechazo"}
    esperados = sorted((int(numero[x.datos["id_etapa_obra"]]), por_accion[x.accion], x.momento_registrado)
                       for x in origen.verdad() if x.accion in por_accion and x.momento_registrado <= lectura.leido_en)
    obtenidos = sorted((int(e.numero), e.tipo, e.momento.to_pydatetime())
                       for e in eventos.itertuples() if e.tipo != "inicio")
    assert esperados and obtenidos == esperados


def test_notificaciones_que_empiezan_con_una_aprobacion():
    # fecha_revision está truncada al minuto: la aprobación notificada a las 11:30:59 es la misma de las 11:30.
    etapas = [etapa(31, 3, 1, "APROBADA", fecha_inicio=date(2026, 10, 1), fecha_revision=datetime(2026, 10, 5, 10)),
              etapa(32, 3, 2, "APROBADA", fecha_inicio=date(2026, 10, 5), fecha_revision=datetime(2026, 11, 4, 11, 30)),
              etapa(33, 3, 3, "EN_CURSO", fecha_inicio=date(2026, 11, 4)),
              *[etapa(30 + n, 3, n, "PENDIENTE") for n in range(4, 7)]]
    lectura = lectura_de(etapas=etapas, notificaciones=[
        notificacion(1, 11, "ETAPA_APROBADA", datetime(2026, 11, 4, 11, 30, 59), id_referencia=3)])
    eventos = eventos_de_notificaciones(lectura)
    assert [(int(e.numero), e.tipo) for e in eventos.itertuples()] == [(2, "aprobacion"), (3, "inicio")]
    assert obras_con_notificaciones_incompletas(eventos, lectura.tabla("etapas")) == set()


def sin_filas(lectura: Lectura, tabla: str, **igual_a) -> Lectura:
    datos = lectura.tabla(tabla)
    quitar = pd.Series(True, index=datos.index)
    for columna, valor in igual_a.items():
        quitar &= datos[columna] == valor
    return Lectura(lectura.origen, lectura.leido_en, lectura.tablas | {tabla: datos[~quitar].reset_index(drop=True)})


@pytest.fixture
def lectura_completa():
    return lectura_de(
        leido_en=datetime(2026, 10, 23, 23, 59, 59),
        solicitudes=[{"id_solicitud": 1, "estado": "Aprobada", "fecha_solicitud": date(2026, 9, 17),
                      "fecha_activacion": date(2026, 9, 19), "cuit_org": "30-1", "id_familia": 1}],
        familias=[{"id_familia": 1, "cantidad_familiares": 4, "antiguedad_rancho": 10}],
        viviendas=[{"id_vivienda": 1, "id_solicitud": 1, "id_familia": 1}],
        visitas_iniciales=[{"id_visita": 1, "id_solicitud": 1, "fecha_visita": datetime(2026, 9, 18, 10)}],
        etapas=[etapa(1, 1, 1, "APROBADA", fecha_inicio=date(2026, 10, 16), fecha_limite=date(2026, 10, 20),
                      fecha_limite_original=date(2026, 10, 20), fecha_envio=datetime(2026, 10, 19, 15, 0),
                      fecha_revision=datetime(2026, 10, 20, 11, 30)),
                etapa(2, 1, 2, "EN_CURSO", fecha_inicio=date(2026, 10, 20), fecha_limite=date(2026, 10, 22),
                      fecha_limite_original=date(2026, 10, 22)),
                *[etapa(n, 1, n, "PENDIENTE") for n in range(3, 7)]],
        fotos_etapa=[{"id_foto": 1, "id_etapa_obra": 1, "fecha_subida": datetime(2026, 10, 19, 9, 0, 30)}],
        documentos=[{"id_documento": 1, "tipo": "DNI_FAMILIARES", "estado": "A_CORREGIR", "id_familia": 1,
                     "fecha_subida": datetime(2026, 9, 17, 10), "fecha_revision": datetime(2026, 9, 18, 9)}],
        solicitudes_organizacion=[{"id_solicitud_org": 1, "cuit": "30-1", "estado": "Aprobada",
                                   "fecha_solicitud": date(2026, 8, 1), "fecha_aprobacion": date(2026, 8, 10)}],
    )


def lectura_prorrogada() -> Lectura:
    return lectura_de(etapas=[etapa(1, 1, 1, "EN_CURSO", fecha_inicio=date(2026, 10, 16),
                                    fecha_limite_original=date(2026, 10, 20), fecha_limite=date(2026, 10, 23),
                                    motivo_prorroga="lluvias")])


def test_vinculos_de_cada_fila_con_su_solicitud(lectura_completa):
    v = vinculos(lectura_completa)
    assert v.id_solicitud("fotos_etapa", {"id_etapa_obra": 1}) == 1
    assert v.id_solicitud("documentos", {"id_familia": 1}) == 1
    assert v.id_solicitud("notificaciones", {"id_referencia": 7}) == 7
    assert v.id_solicitud("documentos", {"id_familia": None}) is None
    assert v.id_solicitud("organizaciones", {"cuit": "30-1"}) is None


def test_eventos_de_una_lectura(lectura_completa):
    eventos = eventos_de_la_lectura(lectura_completa)
    assert list(eventos.columns) == list(COLUMNAS_EVENTOS)
    assert sorted(zip(eventos["entidad"], eventos["tipo"])) == sorted([
        ("solicitudes", "solicitud_registrada"), ("solicitudes", "solicitud_aprobada"), ("viviendas", "vivienda_creada"),
        ("visitas_iniciales", "visita_inicial"), ("etapas", "inicio"), ("etapas", "envio"), ("etapas", "aprobacion"),
        ("etapas", "inicio"), ("fotos_etapa", "foto_subida"), ("documentos", "documento_subido"),
        ("documentos", "documento_a_corregir"), ("solicitudes_organizacion", "alta_registrada"),
        ("solicitudes_organizacion", "alta_aprobada")])
    assert set(eventos.loc[eventos["entidad"] != "solicitudes_organizacion", "id_solicitud"]) == {1}
    assert eventos.loc[eventos["entidad"] == "solicitudes_organizacion", "id_solicitud"].isna().all()
    assert eventos.loc[eventos["tipo"] == "envio", "precision"].item() == "exacto"
    assert eventos.loc[eventos["tipo"] == "solicitud_registrada", "momento"].item() == pd.Timestamp(2026, 9, 17)
    assert eventos.loc[eventos["tipo"] == "vivienda_creada", "momento"].item() == pd.Timestamp(2026, 9, 19)
    assert set(eventos["fuente"]) == {"lectura"}


def test_la_prorroga_neta_de_una_lectura():
    eventos = eventos_de_la_lectura(lectura_prorrogada())
    prorroga = eventos[eventos["tipo"] == "prorroga"].iloc[0]
    assert prorroga["precision"] == "intervalo" and prorroga["momento"] == pd.Timestamp(2026, 11, 4, 12)
    assert prorroga["detalle"] == {"limite_anterior": "2026-10-20", "limite_nuevo": "2026-10-23", "motivo": "lluvias",
                                   "neta": True}


def test_la_historia_elige_notificaciones_o_versiones(lectura_con_notificaciones):
    otros = tabla_eventos([
        {"entidad": "etapas", "clave": "1", "id_solicitud": 1, "numero": 1, "tipo": "envio", "ronda": 1,
         "momento": datetime(2026, 10, 15, 9), "precision": "exacto", "fuente": "versiones"},     # antes de t0: queda
        {"entidad": "etapas", "clave": "1", "id_solicitud": 1, "numero": 1, "tipo": "envio", "ronda": 2,
         "momento": datetime(2026, 10, 19, 15), "precision": "exacto", "fuente": "versiones"},    # después: se descarta
        {"entidad": "etapas", "clave": "1", "id_solicitud": 1, "numero": 1, "tipo": "inicio",
         "momento": datetime(2026, 10, 16), "precision": "dia", "fuente": "versiones"},           # coincide: se descarta
        {"entidad": "solicitudes", "clave": "1", "id_solicitud": 1, "tipo": "expediente_asignado",
         "momento": datetime(2026, 9, 20), "precision": "intervalo", "fuente": "versiones"},     # no es de etapas: queda
    ])
    historia = elegir_historia_de_etapas(eventos_de_notificaciones(lectura_con_notificaciones), otros,
                                         lectura_con_notificaciones.tabla("etapas"))
    assert len(historia) == 7 + 2
    assert (historia["fuente"] == "versiones").sum() == 2


def test_una_obra_con_notificaciones_incompletas_usa_las_versiones(lectura_con_notificaciones):
    sin_aprobacion = sin_filas(lectura_con_notificaciones, "notificaciones", tipo="ETAPA_APROBADA")
    notificadas = eventos_de_notificaciones(sin_aprobacion)
    assert obras_con_notificaciones_incompletas(notificadas, sin_aprobacion.tabla("etapas")) == {1}
    historia = elegir_historia_de_etapas(notificadas, eventos_de_la_lectura(sin_aprobacion),
                                         sin_aprobacion.tabla("etapas"))
    assert set(historia.loc[historia["entidad"] == "etapas", "fuente"]) == {"lectura"}


def test_eventos_para_contexto_con_el_simulador():
    lectura = OrigenSimulado(8, hasta=date(2026, 10, 15)).leer()
    eventos = eventos_para_contexto(lectura)
    assert list(eventos.columns) == list(COLUMNAS_EVENTOS)
    assert set(eventos.loc[eventos["entidad"] == "etapas", "fuente"]) == {"notificaciones"}
    assert {"solicitud_registrada", "visita_inicial", "foto_subida", "alta_aprobada"} <= set(eventos["tipo"])
    assert eventos["momento"].is_monotonic_increasing
