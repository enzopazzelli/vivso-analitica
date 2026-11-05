from datetime import date, datetime, timedelta

import pytest

from analitica.esquema import TABLAS
from analitica.origenes.simulado_proyeccion import Hecho, Ref, ReglaDeJava, asignar_ids, proyectar

VIERNES = datetime(2026, 10, 16, 10, 15, 42)
FIN = datetime(2030, 1, 1)
PERSONA = dict(dni="20111222", nombre="Ana", apellido="Paz", correo="ana@example.com", telefono="3855000000",
               fecha_alta_cargo=date(2025, 1, 1), domicilio="Belgrano 100")
PRESIDENTE = dict(id_integrante=1, id_usuario=11, username="ana.paz")
TESORERO = dict(id_integrante=2, id_usuario=12, username="luis.paz")


def h(accion, cuando, autor=1, real=None, **datos):
    return Hecho(accion, real or cuando, cuando, autor, datos)


def alta(cuando, id_alta=1, cuit="30-11111111-1", documentos=()):
    return h("registrar_alta", cuando, None, id_solicitud_org=id_alta, cuit=cuit, nombre="Asociación Civil Paz",
             tipo="Asociación civil", dom_legal="Belgrano 100", cpe="1234", fecha_vencimiento_vigencia=date(2027, 1, 1),
             fecha_ultima_asamblea=date(2025, 6, 1), presidente=PERSONA,
             tesorero=PERSONA | {"dni": "20333444", "nombre": "Luis", "correo": "luis@example.com"},
             documentos=list(documentos))


def solicitud_aprobada(cuando=VIERNES - timedelta(days=30)):
    return [
        alta(cuando),
        h("aprobar_alta", cuando + timedelta(hours=1), 9, id_solicitud_org=1, presidente=PRESIDENTE, tesorero=TESORERO),
        h("registrar_solicitud", cuando + timedelta(days=1), 11, id_solicitud=1, id_familia=1, cuit_org="30-11111111-1",
          cantidad_familiares=4, antiguedad_rancho=10,
          documentos=[dict(id_documento=1, tipo="DNI_FAMILIARES", nombre_original="dni.pdf", url="u/1")]),
        h("asignar_expediente", cuando + timedelta(days=2), 9, id_solicitud=1, num_exp="EXP-2026-0001"),
        h("aprobar_solicitud", cuando + timedelta(days=3), 9, id_solicitud=1, id_vivienda=1, id_tecnico_asignado=5),
    ]


def obra(*hechos_de_etapas):
    return solicitud_aprobada() + [h("iniciar_obra", VIERNES, 5, id_solicitud=1, etapas=[1, 2, 3, 4, 5, 6]),
                                   *hechos_de_etapas]


def foto(cuando, id_foto=1, id_etapa=1, autor=11, real=None):
    return h("subir_foto", cuando, autor, real, id_foto=id_foto, id_etapa_obra=id_etapa, nombre_archivo="a.jpg",
             ruta_archivo=f"r/{id_foto}.jpg")


def etapas(filas):
    return sorted(filas["etapas"], key=lambda e: e["numero"])


def test_sin_hechos_hay_trece_tablas_vacias():
    filas = proyectar([], FIN)
    assert set(filas) == set(TABLAS) and all(v == [] for v in filas.values())


def test_aprobar_una_solicitud_crea_la_vivienda_vacia():
    filas = proyectar(solicitud_aprobada(), FIN)
    sol = filas["solicitudes"][0]
    assert (sol["estado"], sol["fecha_activacion"], sol["id_revisor"]) == ("Aprobada", date(2026, 9, 19), 9)
    vivienda = filas["viviendas"][0]
    assert {k for k, v in vivienda.items() if v is not None} == {"id_vivienda", "id_solicitud", "id_familia"}


def test_no_se_aprueba_sin_expediente():
    with pytest.raises(ReglaDeJava, match="expediente"):
        proyectar([x for x in solicitud_aprobada() if x.accion != "asignar_expediente"], FIN)


def test_iniciar_obra_crea_seis_etapas_y_activa_la_primera():
    e = etapas(proyectar(obra(), FIN))
    assert [x["estado"] for x in e] == ["EN_CURSO"] + ["PENDIENTE"] * 5
    assert (e[0]["fecha_inicio"], e[0]["fecha_limite"], e[0]["fecha_limite_original"]) == (
        date(2026, 10, 16), date(2026, 10, 20), date(2026, 10, 20))
    assert e[1]["fecha_inicio"] is None


