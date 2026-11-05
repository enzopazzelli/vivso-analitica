"""La proyección del origen simulado: aplica los hechos de la verdad sobre las 13 tablas con las reglas de Java.

Cada acción replica un método de los servicios de Desarrollo (`SolicitudService`, `EtapaObraService`, etc.): las mismas
precondiciones (si no se cumplen, `ReglaDeJava`), los mismos campos que se pisan y la hora del servidor, que es el
momento en que el hecho llegó (`momento_registrado`). Como en Java, no queda historia: cada acción sobrescribe.
"""
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from analitica.calendario import CALENDARIO_JAVA
from analitica.catalogo import CLASIFICACIONES, ETAPAS, ROLES, TIPOS_VIVIENDA, etapa, siguiente
from analitica.esquema import TABLAS, nombres


@dataclass(frozen=True)
class Ref:
    """Una fila de la verdad antes de tener id: `asignar_ids` la cambia por el id que le daría MySQL."""
    tabla: str
    clave: str


@dataclass(frozen=True)
class Hecho:
    accion: str
    momento_real: datetime          # cuándo pasó
    momento_registrado: datetime    # cuándo llegó al servidor (la hora que guarda Java)
    autor: Ref | int | None         # el usuario que lo hizo
    datos: dict


class ReglaDeJava(Exception):
    """Un hecho que el sistema de Desarrollo no aceptaría (la verdad simulada tiene un error)."""


def asignar_ids(hechos: Sequence[Hecho]) -> tuple[list[Hecho], dict[Ref, int]]:
    """Cambia cada `Ref` por un id, como el autoincremental de MySQL: en el orden en que llegan al servidor, la
    primera vez que aparece un `Ref` (su creación) toma el próximo id de su tabla."""
    mapa: dict[Ref, int] = {}
    contadores: dict[str, int] = defaultdict(int)

    def convertir(valor):
        if isinstance(valor, Ref):
            if valor not in mapa:
                contadores[valor.tabla] += 1
                mapa[valor] = contadores[valor.tabla]
            return mapa[valor]
        if isinstance(valor, dict):
            return {clave: convertir(v) for clave, v in valor.items()}
        if isinstance(valor, list):
            return [convertir(v) for v in valor]
        if isinstance(valor, tuple):
            return tuple(convertir(v) for v in valor)
        return valor

    ordenados = [h for _, h in sorted(enumerate(hechos), key=lambda par: (par[1].momento_registrado, par[0]))]
    con_ids = [replace(h, autor=convertir(h.autor), datos=convertir(h.datos)) for h in ordenados]
    return con_ids, mapa


def _al_minuto(momento: datetime) -> datetime:
    """Java trunca `fecha_envio` y `fecha_revision` al minuto."""
    return momento.replace(second=0, microsecond=0)


_ESTADOS_CON_FOTOS = ("EN_CURSO", "OBSERVADA")
_PERSONA = ("dni", "nombre", "apellido", "correo", "telefono", "fecha_alta_cargo", "domicilio")


