from datetime import date, datetime, timedelta, timezone

import pytest

from analitica.calendario import CALENDARIO_JAVA, Calendario, fecha_local

VIERNES, SABADO, DOMINGO = date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 18)
LUNES, MARTES = date(2026, 10, 19), date(2026, 10, 20)
PUENTE, MEMORIA = date(2026, 3, 23), date(2026, 3, 24)          # lunes y martes, feriados de 2026
CON_FERIADOS = Calendario({PUENTE, MEMORIA})


def test_un_datetime_se_cuenta_por_su_fecha():
    calendario = Calendario([date(2026, 10, 12)])
    assert calendario.es_habil(datetime(2026, 10, 12, 9, 30)) is False
    assert calendario.sumar_habiles(datetime(2026, 10, 9, 18, 0), 1) == date(2026, 10, 13)


@pytest.mark.parametrize("desde, n, esperado", [
    (VIERNES, 2, MARTES),                                         # el ejemplo de CalendarioService.java
    (SABADO, 1, LUNES), (DOMINGO, 1, LUNES), (SABADO, 2, MARTES),
    (VIERNES, 0, VIERNES), (SABADO, 0, SABADO),
    (LUNES, 5, date(2026, 10, 26)), (VIERNES, 10, date(2026, 10, 30)),
])
def test_sumar_habiles_como_java(desde, n, esperado):
    assert CALENDARIO_JAVA.sumar_habiles(desde, n) == esperado


def test_dias_negativos_dan_error():
    with pytest.raises(ValueError):
        CALENDARIO_JAVA.sumar_habiles(LUNES, -1)


def test_un_feriado_en_el_medio():
    assert CALENDARIO_JAVA.sumar_habiles(date(2026, 3, 20), 2) == MEMORIA
    assert CON_FERIADOS.sumar_habiles(date(2026, 3, 20), 2) == date(2026, 3, 26)
    assert CON_FERIADOS.habiles_entre(date(2026, 3, 20), date(2026, 3, 26)) == 2
    assert not CON_FERIADOS.es_habil(PUENTE) and CALENDARIO_JAVA.es_habil(PUENTE)


def test_habiles_entre_cuenta_despues_de_a_y_hasta_b():
    assert CALENDARIO_JAVA.habiles_entre(VIERNES, MARTES) == 2
    assert CALENDARIO_JAVA.habiles_entre(VIERNES, VIERNES) == 0
    assert CALENDARIO_JAVA.habiles_entre(SABADO, DOMINGO) == 0
    assert CALENDARIO_JAVA.habiles_entre(MARTES, VIERNES) == -2
    # El martes 02:30 UTC es el lunes 23:30 en Buenos Aires.
    assert CALENDARIO_JAVA.habiles_entre(datetime(2026, 10, 16, 23, 30),
                                         datetime(2026, 10, 20, 2, 30, tzinfo=timezone.utc)) == 1


@pytest.mark.parametrize("calendario", [CALENDARIO_JAVA, CON_FERIADOS])
def test_sumar_y_contar_son_inversas_durante_dos_anios(calendario):
    for desplazamiento in range(730):
        a = date(2025, 1, 1) + timedelta(days=desplazamiento)
        for n in (0, 1, 2, 5, 8, 10, 29):
            assert calendario.habiles_entre(a, calendario.sumar_habiles(a, n)) == n


def test_restantes_como_java():
    assert CALENDARIO_JAVA.habiles_restantes(VIERNES, MARTES) == 2
    assert CALENDARIO_JAVA.habiles_restantes(MARTES, MARTES) == 0
    assert CALENDARIO_JAVA.habiles_restantes(MARTES, LUNES) == 0


def test_fecha_local_sin_zona_y_con_zona():
    assert fecha_local(datetime(2026, 10, 16, 23, 30)) == VIERNES
    assert fecha_local(datetime(2026, 10, 17, 2, 30, tzinfo=timezone.utc)) == VIERNES
