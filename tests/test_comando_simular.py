import subprocess
import sys
from dataclasses import replace

from analitica.__main__ import main
from analitica.origenes.simulado import OrigenSimulado
from analitica.parametros_simulacion import PARAMETROS


def test_comando_simular(capsys, tmp_path):
    assert main(["simular", "--hasta", "2026-10-15", "--csv", str(tmp_path / "csv")]) == 0
    salida = capsys.readouterr().out
    assert "Origen simulado · semilla 8 · corte 2026-10-15 23:59" in salida
    assert "Filas por tabla:" in salida and "Obras por etapa actual:" in salida
    assert "Relaciones: sin filas huérfanas" in salida and "Aviso" not in salida
    assert len(list((tmp_path / "csv").glob("*.csv"))) == 14


def test_simular_muestra_las_obras_rechazadas(capsys, monkeypatch):
    monkeypatch.setattr("analitica.__main__.OrigenSimulado",
                        lambda semilla, hasta: OrigenSimulado(semilla, hasta=hasta,
                                                              parametros=replace(PARAMETROS, prob_rechazo_etapa=1.0)))
    assert main(["simular", "--hasta", "2026-10-15"]) == 0
    salida = capsys.readouterr().out
    assert "Etapa 1: Replanteo y cimientos (RECHAZADA)" in salida
    assert "Notificaciones:" in salida


def test_con_el_simulador_apagado_avisa(capsys, monkeypatch):
    monkeypatch.setenv("ANALITICA_ORIGEN", "vacio")
    assert main(["simular", "--hasta", "2026-10-15"]) == 0
    assert capsys.readouterr().out.startswith("Aviso: ANALITICA_ORIGEN=vacio")


def test_el_nucleo_no_carga_fastapi_ni_streamlit():
    codigo = ("import sys, analitica.catalogo, analitica.calendario, analitica.feriados, analitica.esquema, "
              "analitica.origenes.base, analitica.origenes.simulado, analitica.__main__; "
              "print(sorted(m for m in ('fastapi', 'streamlit') if m in sys.modules))")
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert resultado.stdout.strip() == "[]"
