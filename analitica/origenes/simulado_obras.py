"""La verdad del simulador, tercera parte: las obras, etapa por etapa, con sus fotos, envíos, revisiones y prórrogas
([E4] a [E10], [E16], [E17]), y el avance físico real de cada obra ([E18]).

[E18] Avance físico: dentro de cada etapa crece en línea recta, en días hábiles de CALENDARIO_JAVA, desde su inicio
(cuando el sistema la activa) hasta su fin físico (el día del primer envío real: la obra está hecha aunque después la
observen o no se pueda enviar). Antes del inicio la etapa aporta 0 y desde el fin aporta sus días estimados.
avance = 100 × suma de aportes / 29. Sirve para evaluar el AFO contra la obra real.

Lo que hace la organización puede ir sin conexión: el momento real es cuando lo hizo y el registrado, cuando llegó al
servidor. Lo del técnico llega en su momento.
"""
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from math import log

import numpy as np
from faker import Faker

from analitica.calendario import CALENDARIO_JAVA
from analitica.catalogo import ETAPAS, TOTAL_DIAS_ESTIMADOS, etapa
from analitica.origenes.simulado_comun import dia_habil, entero, momento_habil
from analitica.origenes.simulado_proyeccion import Hecho, Ref
from analitica.origenes.simulado_solicitudes import ObraPorIniciar
from analitica.parametros_simulacion import (DEPARTAMENTOS_URBANOS, MOTIVOS_PRORROGA, OBSERVACIONES_ORGANIZACION,
                                              OBSERVACIONES_TECNICO, ParametrosSimulacion)


@dataclass(frozen=True)
class EtapaReal:
    codigo: str
    inicio: date          # cuando el sistema la activó
    fin_fisico: date      # el día del primer envío real


@dataclass
class MundoObras:
    hechos: list[Hecho] = field(default_factory=list)
    etapas_reales: dict[Ref, list[EtapaReal]] = field(default_factory=dict)    # por solicitud


def avance_fisico(etapas: Sequence[EtapaReal], dia: date) -> float:
    total = 0.0
    for real in etapas:
        estimados = etapa(real.codigo).dias_estimados
        if dia >= real.fin_fisico:
            total += estimados
        elif dia > real.inicio:
            duracion = CALENDARIO_JAVA.habiles_entre(real.inicio, real.fin_fisico)
            hechos = CALENDARIO_JAVA.habiles_entre(real.inicio, dia)
            total += estimados * min(1.0, hechos / duracion) if duracion > 0 else estimados
    return 100 * total / TOTAL_DIAS_ESTIMADOS


def _sin_micro(momento: datetime) -> datetime:
    return momento.replace(microsecond=0)


