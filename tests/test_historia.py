from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from analitica.esquema import TABLAS
from analitica.historia import COLUMNAS_EVENTOS, estimar_desfase_horas, eventos_de_notificaciones
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