def test_iniciar_obra_exige_la_solicitud_aprobada():
    hechos = [x for x in obra() if x.accion != "aprobar_solicitud"]
    with pytest.raises(ReglaDeJava, match="Aprobada"):
        proyectar(hechos, FIN)


def test_el_ciclo_de_una_etapa_como_en_java():
    lunes = datetime(2026, 10, 19, 9, 0, 30)
    e = etapas(proyectar(obra(
        foto(lunes),
        h("enviar_etapa", lunes + timedelta(minutes=5), 11, id_etapa_obra=1, observacion_organizacion="listo"),
        h("observar_etapa", lunes + timedelta(hours=3), 5, id_etapa_obra=1, observacion_tecnico="falta la capa aisladora"),
        foto(lunes + timedelta(hours=5), id_foto=2, autor=12),
        h("enviar_etapa", lunes + timedelta(hours=6), 12, id_etapa_obra=1, observacion_organizacion=None),
        h("aprobar_etapa", datetime(2026, 10, 20, 11, 30, 59), 5, id_etapa_obra=1),
    ), FIN))
    assert (e[0]["estado"], e[0]["fecha_revision"], e[0]["id_revisor"]) == ("APROBADA", datetime(2026, 10, 20, 11, 30), 5)
    assert (e[0]["fecha_envio"], e[0]["id_usuario_envio"]) == (datetime(2026, 10, 19, 15, 0), 12)
    assert e[0]["observacion_organizacion"] is None                    # el segundo envío pisa el texto del primero
    assert e[0]["observacion_tecnico"] == "falta la capa aisladora"    # aprobar no la borra
    assert (e[1]["estado"], e[1]["fecha_inicio"], e[1]["fecha_limite"]) == ("EN_CURSO", date(2026, 10, 20), date(2026, 10, 22))


def test_fotos_solo_en_curso_u_observada():
    lunes = datetime(2026, 10, 19, 9, 0)
    assert proyectar(obra(foto(lunes), h("borrar_foto", lunes + timedelta(minutes=1), 11, id_foto=1)), FIN)["fotos_etapa"] == []
    with pytest.raises(ReglaDeJava, match="EN_REVISION"):
        proyectar(obra(h("enviar_etapa", lunes, 11, id_etapa_obra=1, observacion_organizacion=None),
                       foto(lunes + timedelta(minutes=1))), FIN)
    with pytest.raises(ReglaDeJava, match="PENDIENTE"):
        proyectar(obra(foto(lunes, id_etapa=2)), FIN)


def test_una_etapa_prorrogada_queda_trabada_por_el_error_de_java():
    martes = datetime(2026, 10, 20, 17, 0)
    hechos = obra(h("prorrogar_etapa", martes, 5, id_etapa_obra=1, fecha_limite=date(2026, 10, 23), motivo="lluvias"),
                  h("enviar_etapa", martes + timedelta(days=2), 11, id_etapa_obra=1, observacion_organizacion=None))
    with pytest.raises(ReglaDeJava, match="PRORROGADA"):
        proyectar(hechos, FIN)
    e1 = etapas(proyectar(hechos, FIN, error_prorroga_java=False))[0]
    assert (e1["estado"], e1["fecha_limite"], e1["fecha_limite_original"], e1["motivo_prorroga"]) == (
        "EN_REVISION", date(2026, 10, 23), date(2026, 10, 20), "lluvias")


@pytest.mark.parametrize("nueva, problema", [(date(2026, 10, 24), "hábil"), (date(2026, 10, 20), "posterior")])
def test_la_prorroga_exige_una_fecha_habil_posterior_al_limite(nueva, problema):
    with pytest.raises(ReglaDeJava, match=problema):
        proyectar(obra(h("prorrogar_etapa", datetime(2026, 10, 19, 9), 5, id_etapa_obra=1, fecha_limite=nueva,
                         motivo="x")), FIN)


