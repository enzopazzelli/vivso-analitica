import json
from datetime import date

import httpx
import pytest

from analitica import feriados
from analitica.__main__ import main
from analitica.feriados import cargar

FORMATO = [  # como responde https://api.argentinadatos.com/v1/feriados/2026 (verificado el 21/10/2026)
    {"fecha": "2026-03-23", "tipo": "puente", "nombre": "Puente turístico no laborable"},
    {"fecha": "2026-03-24", "tipo": "inamovible", "nombre": "Día Nacional de la Memoria por la Verdad y la Justicia"},
    {"fecha": "2026-06-15", "tipo": "trasladable", "nombre": "Paso a la Inmortalidad del General Martín Miguel de Güemes"},
]


def test_baja_guarda_y_despues_lee_el_archivo(tmp_path):
    pedidos = []
    r = cargar([2026], carpeta=tmp_path, descargar=lambda url: pedidos.append(url) or FORMATO)
    assert r.fechas == {date(2026, 3, 23), date(2026, 3, 24), date(2026, 6, 15)}
    assert pedidos == ["https://api.argentinadatos.com/v1/feriados/2026"] and r.fuentes == {2026: "descarga"}
    assert json.loads((tmp_path / "2026.json").read_text(encoding="utf-8")) == FORMATO
    r2 = cargar([2026], carpeta=tmp_path, descargar=lambda url: pytest.fail("no tenía que bajar"))
    assert r2.fechas == r.fechas and r2.fuentes == {2026: "archivo"} and r2.advertencias == []
    assert not r2.calendario().es_habil(date(2026, 3, 24))


def test_solo_cuentan_los_tipos_pedidos(tmp_path):
    assert cargar([2026], carpeta=tmp_path, tipos=("inamovible",), descargar=lambda url: FORMATO).fechas == {date(2026, 3, 24)}


def test_sin_conexion_ni_archivo_usa_los_nacionales_y_avisa(tmp_path):
    def sin_red(url):
        raise httpx.ConnectError("sin red")
    r = cargar([2026], carpeta=tmp_path, descargar=sin_red)
    assert {date(2026, 5, 25), date(2026, 7, 9)} <= r.fechas
    assert r.fuentes == {2026: "respaldo"} and "holidays" in r.advertencias[0]
    assert not (tmp_path / "2026.json").exists()


def test_un_archivo_danado_se_vuelve_a_bajar(tmp_path):
    (tmp_path / "2026.json").write_text("{no es json", encoding="utf-8")
    r = cargar([2026], carpeta=tmp_path, descargar=lambda url: FORMATO)
    assert r.fuentes == {2026: "descarga"} and "dañado" in r.advertencias[0]


def test_una_respuesta_con_otro_formato_no_se_guarda(tmp_path):
    r = cargar([2026], carpeta=tmp_path, descargar=lambda url: [{"date": "2026-01-01"}])
    assert r.fuentes == {2026: "respaldo"}
    assert not (tmp_path / "2026.json").exists()


def test_un_archivo_con_fechas_de_otro_tipo_se_vuelve_a_bajar(tmp_path):
    (tmp_path / "2026.json").write_text('[{"fecha": null, "tipo": "inamovible"}]', encoding="utf-8")
    r = cargar([2026], carpeta=tmp_path, descargar=lambda url: FORMATO)
    assert r.fuentes == {2026: "descarga"} and "dañado" in r.advertencias[0]


def test_una_respuesta_con_fechas_de_otro_tipo_no_se_guarda(tmp_path):
    r = cargar([2026], carpeta=tmp_path, descargar=lambda url: [{"fecha": 20260101, "tipo": "inamovible"}])
    assert r.fuentes == {2026: "respaldo"}
    assert not (tmp_path / "2026.json").exists()


def test_comando_feriados(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(feriados, "descargar_json", lambda url: FORMATO)
    assert main(["feriados", "2026"]) == 0
    assert "2026: 3 feriados (descarga)" in capsys.readouterr().out
    assert (tmp_path / "datos_locales" / "feriados" / "2026.json").exists()
