import pytest

from analitica.catalogo import (CLASIFICACIONES, ESTADOS_ACTIVOS, ESTADOS_DOCUMENTO, ESTADOS_ETAPA, ESTADOS_SOLICITUD,
                                ETAPAS, ROLES, TIPOS_CARGO, TIPOS_DOCUMENTO, TIPOS_VIVIENDA, TOTAL_DIAS_ESTIMADOS, etapa,
                                grupo_organizacion, siguiente)


def test_las_seis_etapas_como_en_java():
    assert [(e.codigo, e.numero, e.dias_estimados) for e in ETAPAS] == [
        ("ETAPA_1", 1, 2), ("ETAPA_2", 2, 2), ("ETAPA_3", 3, 10), ("ETAPA_4", 4, 8), ("ETAPA_5", 5, 5), ("ETAPA_6", 6, 2)]
    assert TOTAL_DIAS_ESTIMADOS == 29
    assert etapa("ETAPA_3").nombre == "Elevación y techo"
    assert etapa("ETAPA_6").descripcion.startswith("Pintura interior y exterior")
    assert siguiente("ETAPA_5").codigo == "ETAPA_6" and siguiente("ETAPA_6") is None
    with pytest.raises(KeyError, match="ETAPA_9"):
        etapa("ETAPA_9")


def test_estados_y_roles_como_los_guarda_la_base():
    assert ESTADOS_ETAPA == ("PENDIENTE", "EN_CURSO", "EN_REVISION", "PRORROGADA", "OBSERVADA", "APROBADA")
    assert ESTADOS_ACTIVOS == ("EN_CURSO", "EN_REVISION", "PRORROGADA", "OBSERVADA")
    assert ESTADOS_SOLICITUD == ("Pendiente", "SemiAprobada", "Aprobada", "Rechazada")
    assert ROLES == ("ADMIN", "OPERADOR", "ARQUITECTO", "TECNICO", "INTEGRANTE")


def test_enums_con_su_valor():
    assert len(CLASIFICACIONES) == 13
    assert (CLASIFICACIONES["TIPO_1A"], CLASIFICACIONES["TIPO_5D"]) == ("1a", "5d")
    assert (CLASIFICACIONES["DERRUMBE"], CLASIFICACIONES["OTRA"]) == ("DERRUMBE", "OTRA")
    assert TIPOS_VIVIENDA == {"URBANA": "Urbana", "RURAL": "Rural", "ECONOMICA": "Económica"}
    assert ESTADOS_DOCUMENTO == {"PENDIENTE": "Pendiente", "A_CORREGIR": "A corregir", "APROBADO": "Aprobado",
                                 "RECHAZADO": "Rechazado"}
    assert list(TIPOS_CARGO) == ["PRESIDENTE", "VICEPRESIDENTE", "TESORERO", "SECRETARIO", "VOCAL", "INTEGRANTE"]


def test_los_19_tipos_de_documento_con_su_ambito():
    assert len(TIPOS_DOCUMENTO) == 19
    ambitos = [t.ambito for t in TIPOS_DOCUMENTO.values()]
    assert {a: ambitos.count(a) for a in set(ambitos)} == {"organizacion": 10, "familia": 7, "obra": 1, "otro": 1}
    assert TIPOS_DOCUMENTO["CERTIFICADO_RESIDENCIA_FAMILIA"].valor == "Certificado de Residencia  de familia"
    assert TIPOS_DOCUMENTO["CONSTANCIA_CUENTA_BANCARIA"].valor == "Constancia de cuenta bancaria (BSE)"
    assert TIPOS_DOCUMENTO["FOTO_OBRA"].ambito == "obra"


@pytest.mark.parametrize("tipo, nombre, esperado", [
    ("Municipio", "Municipalidad de Fernández", ("OG", "Municipio")),
    ("Comisión Municipal", "Comisión Municipal de Clodomira", ("OG", "Comisión Municipal")),
    ("comision municipal", None, ("OG", "Comisión Municipal")),
    ("COM. MUN.", None, ("OG", "Comisión Municipal")),
    ("Intendencia", None, ("OG", "Municipio")),
    ("Asociación civil", "Asociación Civil Manos Unidas", ("ONG", "ONG")),
    ("Cooperativa", "Cooperativa de Trabajo Municipio Unido", ("ONG", "ONG")),  # el tipo alcanza: no se mira el nombre
    ("Comisión de Fomento", None, ("ONG", "ONG")),
    (None, "Municipalidad de Quimilí", ("OG", "Municipio")),
    ("", "MUN. DE LA CAPITAL", ("OG", "Municipio")),
    ("Otro", "Comisionado Municipal de Pinto", ("OG", "Comisión Municipal")),
    ("", "ASOC.CIV.SOC.COMUN.DE ACCION", ("ONG", "ONG")),
    (None, None, ("ONG", "ONG")),
])
def test_grupo_organizacion(tipo, nombre, esperado):
    assert grupo_organizacion(tipo, nombre) == esperado
