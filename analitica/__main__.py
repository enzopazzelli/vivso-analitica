"""Comandos del servicio: `python -m analitica <comando>`.

    simular [--semilla N] [--hasta AAAA-MM-DD] [--csv CARPETA]   muestra el origen simulado a un corte
    feriados ANIO [ANIO ...]   baja (o lee) los feriados de esos años y los deja en datos_locales/feriados/
"""
import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from analitica import feriados
from analitica.catalogo import ESTADOS_ACTIVOS, ESTADOS_ETAPA, etapa
from analitica.config import cargar_configuracion
from analitica.esquema import TABLAS
from analitica.origenes.base import verificar_relaciones
from analitica.origenes.simulado import OrigenSimulado

_FINALIZADA = "Obra finalizada"


def _obras_por_etapa_actual(etapas: pd.DataFrame) -> list[tuple[str, int]]:
    """Como lo muestra la web de Desarrollo: la etapa activa de cada obra con su estado, u «Obra finalizada»."""
    cuentas: dict[tuple, int] = {}
    for _, de_la_obra in etapas.groupby("id_solicitud"):
        activas = de_la_obra[de_la_obra["estado"].isin(ESTADOS_ACTIVOS)]
        if len(activas):
            fila = activas.iloc[0]
            clave = (int(fila["numero"]), ESTADOS_ETAPA.index(fila["estado"]), fila["etapa"], fila["estado"])
        elif (de_la_obra["estado"] == "APROBADA").all():
            clave = (99, 0, None, None)
        else:
            continue
        cuentas[clave] = cuentas.get(clave, 0) + 1
    return [(_FINALIZADA if codigo is None else f"Etapa {numero}: {etapa(codigo).nombre} ({estado})", n)
            for (numero, _, codigo, estado), n in sorted(cuentas.items())]


def _simular(args: argparse.Namespace) -> int:
    if cargar_configuracion().origen == "vacio":
        print("Aviso: ANALITICA_ORIGEN=vacio; el servicio no usa el simulador. Esto es solo una vista del simulador.")
    origen = OrigenSimulado(args.semilla, hasta=args.hasta)
    lectura = origen.leer()
    print(f"Origen simulado · semilla {args.semilla} · corte {lectura.leido_en:%Y-%m-%d %H:%M}")
    print("Filas por tabla:")
    for tabla, filas in lectura.filas().items():
        print(f"  {tabla:<26}{filas:>6}")
    print("Obras por etapa actual:")
    obras = _obras_por_etapa_actual(lectura.tabla("etapas"))
    for texto, n in obras:
        print(f"  {texto:<52}{n:>5}")
    if not obras:
        print("  (ninguna obra iniciada a este corte)")
    advertencias = verificar_relaciones(lectura)
    print("Relaciones: sin filas huérfanas" if not advertencias else "Relaciones:")
    for advertencia in advertencias:
        print(f"  {advertencia}")
    if args.csv:
        carpeta = Path(args.csv)
        carpeta.mkdir(parents=True, exist_ok=True)
        for tabla in TABLAS:
            lectura.tabla(tabla).to_csv(carpeta / f"{tabla}.csv", index=False, encoding="utf-8-sig")
        print(f"CSV: {len(TABLAS)} archivos en {carpeta}")
    return 0


def _feriados(args: argparse.Namespace) -> int:
    cfg = cargar_configuracion()
    resultado = feriados.cargar(args.anios, url=cfg.feriados_url, tipos=cfg.feriados_tipos)
    fechas = sorted(resultado.fechas)
    for anio in args.anios:
        cantidad = sum(1 for f in fechas if f.year == anio)
        print(f"{anio}: {cantidad} feriados ({resultado.fuentes[anio]})")
    for advertencia in resultado.advertencias:
        print(f"Advertencia: {advertencia}")
    return 0


def _argumentos() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m analitica", description="Servicio de analítica de VIVSO")
    comandos = parser.add_subparsers(dest="comando", required=True)
    cmd_simular = comandos.add_parser("simular", help="muestra el origen simulado a un corte")
    cmd_simular.add_argument("--semilla", type=int, default=8)
    cmd_simular.add_argument("--hasta", type=date.fromisoformat, default=None, metavar="AAAA-MM-DD",
                             help="fecha de corte (por defecto, ahora)")
    cmd_simular.add_argument("--csv", default=None, metavar="CARPETA", help="guarda las 13 tablas como CSV")
    cmd_simular.set_defaults(funcion=_simular)
    cmd_feriados = comandos.add_parser("feriados", help="baja los feriados de ArgentinaDatos y los guarda")
    cmd_feriados.add_argument("anios", nargs="+", type=int, metavar="ANIO")
    cmd_feriados.set_defaults(funcion=_feriados)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _argumentos().parse_args(argv)
    return args.funcion(args)


if __name__ == "__main__":
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
    sys.exit(main())