class _Proyeccion:
    def __init__(self, error_prorroga_java: bool):
        self.error_prorroga_java = error_prorroga_java
        self.tablas: dict[str, dict] = {t: {} for t in TABLAS}
        self.etapas_de: dict[int, list[int]] = {}               # id_solicitud → ids de sus 6 etapas, en orden
        self.documentos_de_familia: dict[int, list[int]] = defaultdict(list)
        self.documentos_de_alta: dict[int, list[int]] = defaultdict(list)

    # --- ayudas ---

    def _nueva(self, tabla: str, clave, **valores) -> dict:
        desconocidas = set(valores) - set(nombres(tabla))
        if desconocidas:
            raise ValueError(f"{tabla}: columnas desconocidas {sorted(desconocidas)}")
        fila = {columna: valores.get(columna) for columna in nombres(tabla)}
        self.tablas[tabla][clave] = fila
        return fila

    def _fila(self, accion: str, tabla: str, clave) -> dict:
        try:
            return self.tablas[tabla][clave]
        except KeyError:
            raise ReglaDeJava(f"{accion}: no existe {tabla} {clave}") from None

    @staticmethod
    def _exigir(condicion: bool, mensaje: str) -> None:
        if not condicion:
            raise ReglaDeJava(mensaje)

    def _documentos(self, ids, accion: str) -> list[dict]:
        return [self._fila(accion, "documentos", i) for i in ids]

    # --- usuarios y organizaciones ---

    def crear_usuario(self, h: Hecho) -> None:
        d = h.datos
        self._exigir(d["rol"] in ROLES, f"crear_usuario: rol desconocido {d['rol']}")
        self._usuario_nuevo("crear_usuario", d["id_usuario"], d["username"], d["rol"], d["email"])

    def _usuario_nuevo(self, accion: str, id_usuario: int, username: str, rol: str, email: str) -> None:
        usuarios = self.tablas["usuarios"].values()
        self._exigir(all(u["username"] != username for u in usuarios), f"{accion}: el username {username} ya existe")
        self._exigir(all(u["email"] != email for u in usuarios), f"{accion}: el correo {email} ya está en uso")
        self._nueva("usuarios", id_usuario, id_usuario=id_usuario, username=username, rol=rol, email=email, activo=True)

    def registrar_alta(self, h: Hecho) -> None:
        d = h.datos
        cuit = d["cuit"]
        self._exigir(all(a["cuit"] != cuit for a in self.tablas["solicitudes_organizacion"].values()),
                     f"registrar_alta: ya hay un alta con el cuit {cuit} (la columna es única)")
        self._exigir(cuit not in self.tablas["organizaciones"], f"registrar_alta: el cuit {cuit} ya es una organización")
        personas = {f"{campo}_{cargo}": d[cargo][campo] for cargo in ("presidente", "tesorero") for campo in _PERSONA}
        self._nueva("solicitudes_organizacion", d["id_solicitud_org"], id_solicitud_org=d["id_solicitud_org"], cuit=cuit,
                    nombre=d["nombre"], tipo=d["tipo"], dom_legal=d["dom_legal"], cpe=d["cpe"],
                    fecha_vencimiento_vigencia=d["fecha_vencimiento_vigencia"],
                    fecha_ultima_asamblea=d["fecha_ultima_asamblea"], estado="Pendiente",
                    fecha_solicitud=h.momento_registrado.date(), **personas)
        for doc in d["documentos"]:
            self._documento_nuevo(h, doc, id_solicitud_org=d["id_solicitud_org"])
            self.documentos_de_alta[d["id_solicitud_org"]].append(doc["id_documento"])

    def _documento_nuevo(self, h: Hecho, doc: dict, **duenio) -> None:
        self._nueva("documentos", doc["id_documento"], id_documento=doc["id_documento"],
                    nombre_original=doc["nombre_original"], url=doc["url"], tipo=doc["tipo"], estado="PENDIENTE",
                    fecha_subida=h.momento_registrado, **duenio)

    def observar_alta(self, h: Hecho) -> None:
        d = h.datos
        alta = self._fila("observar_alta", "solicitudes_organizacion", d["id_solicitud_org"])
        self._exigir(alta["estado"] == "Pendiente", f"observar_alta: el alta {d['id_solicitud_org']} está {alta['estado']}")
        documentos = self._documentos(d["documentos"], "observar_alta")
        for doc in documentos:
            self._exigir(doc["estado"] == "PENDIENTE" and doc["id_solicitud_org"] == d["id_solicitud_org"],
                         f"observar_alta: el documento {doc['id_documento']} no es un documento PENDIENTE de esta alta")
        alta.update(estado="SemiAprobada", motivo=d["motivo"], campos_observados=",".join(d["campos_observados"]),
                    id_revisor=h.autor)
        for doc in documentos:
            doc.update(estado="A_CORREGIR", motivo_observacion=d["motivo"], fecha_revision=h.momento_registrado,
                       id_revisor=h.autor)

    def corregir_alta(self, h: Hecho) -> None:
        d = h.datos
        alta = self._fila("corregir_alta", "solicitudes_organizacion", d["id_solicitud_org"])
        self._exigir(alta["estado"] == "SemiAprobada",
                     f"corregir_alta: el alta {d['id_solicitud_org']} está {alta['estado']}, no en observaciones")
        for reemplazo in d["reemplazos"]:
            self._reemplazar("corregir_alta", reemplazo)
        pendientes = [i for i in self.documentos_de_alta[d["id_solicitud_org"]]
                      if self.tablas["documentos"][i]["estado"] == "A_CORREGIR"]
        self._exigir(not pendientes, f"corregir_alta: quedan documentos A_CORREGIR {pendientes}")
        alta.update(estado="Pendiente", motivo=None, campos_observados=None)

    def _reemplazar(self, accion: str, reemplazo: dict) -> None:
        doc = self._fila(accion, "documentos", reemplazo["id_documento"])
        self._exigir(doc["estado"] == "A_CORREGIR",
                     f"{accion}: el documento {reemplazo['id_documento']} está {doc['estado']}; solo se reemplaza A_CORREGIR")
        doc.update(estado="PENDIENTE", nombre_original=reemplazo["nombre_original"], url=reemplazo["url"],
                   motivo_observacion=None, id_revisor=None)

    def aprobar_alta(self, h: Hecho) -> None:
        d = h.datos
        alta = self._fila("aprobar_alta", "solicitudes_organizacion", d["id_solicitud_org"])
        cuit = alta["cuit"]
        self._exigir(alta["estado"] != "Aprobada", f"aprobar_alta: el alta {d['id_solicitud_org']} ya está aprobada")
        self._exigir(cuit not in self.tablas["organizaciones"], f"aprobar_alta: ya existe una organización con el cuit {cuit}")
        self._exigir(alta["fecha_vencimiento_vigencia"] is not None,
                     f"aprobar_alta: el alta {d['id_solicitud_org']} no tiene fecha de vencimiento de la vigencia")
        alta.update(estado="Aprobada", fecha_aprobacion=h.momento_registrado.date(), id_revisor=h.autor)
        self._nueva("organizaciones", cuit, cuit=cuit, nombre=alta["nombre"], tipo=alta["tipo"],
                    dom_legal=alta["dom_legal"], cpe=alta["cpe"],
                    fecha_vencimiento_vigencia=alta["fecha_vencimiento_vigencia"],
                    fecha_ultima_asamblea=alta["fecha_ultima_asamblea"])
        for cargo in ("presidente", "tesorero"):
            ids = d[cargo]
            persona = {campo: alta[f"{campo}_{cargo}"] for campo in _PERSONA}
            self._usuario_nuevo("aprobar_alta", ids["id_usuario"], ids["username"], "INTEGRANTE", persona["correo"])
            self._nueva("integrantes", ids["id_integrante"], id_integrante=ids["id_integrante"], cuit_org=cuit,
                        cargo=cargo.upper(), activo=True, id_usuario=ids["id_usuario"], **persona)
        for doc in self._documentos(self.documentos_de_alta[d["id_solicitud_org"]], "aprobar_alta"):
            doc.update(estado="APROBADO", cuit_org=cuit, id_revisor=h.autor)

    def rechazar_alta(self, h: Hecho) -> None:
        d = h.datos
        alta = self._fila("rechazar_alta", "solicitudes_organizacion", d["id_solicitud_org"])
        self._exigir(alta["estado"] != "Aprobada", f"rechazar_alta: el alta {d['id_solicitud_org']} ya está aprobada")
        alta.update(estado="Rechazada", motivo=d["motivo"], fecha_rechazo=h.momento_registrado.date(), id_revisor=h.autor)
        for doc in self._documentos(self.documentos_de_alta[d["id_solicitud_org"]], "rechazar_alta"):
            doc.update(estado="RECHAZADO", id_revisor=h.autor)       # se borra el archivo, la fila queda

    def agregar_integrante(self, h: Hecho) -> None:
        d = h.datos
        self._fila("agregar_integrante", "organizaciones", d["cuit_org"])
        self._nueva("integrantes", d["id_integrante"], activo=True, id_usuario=None,
                    **{c: d[c] for c in ("id_integrante", "cuit_org", "cargo", "dni", "nombre", "apellido", "correo",
                                         "telefono", "fecha_alta_cargo", "domicilio")})

    # --- solicitudes, documentos, viviendas y visitas ---

    def registrar_solicitud(self, h: Hecho) -> None:
        d = h.datos
        self._fila("registrar_solicitud", "organizaciones", d["cuit_org"])
        self._exigir(d["cantidad_familiares"] >= 1, "registrar_solicitud: la familia no tiene familiares")
        self._exigir(d["antiguedad_rancho"] >= 5, "registrar_solicitud: la base exige 5 años o más de antigüedad del rancho")
        self._nueva("familias", d["id_familia"], id_familia=d["id_familia"], cantidad_familiares=d["cantidad_familiares"],
                    antiguedad_rancho=d["antiguedad_rancho"])
        self._nueva("solicitudes", d["id_solicitud"], id_solicitud=d["id_solicitud"], estado="Pendiente",
                    fecha_solicitud=h.momento_registrado.date(), cuit_org=d["cuit_org"], id_familia=d["id_familia"])
        for doc in d["documentos"]:
            self._documento_nuevo(h, doc, id_familia=d["id_familia"])
            self.documentos_de_familia[d["id_familia"]].append(doc["id_documento"])

    def asignar_expediente(self, h: Hecho) -> None:
        self._fila("asignar_expediente", "solicitudes", h.datos["id_solicitud"])["num_exp"] = h.datos["num_exp"]

    def marcar_documento(self, h: Hecho) -> None:
        doc = self._fila("marcar_documento", "documentos", h.datos["id_documento"])
        self._exigir(doc["estado"] == "PENDIENTE",
                     f"marcar_documento: el documento {h.datos['id_documento']} está {doc['estado']}; solo se revisan PENDIENTE")
        doc.update(estado="A_CORREGIR", motivo_observacion=h.datos["motivo"], fecha_revision=h.momento_registrado,
                   id_revisor=h.autor)

    def reemplazar_documento(self, h: Hecho) -> None:
        self._reemplazar("reemplazar_documento", h.datos)

    def semiaprobar_solicitud(self, h: Hecho) -> None:
        d = h.datos
        sol = self._fila("semiaprobar_solicitud", "solicitudes", d["id_solicitud"])
        self._exigir(sol["estado"] not in ("Aprobada", "Rechazada"),
                     f"semiaprobar_solicitud: la solicitud {d['id_solicitud']} está {sol['estado']}")
        sol.update(estado="SemiAprobada", observacion=d["motivo"], campos_observados=",".join(d["campos_observados"]),
                   id_revisor=h.autor)

    def confirmar_correccion(self, h: Hecho) -> None:
        d = h.datos
        sol = self._fila("confirmar_correccion", "solicitudes", d["id_solicitud"])
        self._exigir(sol["estado"] == "SemiAprobada",
                     f"confirmar_correccion: la solicitud {d['id_solicitud']} está {sol['estado']}, no en observaciones")
        pendientes = [i for i in self.documentos_de_familia[sol["id_familia"]]
                      if self.tablas["documentos"][i]["estado"] == "A_CORREGIR"]
        self._exigir(not pendientes, f"confirmar_correccion: quedan documentos A_CORREGIR de la familia {sol['id_familia']}")
        sol.update(estado="Pendiente", observacion=None, campos_observados=None)

    def aprobar_solicitud(self, h: Hecho) -> None:
        d = h.datos
        sol = self._fila("aprobar_solicitud", "solicitudes", d["id_solicitud"])
        self._exigir(sol["estado"] != "Aprobada", f"aprobar_solicitud: la solicitud {d['id_solicitud']} ya está aprobada")
        self._exigir(bool(sol["num_exp"]), f"aprobar_solicitud: la solicitud {d['id_solicitud']} no tiene número de expediente")
        sol.update(estado="Aprobada", fecha_activacion=h.momento_registrado.date(), id_revisor=h.autor,
                   id_tecnico_asignado=d.get("id_tecnico_asignado"))
        # La vivienda nace vacía: solo la familia y la solicitud (SolicitudService.aprobarSolicitudVivienda).
        self._nueva("viviendas", d["id_vivienda"], id_vivienda=d["id_vivienda"], id_solicitud=d["id_solicitud"],
                    id_familia=sol["id_familia"])

    def rechazar_solicitud(self, h: Hecho) -> None:
        d = h.datos
        sol = self._fila("rechazar_solicitud", "solicitudes", d["id_solicitud"])
        self._exigir(sol["estado"] != "Aprobada", f"rechazar_solicitud: la solicitud {d['id_solicitud']} ya está aprobada")
        sol.update(estado="Rechazada", observacion=d["motivo"], id_revisor=h.autor)

    def completar_vivienda(self, h: Hecho) -> None:
        d = dict(h.datos)
        vivienda = self._fila("completar_vivienda", "viviendas", d.pop("id_vivienda"))
        self._exigir(d["tipo_vivienda"] in TIPOS_VIVIENDA, f"completar_vivienda: tipo desconocido {d['tipo_vivienda']}")
        vivienda.update(d)

    def visita_inicial(self, h: Hecho) -> None:
        d = dict(h.datos)
        self._fila("visita_inicial", "solicitudes", d["id_solicitud"])
        self._exigir(d["clasificacion"] in CLASIFICACIONES, f"visita_inicial: clasificación desconocida {d['clasificacion']}")
        fotos = d.pop("fotos")
        # La única fecha que viene del celular.
        self._nueva("visitas_iniciales", d["id_visita"], fecha_visita=h.momento_real, id_tecnico=h.autor, **d)
        for n, url in enumerate(fotos):
            self._nueva("fotos_visita", (d["id_visita"], n), id_visita=d["id_visita"], url_foto=url)

    # --- etapas y fotos ---

    def _activar(self, fila: dict, h: Hecho) -> None:
        hoy = h.momento_registrado.date()
        limite = CALENDARIO_JAVA.sumar_habiles(hoy, etapa(fila["etapa"]).dias_estimados)
        fila.update(estado="EN_CURSO", fecha_inicio=hoy, fecha_limite=limite, fecha_limite_original=limite)

    def _tecnico_asignado(self, accion: str, id_solicitud: int, autor) -> None:
        """EtapaObraService.validarTecnicoAsignado: solo el técnico asignado a la solicitud inicia la obra y aprueba,
        observa o prorroga sus etapas (sin excepción para ADMIN). Sin técnico asignado, nadie puede."""
        asignado = self.tablas["solicitudes"][id_solicitud]["id_tecnico_asignado"]
        self._exigir(asignado is not None and asignado == autor,
                     f"{accion}: solo el técnico asignado a la solicitud {id_solicitud} puede hacerlo "
                     f"(asignado: {asignado}, autor: {autor})")

    def _etapa(self, accion: str, id_etapa: int, permitidos: tuple[str, ...], para: str) -> dict:
        fila = self._fila(accion, "etapas", id_etapa)
        self._exigir(fila["estado"] in permitidos,
                     f"{accion}: la etapa {id_etapa} está {fila['estado']}; Java solo {para} {' u '.join(permitidos)}")
        return fila

    def iniciar_obra(self, h: Hecho) -> None:
        d = h.datos
        sol = self._fila("iniciar_obra", "solicitudes", d["id_solicitud"])
        self._exigir(sol["estado"] == "Aprobada",
                     f"iniciar_obra: la solicitud {d['id_solicitud']} está {sol['estado']}; Java exige que esté Aprobada")
        self._tecnico_asignado("iniciar_obra", d["id_solicitud"], h.autor)
        self._exigir(d["id_solicitud"] not in self.etapas_de, f"iniciar_obra: la solicitud {d['id_solicitud']} ya tiene etapas")
        self._exigir(len(d["etapas"]) == len(ETAPAS), "iniciar_obra: hacen falta 6 ids de etapa")
        self.etapas_de[d["id_solicitud"]] = list(d["etapas"])
        filas = [self._nueva("etapas", id_etapa, id_etapa_obra=id_etapa, id_solicitud=d["id_solicitud"], etapa=e.codigo,
                             numero=e.numero, estado="PENDIENTE")
                 for id_etapa, e in zip(d["etapas"], ETAPAS)]
        self._activar(filas[0], h)

    def subir_foto(self, h: Hecho) -> None:
        d = h.datos
        self._etapa("subir_foto", d["id_etapa_obra"], _ESTADOS_CON_FOTOS, "acepta fotos")
        self._nueva("fotos_etapa", d["id_foto"], id_foto=d["id_foto"], id_etapa_obra=d["id_etapa_obra"],
                    nombre_archivo=d["nombre_archivo"], ruta_archivo=d["ruta_archivo"],
                    fecha_subida=h.momento_registrado, id_usuario_subida=h.autor)

    def borrar_foto(self, h: Hecho) -> None:
        foto = self._fila("borrar_foto", "fotos_etapa", h.datos["id_foto"])
        self._etapa("borrar_foto", foto["id_etapa_obra"], _ESTADOS_CON_FOTOS, "deja borrar fotos")
        del self.tablas["fotos_etapa"][h.datos["id_foto"]]     # el borrado no deja rastro

    def enviar_etapa(self, h: Hecho) -> None:
        d = h.datos
        permitidos = ("EN_CURSO", "OBSERVADA") if self.error_prorroga_java else ("EN_CURSO", "OBSERVADA", "PRORROGADA")
        fila = self._etapa("enviar_etapa", d["id_etapa_obra"], permitidos, "envía")
        fila.update(estado="EN_REVISION", fecha_envio=_al_minuto(h.momento_registrado),
                    observacion_organizacion=d.get("observacion_organizacion"), id_usuario_envio=h.autor)

    def aprobar_etapa(self, h: Hecho) -> None:
        fila = self._etapa("aprobar_etapa", h.datos["id_etapa_obra"], ("EN_REVISION",), "aprueba")
        self._tecnico_asignado("aprobar_etapa", fila["id_solicitud"], h.autor)
        fila.update(estado="APROBADA", fecha_revision=_al_minuto(h.momento_registrado), id_revisor=h.autor)
        proxima = siguiente(fila["etapa"])
        if proxima:
            id_proxima = self.etapas_de[fila["id_solicitud"]][proxima.numero - 1]
            self._activar(self.tablas["etapas"][id_proxima], h)

    def observar_etapa(self, h: Hecho) -> None:
        fila = self._etapa("observar_etapa", h.datos["id_etapa_obra"], ("EN_REVISION",), "observa")
        self._tecnico_asignado("observar_etapa", fila["id_solicitud"], h.autor)
        fila.update(estado="OBSERVADA", observacion_tecnico=h.datos["observacion_tecnico"],
                    fecha_revision=_al_minuto(h.momento_registrado), id_revisor=h.autor)

    def prorrogar_etapa(self, h: Hecho) -> None:
        d = h.datos
        fila = self._etapa("prorrogar_etapa", d["id_etapa_obra"], ("EN_CURSO", "OBSERVADA", "PRORROGADA"), "prorroga")
        self._tecnico_asignado("prorrogar_etapa", fila["id_solicitud"], h.autor)
        nueva = d["fecha_limite"]
        self._exigir(nueva > fila["fecha_limite"],
                     f"prorrogar_etapa: la fecha nueva {nueva} tiene que ser posterior al límite vigente {fila['fecha_limite']}")
        self._exigir(CALENDARIO_JAVA.es_habil(nueva), f"prorrogar_etapa: la fecha nueva {nueva} no es día hábil")
        fila.update(estado="PRORROGADA", fecha_limite=nueva, motivo_prorroga=d["motivo"])

    def visita_obra(self, h: Hecho) -> None:
        d = h.datos
        self._fila("visita_obra", "viviendas", d["id_vivienda"])
        self._nueva("visitas_obra", d["id_visita_obra"], id_visita_obra=d["id_visita_obra"], id_vivienda=d["id_vivienda"],
                    fecha=h.momento_registrado.date(), afo=d["afo"], observaciones=d.get("observaciones"),
                    id_tecnico=h.autor)


