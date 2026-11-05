"""La verdad del simulador, primera parte: el personal (técnicos, operadores, arquitecto y administrador) y las altas de
organizaciones con sus integrantes ([E2], [E3], [E22]). Todo pasa en la web, con conexión: momento real = registrado.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np
from faker import Faker

from analitica.catalogo import TIPOS_DOCUMENTO
from analitica.origenes.simulado_comun import dia_habil, entero, mes, momento_habil, persona, username_java
from analitica.origenes.simulado_proyeccion import Hecho, Ref
from analitica.parametros_simulacion import DEPARTAMENTOS, MOTIVOS_OBSERVACION_ALTA, ParametrosSimulacion

_TIPOS_DOCUMENTO_ALTA = [t.codigo for t in TIPOS_DOCUMENTO.values() if t.ambito == "organizacion"]
_CAMPOS_ALTA = ("fechaVencimientoVigencia", "fechaUltimaAsamblea", "domLegal", "dniPresidente", "telefonoTesorero")
_CARGOS_EXTRA = ("VICEPRESIDENTE", "SECRETARIO", "VOCAL", "INTEGRANTE")


@dataclass(frozen=True)
class OrganizacionSimulada:
    cuit: str
    grupo: str                       # "OG" u "ONG", el que se buscó al inventarla
    departamento: str
    aprobada_en: datetime | None     # None si el alta quedó pendiente o se rechazó
    usuarios: tuple[Ref, ...]        # presidente y tesorero


@dataclass
class MundoOrganizaciones:
    hechos: list[Hecho] = field(default_factory=list)
    organizaciones: list[OrganizacionSimulada] = field(default_factory=list)
    tecnicos: list[Ref] = field(default_factory=list)
    operadores: list[Ref] = field(default_factory=list)
    arquitectos: list[Ref] = field(default_factory=list)
    administradores: list[Ref] = field(default_factory=list)


class _Generador:
    def __init__(self, rng: np.random.Generator, fake: Faker, p: ParametrosSimulacion):
        self.rng, self.fake, self.p = rng, fake, p
        self.mundo = MundoOrganizaciones()
        self.usernames: set[str] = set()
        self.cuits: set[str] = set()

    def hecho(self, accion: str, momento: datetime, autor, **datos) -> None:
        self.mundo.hechos.append(Hecho(accion, momento, momento, autor, datos))

    def dia(self, base: date, rango: tuple[int, int]) -> datetime:
        return momento_habil(dia_habil(base + timedelta(days=entero(self.rng, rango))), self.rng)

    def operador(self) -> Ref:
        return self.mundo.operadores[int(self.rng.integers(len(self.mundo.operadores)))]

    # --- personal ---

    def personal(self) -> None:
        inicio = datetime.combine(self.p.fecha_referencia - mes(18), time(8))
        roles = (("TECNICO", self.p.tecnicos, self.mundo.tecnicos), ("OPERADOR", self.p.operadores, self.mundo.operadores),
                 ("ARQUITECTO", self.p.arquitectos, self.mundo.arquitectos),
                 ("ADMIN", self.p.administradores, self.mundo.administradores))
        minuto = 0
        for rol, cantidad, lista in roles:
            for n in range(cantidad):
                datos = persona(self.fake, self.rng)
                username = username_java(datos["nombre"], datos["apellido"], self.usernames)
                self.usernames.add(username)
                ref = Ref("usuarios", f"{rol.lower()}-{n}")
                lista.append(ref)
                self.hecho("crear_usuario", inicio + timedelta(minutes=minuto), None, id_usuario=ref, username=username,
                           rol=rol, email=datos["correo"], nombre=datos["nombre"], apellido=datos["apellido"])
                minuto += 1

    # --- altas ---

    def cuit(self) -> str:
        while True:
            cuit = f"30-{int(self.rng.integers(10_000_000, 100_000_000))}-{int(self.rng.integers(10))}"
            if cuit not in self.cuits:
                self.cuits.add(cuit)
                return cuit

    def altas(self) -> None:
        p = self.p
        finales = ["aprobada"] * p.altas_aprobadas + ["pendiente"] * p.altas_pendientes + ["rechazada"] * p.altas_rechazadas
        cantidad_og = round(p.prob_og * len(finales))
        es_og = self.rng.permutation([True] * cantidad_og + [False] * (len(finales) - cantidad_og))
        pesos = np.array([d.peso for d in DEPARTAMENTOS])
        # Las OG son municipios y comisiones municipales: no se repite departamento entre ellas.
        departamentos_og = iter(self.rng.choice(len(DEPARTAMENTOS), size=cantidad_og, replace=False, p=pesos / pesos.sum()))
        for numero, (final, og) in enumerate(zip(finales, es_og)):
            if og:
                # TipoOrganizacion.java no tiene un tipo para las OG: eligen «Otra» y el grupo sale del nombre.
                departamento = DEPARTAMENTOS[int(next(departamentos_og))]
                tipo = "Otra"
                nombre = (f"Municipalidad de {departamento.localidad}" if numero % 2 == 0
                          else f"Comisión Municipal de {departamento.localidad}")
            else:
                departamento = DEPARTAMENTOS[int(self.rng.choice(len(DEPARTAMENTOS), p=pesos / pesos.sum()))]
                tipo = str(self.rng.choice(["Asociación Civil", "Cooperativa"]))
                nombre = (f"Asociación Civil {self.fake.last_name()}" if tipo == "Asociación Civil"
                          else f"Cooperativa de Trabajo {self.fake.last_name()} Ltda.")
            self.alta(numero, final, "OG" if og else "ONG", departamento.nombre, tipo, nombre)

    def alta(self, numero: int, final: str, grupo: str, departamento: str, tipo: str, nombre: str) -> None:
        p, p_ref = self.p, self.p.fecha_referencia
        if final == "aprobada":
            # Así quedan aprobadas antes de la primera solicitud (ver docs/simulacion.md).
            registro = self.dia(p_ref - timedelta(days=510), (0, 20))
        elif final == "rechazada":
            registro = self.dia(p_ref - timedelta(days=60), (0, 35))
        else:
            registro = self.dia(p_ref - timedelta(days=60), (0, 55))
        cuit = self.cuit()
        id_alta = Ref("solicitudes_organizacion", cuit)
        presidente, tesorero = persona(self.fake, self.rng), persona(self.fake, self.rng)
        for cargo in (presidente, tesorero):
            cargo["fecha_alta_cargo"] = registro.date() - timedelta(days=entero(self.rng, (30, 1000)))
        documentos = [{"id_documento": Ref("documentos", f"{cuit}-{t}"), "tipo": t,
                       "nombre_original": f"{t.lower()}.pdf", "url": f"uploads/organizaciones/{cuit}/{t.lower()}.pdf"}
                      for t in _TIPOS_DOCUMENTO_ALTA]
        self.hecho("registrar_alta", registro, None, id_solicitud_org=id_alta, cuit=cuit, nombre=nombre, tipo=tipo,
                   dom_legal=self.fake.street_address(), cpe=str(int(self.rng.integers(1000, 10000))),
                   fecha_vencimiento_vigencia=registro.date() + timedelta(days=entero(self.rng, (365, 1095))),
                   fecha_ultima_asamblea=registro.date() - timedelta(days=entero(self.rng, (30, 700))),
                   presidente=presidente, tesorero=tesorero, documentos=documentos)
        if final == "pendiente":
            self.mundo.organizaciones.append(OrganizacionSimulada(cuit, grupo, departamento, None, ()))
            return
        momento = registro
        if final == "aprobada" and self.rng.random() < p.prob_alta_observada:
            observados = [documentos[int(i)] for i in self.rng.choice(len(documentos), size=entero(self.rng, (1, 2)),
                                                                       replace=False)]
            motivo = str(self.rng.choice(MOTIVOS_OBSERVACION_ALTA))
            momento = self.dia(momento.date(), p.revision_alta_dias)
            self.hecho("observar_alta", momento, self.operador(), id_solicitud_org=id_alta, motivo=motivo,
                       campos_observados=[str(c) for c in self.rng.choice(_CAMPOS_ALTA, size=2, replace=False)],
                       documentos=[d["id_documento"] for d in observados])
            momento = self.dia(momento.date(), p.revision_alta_dias)
            self.hecho("corregir_alta", momento, None, id_solicitud_org=id_alta,
                       reemplazos=[{"id_documento": d["id_documento"], "nombre_original": f"{d['tipo'].lower()}_corregido.pdf",
                                    "url": f"{d['url'][:-4]}_corregido.pdf"} for d in observados])
        momento = self.dia(momento.date(), p.revision_alta_dias)
        if final == "rechazada":
            self.hecho("rechazar_alta", momento, self.operador(), id_solicitud_org=id_alta,
                       motivo=str(self.rng.choice(MOTIVOS_OBSERVACION_ALTA)))
            self.mundo.organizaciones.append(OrganizacionSimulada(cuit, grupo, departamento, None, ()))
            return
        usuarios = []
        cargos = {}
        for cargo, datos in (("presidente", presidente), ("tesorero", tesorero)):
            username = username_java(datos["nombre"], datos["apellido"], self.usernames)
            self.usernames.add(username)
            usuario = Ref("usuarios", f"{cuit}-{cargo}")
            usuarios.append(usuario)
            cargos[cargo] = {"id_integrante": Ref("integrantes", f"{cuit}-{cargo}"), "id_usuario": usuario,
                             "username": username}
        self.hecho("aprobar_alta", momento, self.operador(), id_solicitud_org=id_alta, **cargos)
        self.mundo.organizaciones.append(OrganizacionSimulada(cuit, grupo, departamento, momento, tuple(usuarios)))
        for n in range(entero(self.rng, p.integrantes_extra)):
            alta_cargo = self.dia(momento.date(), (1, 60))
            self.hecho("agregar_integrante", alta_cargo, usuarios[0], id_integrante=Ref("integrantes", f"{cuit}-extra-{n}"),
                       cuit_org=cuit, cargo=str(self.rng.choice(_CARGOS_EXTRA)), fecha_alta_cargo=alta_cargo.date(),
                       **persona(self.fake, self.rng))


def generar_organizaciones(rng: np.random.Generator, fake: Faker, p: ParametrosSimulacion) -> MundoOrganizaciones:
    generador = _Generador(rng, fake, p)
    generador.personal()
    generador.altas()
    return generador.mundo
