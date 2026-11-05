"""El origen simulado: un mundo inventado con las tablas y las reglas del sistema de Desarrollo.

Tiene dos capas (ver docs/simulacion.md): la verdad —los hechos de organizaciones, solicitudes y obras, con su momento
real, su momento de llegada al servidor y su autor— y la proyección, que los aplica con las reglas de Java hasta un
corte. El mundo se genera una sola vez por instancia, alrededor de la fecha de referencia, y no depende del corte: dos
lecturas con cortes distintos ven el mismo mundo en dos momentos.
"""
from datetime import date, datetime, time

import numpy as np
from faker import Faker

from analitica.calendario import ZONA, ahora_local
from analitica.esquema import TABLAS
from analitica.origenes.base import Lectura, armar_tabla, verificar_lectura
from analitica.origenes.simulado_obras import EtapaReal, avance_fisico, generar_obras
from analitica.origenes.simulado_organizaciones import generar_organizaciones
from analitica.origenes.simulado_proyeccion import Hecho, asignar_ids, proyectar
from analitica.origenes.simulado_solicitudes import generar_solicitudes
from analitica.parametros_simulacion import PARAMETROS, ParametrosSimulacion


def fin_del_corte(hasta: date | datetime) -> datetime:
    """Una fecha corta al final de ese día; un datetime con zona pasa a hora de Buenos Aires sin zona."""
    if isinstance(hasta, datetime):
        return hasta.astimezone(ZONA).replace(tzinfo=None) if hasta.tzinfo else hasta
    return datetime.combine(hasta, time(23, 59, 59))


def _faker(semilla: int) -> Faker:
    fake = Faker("es_AR")
    fake.seed_instance(semilla)
    return fake


class OrigenSimulado:
    codigo = "simulado"

    def __init__(self, semilla: int = 8, hasta: date | datetime | None = None,
                 parametros: ParametrosSimulacion = PARAMETROS):
        self.semilla = semilla
        self.hasta = hasta
        self.parametros = parametros
        self._hechos: list[Hecho] | None = None
        self._etapas_reales: dict[int, list[EtapaReal]] = {}

    def _generar(self) -> list[Hecho]:
        if self._hechos is None:
            # Un generador por parte del mundo: cambiar una parte no corre el azar de las otras.
            rng_org, rng_sol, rng_obra = (np.random.default_rng(s) for s in np.random.SeedSequence(self.semilla).spawn(3))
            p = self.parametros
            orgs = generar_organizaciones(rng_org, _faker(self.semilla), p)
            sols = generar_solicitudes(rng_sol, _faker(self.semilla + 1), p, orgs)
            obras = generar_obras(rng_obra, _faker(self.semilla + 2), p, sols.obras)
            self._hechos, mapa = asignar_ids(orgs.hechos + sols.hechos + obras.hechos)
            self._etapas_reales = {mapa[ref]: reales for ref, reales in obras.etapas_reales.items()}
        return self._hechos

    def leer(self) -> Lectura:
        return self.leer_al(self.hasta if self.hasta is not None else ahora_local())

    def leer_al(self, corte: date | datetime) -> Lectura:
        momento = fin_del_corte(corte)
        filas = proyectar(self._generar(), momento, error_prorroga_java=self.parametros.error_prorroga_java,
                          desfase_notificaciones_horas=self.parametros.desfase_notificaciones_horas)
        lectura = Lectura(origen=self.codigo, leido_en=momento, tablas={t: armar_tabla(t, filas[t]) for t in TABLAS})
        verificar_lectura(lectura)
        return lectura

    def verdad(self) -> list[Hecho]:
        """Todos los hechos del mundo, con ids, ordenados por momento de llegada (para pruebas y evaluación)."""
        return list(self._generar())

    def avance_real(self, id_solicitud: int, dia: date) -> float | None:
        """El avance físico real de una obra ese día ([E18]); None si la solicitud nunca llega a obra."""
        self._generar()
        reales = self._etapas_reales.get(id_solicitud)
        return None if reales is None else avance_fisico(reales, dia)
