"""La verdad del simulador, segunda parte: solicitudes de vivienda con su familia (solo conteos), sus documentos, el
técnico asignado, la visita inicial y la vivienda ([E11] a [E15], [E19], [E20], [E22]).

Primero se arma el plan de fechas de cada solicitud —hacia atrás desde el inicio de obra en las obras, hacia adelante en
las que no llegan a obra—; después se ordenan por registro (para numerar los expedientes) y se emiten los hechos. Todo
pasa con conexión: momento real = registrado (la visita inicial guarda además la hora del celular, que es la misma).
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np
from faker import Faker

from analitica.calendario import CALENDARIO_JAVA
from analitica.catalogo import TIPOS_DOCUMENTO
from analitica.origenes.simulado_comun import entero, momento_habil
from analitica.origenes.simulado_organizaciones import MundoOrganizaciones, OrganizacionSimulada
from analitica.origenes.simulado_proyeccion import Hecho, Ref
from analitica.parametros_simulacion import (CAMPOS_OBSERVABLES, DEPARTAMENTOS, LIMITES_PROVINCIA, MOTIVOS_DOCUMENTO,
                                              MOTIVOS_RECHAZO, MOTIVOS_SEMIAPROBACION, OBSERVACIONES_VISITA,
                                              PESOS_CLASIFICACION, ParametrosSimulacion)

_TIPOS_FAMILIA = sorted(t.codigo for t in TIPOS_DOCUMENTO.values() if t.ambito == "familia")
_FINALES_SIN_OBRA = ("pendiente", "semiaprobada", "rechazada", "aprobada_sin_iniciar")
_POR_NOMBRE = {d.nombre: d for d in DEPARTAMENTOS}


@dataclass(frozen=True)
class ObraPorIniciar:
    id_solicitud: Ref
    id_vivienda: Ref
    inicio: datetime                 # cuando el técnico la inicia (hora del servidor)
    departamento: str
    tecnico: Ref
    usuarios_org: tuple[Ref, ...]    # presidente y tesorero: los que cargan fotos y envían etapas


@dataclass
class MundoSolicitudes:
    hechos: list[Hecho] = field(default_factory=list)
    obras: list[ObraPorIniciar] = field(default_factory=list)


@dataclass
class _Plan:
    clave: str
    final: str                       # "obra" o uno de _FINALES_SIN_OBRA
    org: OrganizacionSimulada
    registro: datetime
    expediente: datetime | None = None
    visita: datetime | None = None
    semi: datetime | None = None
    confirmacion: datetime | None = None
    aprobacion: datetime | None = None
    rechazo: datetime | None = None
    inicio: datetime | None = None


class _Generador:
    def __init__(self, rng: np.random.Generator, fake: Faker, p: ParametrosSimulacion, orgs: MundoOrganizaciones):
        self.rng, self.fake, self.p, self.orgs = rng, fake, p, orgs
        self.aprobadas = [o for o in orgs.organizaciones if o.aprobada_en]
        self.pesos_org = rng.dirichlet(np.ones(len(self.aprobadas)))
        self.pesos_dep = np.array([d.peso for d in DEPARTAMENTOS])
        self.pesos_dep = self.pesos_dep / self.pesos_dep.sum()
        self.mundo = MundoSolicitudes()

    # --- ayudas ---

    def dia_entre(self, desde: date, hasta: date) -> date:
        """Un día hábil al azar de [desde, hasta]; si no hay ninguno, cualquier día del rango."""
        dias = [desde + timedelta(days=i) for i in range(max(0, (hasta - desde).days) + 1)]
        opciones = [d for d in dias if CALENDARIO_JAVA.es_habil(d)] or dias
        return opciones[int(self.rng.integers(len(opciones)))]

    def momento(self, dia: date) -> datetime:
        return momento_habil(dia, self.rng)

    def elegir(self, opciones):
        return opciones[int(self.rng.integers(len(opciones)))]

    def hecho(self, accion: str, momento: datetime, autor, **datos) -> None:
        self.mundo.hechos.append(Hecho(accion, momento, momento, autor, datos))

    def dias_habiles(self, desde: date, hasta: date) -> list[date]:
        return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)
                if CALENDARIO_JAVA.es_habil(desde + timedelta(days=i))]

    # --- planes de fechas ---

    def planes(self) -> list[_Plan]:
        p, ref = self.p, self.p.fecha_referencia
        previas = self.dias_habiles(ref - timedelta(days=30 * p.meses_previos), ref)
        posteriores = self.dias_habiles(ref + timedelta(days=1), ref + timedelta(days=30 * p.meses_posteriores))
        cantidad_posteriores = round(p.obras_previas * p.meses_posteriores / p.meses_previos)
        inicios = ([self.elegir(previas) for _ in range(p.obras_previas)]
                   + [self.elegir(posteriores) for _ in range(cantidad_posteriores)])
        planes = [self.plan_de_obra(n, dia) for n, dia in enumerate(inicios)]
        sin_obra = round(len(inicios) * p.prob_sin_obra / (1 - p.prob_sin_obra))
        for n in range(sin_obra):
            planes.append(self.plan_sin_obra(n, _FINALES_SIN_OBRA[n % len(_FINALES_SIN_OBRA)]))
        return planes

    def org(self) -> OrganizacionSimulada:
        return self.aprobadas[int(self.rng.choice(len(self.aprobadas), p=self.pesos_org))]

    def plan_de_obra(self, n: int, inicio_dia: date) -> _Plan:
        inicio = self.momento(inicio_dia)
        aprob_dia = self.dia_entre(inicio_dia - timedelta(days=9), inicio_dia)
        visita_dia = self.dia_entre(aprob_dia - timedelta(days=45), aprob_dia - timedelta(days=5))
        registro_dia = self.dia_entre(visita_dia - timedelta(days=30), visita_dia - timedelta(days=3))
        plan = _Plan(f"obra-{n}", "obra", self.org(), self.momento(registro_dia), inicio=inicio)
        self.hasta_la_aprobacion(plan, visita_dia, aprob_dia)
        if plan.aprobacion >= inicio:          # el mismo día: la aprobación va antes del inicio
            plan.aprobacion = inicio - timedelta(minutes=entero(self.rng, (10, 120)))
        return plan

    def plan_sin_obra(self, n: int, final: str) -> _Plan:
        ref = self.p.fecha_referencia
        registro_dia = self.dia_entre(ref - timedelta(days=330), ref + timedelta(days=30 * self.p.meses_posteriores))
        plan = _Plan(f"sin-obra-{n}", final, self.org(), self.momento(registro_dia))
        if final == "pendiente":
            plan.expediente = self.momento(self.dia_entre(registro_dia + timedelta(days=2), registro_dia + timedelta(days=15)))
            return plan
        visita_dia = self.dia_entre(registro_dia + timedelta(days=3), registro_dia + timedelta(days=30))
        if final == "aprobada_sin_iniciar":
            aprob_dia = self.dia_entre(visita_dia + timedelta(days=5), visita_dia + timedelta(days=45))
            self.hasta_la_aprobacion(plan, visita_dia, aprob_dia)
            return plan
        plan.expediente = self.momento(self.dia_entre(registro_dia + timedelta(days=2), registro_dia + timedelta(days=15)))
        plan.visita = self.momento(visita_dia)
        if final == "semiaprobada":
            plan.semi = self.momento(self.dia_entre(visita_dia + timedelta(days=1), visita_dia + timedelta(days=10)))
        else:
            plan.rechazo = self.momento(self.dia_entre(visita_dia + timedelta(days=5), visita_dia + timedelta(days=45)))
        return plan

    def hasta_la_aprobacion(self, plan: _Plan, visita_dia: date, aprob_dia: date) -> None:
        """Expediente, visita, semiaprobación (30 %) y corrección, y aprobación, en ese orden."""
        registro_dia = plan.registro.date()
        tope_expediente = min(registro_dia + timedelta(days=15), aprob_dia - timedelta(days=1))
        plan.expediente = self.momento(self.dia_entre(registro_dia + timedelta(days=2), tope_expediente))
        plan.visita = self.momento(visita_dia)
        plan.aprobacion = self.momento(aprob_dia)
        if self.rng.random() < self.p.prob_semiaprobada:
            correccion = entero(self.rng, self.p.correccion_solicitud_dias)
            ultimo = aprob_dia - timedelta(days=correccion + 1)
            if ultimo < visita_dia + timedelta(days=1):
                correccion, ultimo = 3, aprob_dia - timedelta(days=4)
            if ultimo >= visita_dia + timedelta(days=1):
                semi_dia = self.dia_entre(visita_dia + timedelta(days=1), ultimo)
                plan.semi = self.momento(semi_dia)
                plan.confirmacion = self.momento(semi_dia + timedelta(days=correccion))

    # --- hechos ---

    def emitir(self, plan: _Plan, num_exp: str) -> None:
        p, clave = self.p, plan.clave
        id_solicitud, id_familia = Ref("solicitudes", clave), Ref("familias", clave)
        integrante = self.elegir(plan.org.usuarios)
        tecnico = self.elegir(self.orgs.tecnicos)
        familiares = entero(self.rng, p.familiares)
        tipos = self.rng.choice(_TIPOS_FAMILIA, size=entero(self.rng, p.documentos_familia), replace=False)
        documentos = [{"id_documento": Ref("documentos", f"{clave}-{t}"), "tipo": str(t),
                       "nombre_original": f"{str(t).lower()}.pdf", "url": f"uploads/familias/{clave}/{str(t).lower()}.pdf"}
                      for t in tipos]
        self.hecho("registrar_solicitud", plan.registro, integrante, id_solicitud=id_solicitud, id_familia=id_familia,
                   cuit_org=plan.org.cuit, cantidad_familiares=familiares,
                   antiguedad_rancho=entero(self.rng, p.antiguedad_rancho), documentos=documentos)
        if plan.expediente:
            self.hecho("asignar_expediente", plan.expediente, self.elegir(self.orgs.operadores), id_solicitud=id_solicitud,
                       num_exp=num_exp)
        if not p.asignar_tecnico:
            return                      # [E19] sin técnico asignado no hay visita ni obra: queda Pendiente
        asignacion = self.asignacion_tecnico(plan)
        if asignacion:
            self.hecho("asignar_tecnico", asignacion, self.orgs.arquitectos[0], id_solicitud=id_solicitud,
                       id_tecnico=tecnico)
        ubicacion = self.ubicacion(plan.org)
        if plan.visita:
            self.visita(plan, id_solicitud, tecnico, familiares, ubicacion)
        self.documentos_a_corregir(plan, id_solicitud, integrante, documentos)
        if plan.rechazo:
            self.hecho("rechazar_solicitud", plan.rechazo, self.elegir(self.orgs.operadores), id_solicitud=id_solicitud,
                       motivo=str(self.elegir(MOTIVOS_RECHAZO)))
        if plan.aprobacion:
            self.aprobar(plan, id_solicitud, tecnico, ubicacion)

    def asignacion_tecnico(self, plan: _Plan) -> datetime | None:
        """[E19] El arquitecto asigna el técnico unos días después del registro y siempre antes de la visita inicial
        (después ya no se puede reasignar). De las solicitudes sin visita, solo algunas ya tienen técnico."""
        p = self.p
        registro = plan.registro.date()
        desde = registro + timedelta(days=p.asignacion_tecnico_dias[0])
        hasta = registro + timedelta(days=p.asignacion_tecnico_dias[1])
        if plan.visita is None:
            if self.rng.random() >= p.prob_tecnico_sin_visita:
                return None
        else:
            hasta = min(hasta, plan.visita.date() - timedelta(days=1))
            if hasta < desde:
                return plan.visita - timedelta(hours=1)
        return self.momento(self.dia_entre(desde, hasta))

    def ubicacion(self, org: OrganizacionSimulada) -> dict:
        if self.rng.random() < self.p.prob_departamento_de_la_organizacion:
            departamento = _POR_NOMBRE[org.departamento]
        else:
            departamento = DEPARTAMENTOS[int(self.rng.choice(len(DEPARTAMENTOS), p=self.pesos_dep))]
        (lat_min, lat_max), (lon_min, lon_max) = LIMITES_PROVINCIA["latitud"], LIMITES_PROVINCIA["longitud"]
        desvio = self.p.desvio_coordenadas
        return {"departamento": departamento.nombre, "localidad": departamento.localidad,
                "latitud": round(float(np.clip(departamento.latitud + self.rng.normal(0, desvio), lat_min, lat_max)), 6),
                "longitud": round(float(np.clip(departamento.longitud + self.rng.normal(0, desvio), lon_min, lon_max)), 6)}

    def visita(self, plan: _Plan, id_solicitud: Ref, tecnico: Ref, familiares: int, ubicacion: dict) -> None:
        p = self.p
        clasificaciones = list(PESOS_CLASIFICACION)
        pesos = np.array(list(PESOS_CLASIFICACION.values()))
        habitantes = max(1, familiares + int(self.rng.integers(-p.habitantes_desvio, p.habitantes_desvio + 1)))
        self.hecho("visita_inicial", plan.visita, tecnico, id_visita=Ref("visitas_iniciales", plan.clave),
                   id_solicitud=id_solicitud,
                   clasificacion=clasificaciones[int(self.rng.choice(len(clasificaciones), p=pesos / pesos.sum()))],
                   observaciones=str(self.elegir(OBSERVACIONES_VISITA)), habitantes=habitantes,
                   prioridad_social=bool(self.rng.random() < p.prob_prioridad_social),
                   fotos=[f"uploads/visitas/{plan.clave}/foto_{n + 1}.jpg" for n in range(entero(self.rng, p.fotos_visita))],
                   **ubicacion)

    def documentos_a_corregir(self, plan: _Plan, id_solicitud: Ref, integrante: Ref, documentos: list[dict]) -> None:
        """[E14]: cada documento se marca con probabilidad 0,20 en la revisión del operador y se reemplaza 2 a 10 días
        después, antes de la confirmación de la corrección y de la aprobación (o del rechazo)."""
        marcados = [d for d in documentos if self.rng.random() < self.p.prob_documento_a_corregir]
        operador = self.elegir(self.orgs.operadores)
        if plan.semi:
            marcados = marcados or [self.elegir(documentos)]
            self.hecho("semiaprobar_solicitud", plan.semi, operador, id_solicitud=id_solicitud,
                       motivo=str(self.elegir(MOTIVOS_SEMIAPROBACION)),
                       campos_observados=[str(c) for c in self.rng.choice(CAMPOS_OBSERVABLES, size=entero(self.rng, (1, 2)),
                                                                          replace=False)])
            marcas = [plan.semi + timedelta(minutes=n + 1) for n in range(len(marcados))]
            limite = plan.confirmacion          # None si la solicitud quedó semiaprobada sin corregir
        else:
            fin = plan.aprobacion or plan.rechazo
            if fin is None:
                return
            desde, hasta = plan.registro.date() + timedelta(days=1), fin.date() - timedelta(days=3)
            if hasta < desde:
                return
            marcas = [self.momento(self.dia_entre(desde, hasta)) for _ in marcados]
            limite = fin
        for doc, marca in zip(marcados, marcas):
            self.hecho("marcar_documento", marca, operador, id_documento=doc["id_documento"],
                       motivo=str(self.elegir(MOTIVOS_DOCUMENTO)))
            if limite is None:
                continue
            dia = self.dia_entre(marca.date() + timedelta(days=2), min(marca.date() + timedelta(days=10), limite.date()))
            reemplazo = self.momento(dia)
            if reemplazo >= limite:
                reemplazo = limite - timedelta(minutes=entero(self.rng, (5, 60)))
            nombre = f"{doc['tipo'].lower()}_2.pdf"
            self.hecho("reemplazar_documento", reemplazo, integrante, id_documento=doc["id_documento"],
                       nombre_original=nombre, url=f"uploads/familias/{plan.clave}/{nombre}")
        if plan.confirmacion:
            self.hecho("confirmar_correccion", plan.confirmacion, integrante, id_solicitud=id_solicitud)

    def aprobar(self, plan: _Plan, id_solicitud: Ref, tecnico: Ref, ubicacion: dict) -> None:
        p = self.p
        id_vivienda = Ref("viviendas", plan.clave)
        self.hecho("aprobar_solicitud", plan.aprobacion, self.elegir(self.orgs.operadores), id_solicitud=id_solicitud,
                   id_vivienda=id_vivienda)
        if self.rng.random() < p.prob_vivienda_completada:
            dia = plan.aprobacion.date()
            completada = self.momento(self.dia_entre(dia + timedelta(days=p.completar_vivienda_dias[0]),
                                                     dia + timedelta(days=p.completar_vivienda_dias[1])))
            tipos = [t for t, _ in p.pesos_tipo_vivienda]
            pesos = np.array([w for _, w in p.pesos_tipo_vivienda])
            self.hecho("completar_vivienda", completada, self.orgs.arquitectos[0], id_vivienda=id_vivienda,
                       direccion=self.fake.street_address(), barrio=f"Barrio {self.fake.last_name()}",
                       superficie=round(float(self.rng.uniform(*p.superficie_m2)), 2),
                       tipo_vivienda=tipos[int(self.rng.choice(len(tipos), p=pesos / pesos.sum()))],
                       cant_dormitorios=int(self.rng.choice(p.dormitorios)), **ubicacion)
        if plan.final == "obra":
            self.mundo.obras.append(ObraPorIniciar(id_solicitud, id_vivienda, plan.inicio, ubicacion["departamento"],
                                                   tecnico, plan.org.usuarios))


def generar_solicitudes(rng: np.random.Generator, fake: Faker, p: ParametrosSimulacion,
                        orgs: MundoOrganizaciones) -> MundoSolicitudes:
    generador = _Generador(rng, fake, p, orgs)
    planes = sorted(generador.planes(), key=lambda plan: plan.registro)
    por_anio: dict[int, int] = {}
    for plan in planes:
        anio = plan.registro.year
        por_anio[anio] = por_anio.get(anio, 0) + 1
        generador.emitir(plan, f"EXP-{anio}-{por_anio[anio]:04d}")
    return generador.mundo