@pytest.mark.parametrize("accion", ["aprobar_etapa", "observar_etapa"])
def test_el_tecnico_solo_revisa_etapas_enviadas(accion):
    with pytest.raises(ReglaDeJava, match="EN_CURSO"):
        proyectar(obra(h(accion, datetime(2026, 10, 19, 9), 5, id_etapa_obra=1, observacion_tecnico="x")), FIN)


def test_solo_el_tecnico_asignado_inicia_la_obra():
    # EtapaObraService.validarTecnicoAsignado: sin técnico asignado, o con otro, Java responde 403.
    with pytest.raises(ReglaDeJava, match="técnico asignado"):
        proyectar(solicitud_aprobada() + [h("iniciar_obra", VIERNES, 6, id_solicitud=1, etapas=[1, 2, 3, 4, 5, 6])], FIN)
    sin_tecnico = [x for x in solicitud_aprobada() if x.accion != "aprobar_solicitud"] + [
        h("aprobar_solicitud", VIERNES - timedelta(days=27), 9, id_solicitud=1, id_vivienda=1, id_tecnico_asignado=None),
        h("iniciar_obra", VIERNES, 5, id_solicitud=1, etapas=[1, 2, 3, 4, 5, 6])]
    with pytest.raises(ReglaDeJava, match="técnico asignado"):
        proyectar(sin_tecnico, FIN)


@pytest.mark.parametrize("accion, enviada, datos", [
    ("aprobar_etapa", True, {}), ("observar_etapa", True, {"observacion_tecnico": "x"}),
    ("prorrogar_etapa", False, {"fecha_limite": date(2026, 10, 23), "motivo": "x"}),
])
def test_solo_el_tecnico_asignado_revisa_y_prorroga(accion, enviada, datos):
    lunes = datetime(2026, 10, 19, 9, 0)
    previos = [h("enviar_etapa", lunes, 11, id_etapa_obra=1, observacion_organizacion=None)] if enviada else []
    with pytest.raises(ReglaDeJava, match="técnico asignado"):
        proyectar(obra(*previos, h(accion, lunes + timedelta(hours=1), 6, id_etapa_obra=1, **datos)), FIN)


def test_lo_registrado_despues_del_corte_no_aparece():
    llegada = datetime(2026, 10, 22, 20, 0, 0)
    hechos = obra(foto(llegada, real=datetime(2026, 10, 19, 10)))
    assert proyectar(hechos, llegada - timedelta(seconds=1))["fotos_etapa"] == []
    assert proyectar(hechos, llegada)["fotos_etapa"][0]["fecha_subida"] == llegada


def test_los_ids_siguen_el_orden_de_llegada_al_servidor():
    a, b, operador = Ref("solicitudes", "a"), Ref("solicitudes", "b"), Ref("usuarios", "op")
    t = datetime(2026, 10, 19, 9)
    con_ids, mapa = asignar_ids([
        h("registrar_solicitud", t + timedelta(hours=2), operador, id_solicitud=a),
        h("registrar_solicitud", t + timedelta(hours=1), None, id_solicitud=b),
        h("iniciar_obra", t + timedelta(hours=3), operador, id_solicitud=a,
          etapas=[Ref("etapas", f"a-{n}") for n in range(1, 7)]),
    ])
    assert (mapa[b], mapa[a], mapa[operador]) == (1, 2, 1)
    assert [x.datos["id_solicitud"] for x in con_ids] == [1, 2, 2]
    assert con_ids[1].autor == 1 and con_ids[2].datos["etapas"] == [1, 2, 3, 4, 5, 6]


def _solicitud_registrada():
    return solicitud_aprobada()[:3]


def test_la_correccion_exige_los_documentos_reemplazados_y_borra_la_observacion():
    marcado = _solicitud_registrada() + [
        h("semiaprobar_solicitud", VIERNES, 9, id_solicitud=1, motivo="falta el DNI", campos_observados=["dni", "domicilio"]),
        h("marcar_documento", VIERNES + timedelta(minutes=1), 9, id_documento=1, motivo="ilegible"),
    ]
    with pytest.raises(ReglaDeJava, match="A_CORREGIR"):
        proyectar(marcado + [h("confirmar_correccion", VIERNES + timedelta(hours=2), 11, id_solicitud=1)], FIN)
    corregido = marcado + [
        h("reemplazar_documento", VIERNES + timedelta(hours=1), 11, id_documento=1, nombre_original="dni2.pdf", url="u/1b"),
        h("confirmar_correccion", VIERNES + timedelta(hours=2), 11, id_solicitud=1),
    ]
    antes = proyectar(corregido, VIERNES + timedelta(minutes=30))["solicitudes"][0]
    assert (antes["estado"], antes["campos_observados"], antes["observacion"]) == ("SemiAprobada", "dni,domicilio", "falta el DNI")
    despues = proyectar(corregido, FIN)["solicitudes"][0]
    assert (despues["estado"], despues["observacion"], despues["campos_observados"]) == ("Pendiente", None, None)


