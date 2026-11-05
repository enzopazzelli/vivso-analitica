import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DOCUMENTOS = [RAIZ / "README.md", *sorted((RAIZ / "docs").glob("*.md"))]
ENLACE = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
DIAGRAMAS_MINIMOS = {"README.md": 2, "docs/sistema-de-desarrollo.md": 8, "docs/pedido-a-desarrollo.md": 1,
                     "docs/simulacion.md": 6}


def test_estan_los_documentos_de_desarrollo():
    nombres = {d.name for d in DOCUMENTOS}
    assert {"README.md", "sistema-de-desarrollo.md", "pedido-a-desarrollo.md"} <= nombres


def test_los_enlaces_relativos_existen():
    for doc in DOCUMENTOS:
        for destino in ENLACE.findall(doc.read_text(encoding="utf-8")):
            if not destino.startswith(("http://", "https://", "mailto:")):
                assert (doc.parent / destino).exists(), f"{doc.name}: {destino}"


def test_sin_datos_de_conexion_ni_rastros_del_proceso():
    for doc in DOCUMENTOS:
        texto = doc.read_text(encoding="utf-8")
        assert ".aivencloud.com" not in texto, doc.name
        assert not re.search(r"superpowers|\bClaude\b|\bPlan [1-9]\b", texto), doc.name


def test_cada_supuesto_esta_documentado():
    codigo = (RAIZ / "analitica" / "parametros_simulacion.py").read_text(encoding="utf-8")
    documento = (RAIZ / "docs" / "simulacion.md").read_text(encoding="utf-8")
    etiquetas = set(re.findall(r"\[E\d+\]", codigo)) | {"[E18]"}
    assert etiquetas == {f"[E{n}]" for n in range(1, 23)}
    assert etiquetas <= set(re.findall(r"\[E\d+\]", documento))


def test_los_documentos_tienen_diagramas():
    for ruta, minimo in DIAGRAMAS_MINIMOS.items():
        assert (RAIZ / ruta).read_text(encoding="utf-8").count("```mermaid") >= minimo, ruta