class _Generador:
    def __init__(self, rng: np.random.Generator, fake: Faker, p: ParametrosSimulacion):
        self.rng, self.fake, self.p = rng, fake, p
        self.mundo = MundoObras()

    def elegir(self, opciones):
        return opciones[int(self.rng.integers(len(opciones)))]

    def hecho(self, accion: str, registrado: datetime, autor, real: datetime | None = None, **datos) -> None:
        self.mundo.hechos.append(Hecho(accion, real or registrado, registrado, autor, datos))

    def obra(self, obra: ObraPorIniciar) -> None:
        p = self.p
        clave = obra.id_solicitud.clave
        ids_etapas = [Ref("etapas", f"{clave}-{e.numero}") for e in ETAPAS]
        self.hecho("iniciar_obra", obra.inicio, obra.tecnico, id_solicitud=obra.id_solicitud, etapas=ids_etapas)
        prob_sin_conexion = (p.prob_sin_conexion_urbano if obra.departamento in DEPARTAMENTOS_URBANOS
                             else p.prob_sin_conexion_resto)
        reales: list[EtapaReal] = []
        self.mundo.etapas_reales[obra.id_solicitud] = reales
        activacion = obra.inicio
        for e, id_etapa in zip(ETAPAS, ids_etapas):
            activacion = self.etapa(obra, e.codigo, id_etapa, activacion, prob_sin_conexion, reales)
            if activacion is None:      # trabada: la obra termina ahí
                return

    def etapa(self, obra: ObraPorIniciar, codigo: str, id_etapa: Ref, activacion: datetime, prob_sin_conexion: float,
              reales: list[EtapaReal]) -> datetime | None:
        """Genera las rondas de una etapa. Devuelve el momento en que se aprobó (activa la siguiente) o None si quedó
        trabada por el error de Java en las prórrogas."""
        p, rng = self.p, self.rng
        estimados = etapa(codigo).dias_estimados
        inicio = activacion.date()
        limite = CALENDARIO_JAVA.sumar_habiles(inicio, estimados)
        duracion = max(1, round(estimados * rng.lognormal(mean=log(p.duracion_mediana), sigma=p.duracion_desvio)))
        envio_real = momento_habil(CALENDARIO_JAVA.sumar_habiles(inicio, duracion), rng)
        reales.append(EtapaReal(codigo, inicio, envio_real.date()))
        desde, prorrogada = activacion, False
        for ronda in range(1, p.rondas_max + 1):
            usuario = self.elegir(obra.usuarios_org)
            fotos, borrado, envio = self.ronda(id_etapa, ronda, desde, envio_real, prob_sin_conexion)
            fin_del_limite = datetime.combine(limite, time(23, 59, 59))
            if not prorrogada and envio > fin_del_limite and rng.random() < p.prob_prorroga:
                momento = momento_habil(limite, rng)
                if momento <= desde:
                    momento = desde + timedelta(minutes=entero(rng, (5, 60)))
                limite = CALENDARIO_JAVA.sumar_habiles(max(limite, momento.date()), entero(rng, p.prorroga_habiles))
                self.hecho("prorrogar_etapa", momento, obra.tecnico, id_etapa_obra=id_etapa, fecha_limite=limite,
                           motivo=str(self.elegir(MOTIVOS_PRORROGA)))
                prorrogada = True
                # Desde la prórroga Java no acepta fotos (FotoEtapaService pide EN_CURSO u OBSERVADA).
                fotos = [f for f in fotos if f["registrado"] < momento]
                if borrado and (borrado["registrado"] >= momento or borrado["foto"] not in fotos):
                    borrado = None
                if p.error_prorroga_java:
                    self.fotos(fotos, borrado, usuario)
                    return None         # enviarEtapa no acepta PRORROGADA: queda trabada
            self.fotos(fotos, borrado, usuario)
            texto = (str(self.elegir(OBSERVACIONES_ORGANIZACION)) if rng.random() < p.prob_observacion_organizacion
                     else None)
            self.hecho("enviar_etapa", envio, usuario, real=envio_real, id_etapa_obra=id_etapa,
                       observacion_organizacion=texto)
            dia_revision = dia_habil(CALENDARIO_JAVA.sumar_habiles(envio.date(), entero(rng, p.espera_revision_habiles)))
            revision = momento_habil(dia_revision, rng)
            if revision <= envio:
                revision = envio + timedelta(minutes=entero(rng, (5, 120)))
            if ronda < p.rondas_max and rng.random() < p.prob_observacion:
                self.hecho("observar_etapa", revision, obra.tecnico, id_etapa_obra=id_etapa,
                           observacion_tecnico=str(self.elegir(OBSERVACIONES_TECNICO)))
                desde = revision
                envio_real = momento_habil(
                    CALENDARIO_JAVA.sumar_habiles(revision.date(), entero(rng, p.correccion_habiles)), rng)
                continue
            self.hecho("aprobar_etapa", revision, obra.tecnico, id_etapa_obra=id_etapa)
            if p.visitas_obra:
                self.hecho("visita_obra", revision + timedelta(minutes=1), obra.tecnico,
                           id_visita_obra=Ref("visitas_obra", id_etapa.clave), id_vivienda=obra.id_vivienda,
                           afo=round(avance_fisico(reales, revision.date())), observaciones=None)
            return revision
        raise AssertionError("la última ronda siempre se aprueba")

    def ronda(self, id_etapa: Ref, ronda: int, desde: datetime, envio_real: datetime, prob_sin_conexion: float):
        """Las fotos de una ronda (con su momento real y el de llegada), una foto borrada si corresponde, y el momento
        en que el envío llega al servidor."""
        p, rng = self.p, self.rng
        cantidad = 0 if rng.random() < p.prob_ronda_sin_fotos else entero(rng, p.fotos_por_ronda)
        margen = timedelta(minutes=1)
        ventana = envio_real - desde - 2 * margen
        reales = sorted(_sin_micro(desde + margen + ventana * float(u)) for u in rng.random(cantidad))
        fotos = []
        for n, real in enumerate(reales):
            nombre = f"IMG_{real:%Y%m%d_%H%M%S}_{n + 1}.jpg"
            fotos.append({"id_foto": Ref("fotos_etapa", f"{id_etapa.clave}-{ronda}-{n + 1}"), "id_etapa": id_etapa,
                          "real": real, "registrado": real, "nombre": nombre})
        if rng.random() < prob_sin_conexion:
            # [E9] Sin señal: todo queda en el celular y llega junto, en ráfaga, al reconectarse. Lo que se borra en el
            # celular nunca llega.
            reconexion = _sin_micro(envio_real + timedelta(days=entero(rng, p.demora_sin_conexion_dias),
                                                           minutes=int(rng.integers(0, 601))))
            for n, foto in enumerate(fotos):
                foto["registrado"] = reconexion + timedelta(seconds=n + 1)
            return fotos, None, reconexion + timedelta(seconds=len(fotos) + 1)
        borrado = None
        if fotos and rng.random() < p.prob_foto_borrada:
            foto = self.elegir(fotos)
            momento = _sin_micro(foto["real"] + (envio_real - foto["real"]) * float(rng.uniform(0.1, 0.9)))
            borrado = {"foto": foto, "registrado": momento}
        return fotos, borrado, envio_real

    def fotos(self, fotos: list[dict], borrado: dict | None, usuario: Ref) -> None:
        for foto in fotos:
            self.hecho("subir_foto", foto["registrado"], usuario, real=foto["real"], id_foto=foto["id_foto"],
                       id_etapa_obra=foto["id_etapa"], nombre_archivo=foto["nombre"],
                       ruta_archivo=f"uploads/etapas/{foto['id_etapa'].clave}/{foto['nombre']}")
        if borrado:
            self.hecho("borrar_foto", borrado["registrado"], usuario, id_foto=borrado["foto"]["id_foto"])


def generar_obras(rng: np.random.Generator, fake: Faker, p: ParametrosSimulacion,
                  obras: list[ObraPorIniciar]) -> MundoObras:
    generador = _Generador(rng, fake, p)
    for obra in obras:
        generador.obra(obra)
    return generador.mundo