def test_documento_marcado_y_reemplazado():
    filas = proyectar(_solicitud_registrada() + [
        h("marcar_documento", VIERNES, 9, id_documento=1, motivo="ilegible"),
        h("reemplazar_documento", VIERNES + timedelta(days=1), 11, id_documento=1, nombre_original="dni2.pdf", url="u/1b"),
    ], FIN)
    doc = filas["documentos"][0]
    assert (doc["estado"], doc["nombre_original"], doc["url"]) == ("PENDIENTE", "dni2.pdf", "u/1b")
    assert (doc["motivo_observacion"], doc["id_revisor"], doc["fecha_revision"]) == (None, None, VIERNES)


def _documentos_de_alta():
    return [dict(id_documento=1, tipo="ALTA_AFIP", nombre_original="afip.pdf", url="o/1"),
            dict(id_documento=2, tipo="NOTA_SOLICITUD", nombre_original="nota.pdf", url="o/2")]


def test_alta_observada_corregida_y_aprobada():
    filas = proyectar([
        alta(VIERNES, documentos=_documentos_de_alta()),
        h("observar_alta", VIERNES + timedelta(days=1), 9, id_solicitud_org=1, motivo="vigencia vencida",
          campos_observados=["fechaVencimientoVigencia"], documentos=[2]),
        h("corregir_alta", VIERNES + timedelta(days=2), None, id_solicitud_org=1,
          reemplazos=[dict(id_documento=2, nombre_original="nota2.pdf", url="o/2b")]),
        h("aprobar_alta", VIERNES + timedelta(days=3), 9, id_solicitud_org=1, presidente=PRESIDENTE, tesorero=TESORERO),
    ], FIN)
    assert [o["cuit"] for o in filas["organizaciones"]] == ["30-11111111-1"]
    integrantes = sorted(filas["integrantes"], key=lambda i: i["id_integrante"])
    assert [(i["cargo"], i["activo"], i["id_usuario"]) for i in integrantes] == [("PRESIDENTE", True, 11), ("TESORERO", True, 12)]
    usuarios = sorted(filas["usuarios"], key=lambda u: u["id_usuario"])
    assert [(u["id_usuario"], u["rol"], u["email"]) for u in usuarios] == [
        (11, "INTEGRANTE", "ana@example.com"), (12, "INTEGRANTE", "luis@example.com")]
    assert {(d["estado"], d["cuit_org"]) for d in filas["documentos"]} == {("APROBADO", "30-11111111-1")}
    alta_final = filas["solicitudes_organizacion"][0]
    assert (alta_final["estado"], alta_final["fecha_aprobacion"]) == ("Aprobada", date(2026, 10, 19))
    assert (alta_final["motivo"], alta_final["campos_observados"]) == (None, None)


def test_alta_rechazada():
    filas = proyectar([alta(VIERNES, documentos=_documentos_de_alta()),
                       h("rechazar_alta", VIERNES + timedelta(days=5), 9, id_solicitud_org=1, motivo="sin personería")], FIN)
    rechazada = filas["solicitudes_organizacion"][0]
    assert (rechazada["estado"], rechazada["motivo"], rechazada["fecha_rechazo"]) == ("Rechazada", "sin personería", date(2026, 10, 21))
    assert {d["estado"] for d in filas["documentos"]} == {"RECHAZADO"}
    assert filas["organizaciones"] == []


def test_un_cuit_con_un_alta_no_puede_pedir_otra():
    with pytest.raises(ReglaDeJava, match="30-11111111-1"):
        proyectar([alta(VIERNES),
                   h("rechazar_alta", VIERNES + timedelta(days=5), 9, id_solicitud_org=1, motivo="sin personería"),
                   alta(VIERNES + timedelta(days=10), id_alta=2)], FIN)