ACCIONES = frozenset({
    "crear_usuario", "registrar_alta", "observar_alta", "corregir_alta", "aprobar_alta", "rechazar_alta",
    "agregar_integrante", "registrar_solicitud", "asignar_expediente", "marcar_documento", "reemplazar_documento",
    "semiaprobar_solicitud", "confirmar_correccion", "aprobar_solicitud", "rechazar_solicitud", "completar_vivienda",
    "visita_inicial", "iniciar_obra", "subir_foto", "borrar_foto", "enviar_etapa", "aprobar_etapa", "observar_etapa",
    "prorrogar_etapa", "visita_obra",
})


def proyectar(hechos: Iterable[Hecho], corte: datetime, *, error_prorroga_java: bool = True) -> dict[str, list[dict]]:
    """Las 13 tablas como las vería Java en el momento `corte`: aplica, en orden de llegada, los hechos que llegaron al
    servidor hasta ese momento (inclusive)."""
    proyeccion = _Proyeccion(error_prorroga_java)
    llegados = [h for h in hechos if h.momento_registrado <= corte]
    for hecho in sorted(llegados, key=lambda x: x.momento_registrado):
        if hecho.accion not in ACCIONES:
            raise ValueError(f"Acción desconocida: {hecho.accion}")
        getattr(proyeccion, hecho.accion)(hecho)
    return {tabla: list(filas.values()) for tabla, filas in proyeccion.tablas.items()}
