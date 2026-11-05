"""La historia de las etapas: cuándo empezó, se envió, se observó, se prorrogó, se aprobó o se rechazó cada una.

El sistema de Desarrollo pisa esos datos en cada ronda, pero desde el 03/11/2026 guarda una notificación por cada acción
sobre una etapa, con su hora exacta y sin borrarla nunca: es la fuente principal de la historia. La notificación no dice
de qué etapa se trata (solo la solicitud), así que la etapa se deduce contando las aprobaciones anteriores. Todos los
eventos del servicio comparten el contrato de `COLUMNAS_EVENTOS`.
"""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pandas as pd

from analitica.esquema import clave_de, es_vacio
from analitica.origenes.base import Lectura

COLUMNAS_EVENTOS = ("entidad", "clave", "id_solicitud", "numero", "tipo", "ronda", "momento", "precision", "fuente",
                    "detalle")
TIPOS_EVENTO_ETAPA = ("inicio", "envio", "observacion", "aprobacion", "prorroga", "rechazo")
PRECISIONES = ("exacto", "dia", "intervalo")
FUENTES = ("notificaciones", "versiones", "lectura")
TIPO_POR_NOTIFICACION = {
    "ETAPA_HABILITADA": "inicio", "ETAPA_ENVIADA": "envio", "ETAPA_APROBADA": "aprobacion",
    "ETAPA_OBSERVADA": "observacion", "ETAPA_PRORROGADA": "prorroga", "ETAPA_RECHAZADA": "rechazo",
}
_TIPOS_PANDAS = {"entidad": "string", "clave": "string", "id_solicitud": "Int64", "numero": "Int64", "tipo": "string",
                 "ronda": "Int64", "momento": "datetime64[ns]", "precision": "string", "fuente": "string"}
_ULTIMA_ETAPA = 6


def tabla_eventos(filas: Iterable[Mapping]) -> pd.DataFrame:
    """Los eventos con las columnas del contrato, en orden y con su tipo (`detalle` es un dict, `{}` si falta)."""
    filas = list(filas)
    datos = {}
    for columna in COLUMNAS_EVENTOS:
        valores = [fila.get(columna) for fila in filas]
        if columna == "detalle":
            datos[columna] = pd.Series([v if isinstance(v, dict) else {} for v in valores], dtype="object")
        else:
            datos[columna] = pd.Series([None if es_vacio(v) else v for v in valores], dtype=_TIPOS_PANDAS[columna])
    return pd.DataFrame(datos, columns=list(COLUMNAS_EVENTOS))


def deduplicar_notificaciones(notificaciones: pd.DataFrame, ventana_segundos: int = 60) -> pd.DataFrame:
    """Una fila por evento: Java guarda una notificación por destinatario, todas en el mismo momento. Las de un mismo
    tipo y una misma solicitud a menos de `ventana_segundos` de la primera son el mismo evento; queda la más temprana."""
    filas = notificaciones[["tipo", "id_referencia", "fecha"]].dropna().sort_values(["id_referencia", "tipo", "fecha"])
    eventos, abierto = [], None
    for tipo, id_referencia, fecha in filas.itertuples(index=False):
        if abierto and abierto[:2] == (tipo, id_referencia) and fecha - abierto[2] < timedelta(seconds=ventana_segundos):
            continue
        abierto = (tipo, id_referencia, fecha)
        eventos.append({"tipo": tipo, "id_referencia": int(id_referencia), "fecha": fecha})
    return pd.DataFrame(eventos, columns=["tipo", "id_referencia", "fecha"]).sort_values("fecha", kind="stable")


def _etapas_por_solicitud(etapas: pd.DataFrame) -> dict[int, pd.DataFrame]:
    return {int(id_solicitud): de_la_obra for id_solicitud, de_la_obra in etapas.groupby("id_solicitud")}


def _numerar(eventos: pd.DataFrame, etapas: pd.DataFrame) -> list[dict]:
    """Etapa y ronda de cada notificación deduplicada: por solicitud y en orden, la etapa es 1 + las aprobaciones
    anteriores (más las que la tabla de etapas muestra aprobadas antes de la primera notificación). Cada aprobación de
    la etapa k < 6 abre además el inicio de la k + 1."""
    de_cada_obra = _etapas_por_solicitud(etapas)
    orden = {tipo: n for n, tipo in enumerate(TIPO_POR_NOTIFICACION)}
    filas = []
    for id_solicitud, de_la_solicitud in eventos.groupby("id_referencia"):
        id_solicitud = int(id_solicitud)
        de_la_solicitud = de_la_solicitud.assign(_orden=de_la_solicitud["tipo"].map(orden)).sort_values(["fecha", "_orden"])
        obra = de_cada_obra.get(id_solicitud, etapas.iloc[0:0])
        claves = {int(e["numero"]): str(int(e["id_etapa_obra"])) for _, e in obra.iterrows()}
        # fecha_revision está truncada al minuto: una aprobación del mismo minuto que la primera notificación es esa misma.
        t0 = de_la_solicitud["fecha"].iloc[0].floor("min")
        aprobadas = int(((obra["estado"] == "APROBADA") & (obra["fecha_revision"] < t0)).sum())
        envios: dict[int, int] = {}
        for tipo_java, _, fecha, _ in de_la_solicitud.itertuples(index=False):
            tipo = TIPO_POR_NOTIFICACION.get(tipo_java)
            if tipo is None:
                continue
            numero = min(aprobadas + 1, _ULTIMA_ETAPA)
            fila = {"entidad": "etapas", "clave": claves.get(numero), "id_solicitud": id_solicitud, "numero": numero,
                    "tipo": tipo, "momento": fecha, "precision": "exacto", "fuente": "notificaciones", "detalle": {}}
            if tipo == "envio":
                envios[numero] = envios.get(numero, 0) + 1
                fila["ronda"] = envios[numero]
            filas.append(fila)
            if tipo == "aprobacion":
                aprobadas += 1
                if numero < _ULTIMA_ETAPA:
                    filas.append(fila | {"clave": claves.get(numero + 1), "numero": numero + 1, "tipo": "inicio",
                                         "detalle": {"derivado_de": "aprobacion"}})
    return filas


def estimar_desfase_horas(lectura: Lectura) -> int:
    """Las horas que la hora de las notificaciones está corrida respecto de Buenos Aires (Java las guarda con la zona
    de la JVM). Compara el último envío notificado de cada etapa con su `fecha_envio`, que sí está en hora de Buenos
    Aires; devuelve la mediana en horas enteras, entre −12 y 12, o 0 si no hay con qué comparar."""
    eventos = deduplicar_notificaciones(lectura.tabla("notificaciones"))
    etapas = lectura.tabla("etapas")
    if eventos.empty or etapas.empty:
        return 0
    envios = {}
    for fila in _numerar(eventos, etapas):
        if fila["tipo"] == "envio":
            envios[(fila["id_solicitud"], fila["numero"])] = fila["momento"]          # queda el último
    diferencias = []
    for _, e in etapas.dropna(subset=["fecha_envio"]).iterrows():
        notificado = envios.get((int(e["id_solicitud"]), int(e["numero"])))
        if notificado is not None:
            diferencias.append(round((notificado - e["fecha_envio"]).total_seconds() / 3600))
    if not diferencias:
        return 0
    mediana = round(pd.Series(diferencias).median())
    return int(mediana) if -12 <= mediana <= 12 else 0


def eventos_de_notificaciones(lectura: Lectura, desfase_horas: int | None = None) -> pd.DataFrame:
    """Los eventos de etapa que dicen las notificaciones (fuente `notificaciones`, todos `exacto`), con la hora corregida
    por el desfase (estimado si no se pasa)."""
    if desfase_horas is None:
        desfase_horas = estimar_desfase_horas(lectura)
    eventos = deduplicar_notificaciones(lectura.tabla("notificaciones"))
    if eventos.empty:
        return tabla_eventos([])
    eventos = eventos.assign(fecha=eventos["fecha"] - pd.Timedelta(hours=desfase_horas))
    tabla = tabla_eventos(_numerar(eventos, lectura.tabla("etapas")))
    return tabla.sort_values(["momento", "id_solicitud"], kind="stable").reset_index(drop=True)


# --- vínculos de cada fila con su solicitud ---

def _entero(valor) -> int | None:
    return None if es_vacio(valor) else int(valor)


def _mapa(tabla: pd.DataFrame, desde: str, hacia: str) -> dict[int, int]:
    pares = tabla[[desde, hacia]].dropna()
    return {int(a): int(b) for a, b in zip(pares[desde], pares[hacia])}


@dataclass(frozen=True)
class Vinculos:
    """A qué solicitud pertenece cada fila: directo, o a través de su etapa, su vivienda, su familia o su visita."""
    etapa_a_solicitud: dict[int, int]
    vivienda_a_solicitud: dict[int, int]
    familia_a_solicitud: dict[int, int]
    visita_a_solicitud: dict[int, int]

    def id_solicitud(self, entidad: str, fila: Mapping) -> int | None:
        if entidad in ("solicitudes", "viviendas", "etapas", "visitas_iniciales"):
            return _entero(fila.get("id_solicitud"))
        if entidad == "fotos_etapa":
            return self.etapa_a_solicitud.get(_entero(fila.get("id_etapa_obra")))
        if entidad == "fotos_visita":
            return self.visita_a_solicitud.get(_entero(fila.get("id_visita")))
        if entidad == "visitas_obra":
            return self.vivienda_a_solicitud.get(_entero(fila.get("id_vivienda")))
        if entidad in ("familias", "documentos"):
            return self.familia_a_solicitud.get(_entero(fila.get("id_familia")))
        if entidad == "notificaciones":
            return _entero(fila.get("id_referencia"))
        return None


def vinculos(lectura: Lectura) -> Vinculos:
    return Vinculos(etapa_a_solicitud=_mapa(lectura.tabla("etapas"), "id_etapa_obra", "id_solicitud"),
                    vivienda_a_solicitud=_mapa(lectura.tabla("viviendas"), "id_vivienda", "id_solicitud"),
                    familia_a_solicitud=_mapa(lectura.tabla("solicitudes"), "id_familia", "id_solicitud"),
                    visita_a_solicitud=_mapa(lectura.tabla("visitas_iniciales"), "id_visita", "id_solicitud"))


# --- lo que fecha una sola lectura ---

def _a_las_cero(dia: date) -> datetime:
    return datetime.combine(dia, time())


def _iso(dia) -> str | None:
    return None if es_vacio(dia) else dia.isoformat()


def eventos_de_la_lectura(lectura: Lectura) -> pd.DataFrame:
    """Lo que una sola foto de las tablas permite fechar (fuente `lectura`): la historia que hay sin base propia y la
    línea de base de la primera corrida del sincronizador. De cada etapa se ve solo el último envío y la última revisión."""
    v = vinculos(lectura)
    filas = []

    def evento(entidad, fila, tipo, momento, precision, **extra):
        if es_vacio(momento):
            return
        filas.append({"entidad": entidad, "clave": clave_de(entidad, fila), "id_solicitud": v.id_solicitud(entidad, fila),
                      "tipo": tipo, "momento": momento, "precision": precision, "fuente": "lectura", **extra})

    activacion = {}
    for fila in lectura.tabla("solicitudes").to_dict("records"):
        evento("solicitudes", fila, "solicitud_registrada", _dia_a_momento(fila["fecha_solicitud"]), "dia")
        evento("solicitudes", fila, "solicitud_aprobada", _dia_a_momento(fila["fecha_activacion"]), "dia")
        activacion[_entero(fila["id_solicitud"])] = fila["fecha_activacion"]
    for fila in lectura.tabla("viviendas").to_dict("records"):
        evento("viviendas", fila, "vivienda_creada", _dia_a_momento(activacion.get(_entero(fila["id_solicitud"]))), "dia")
    for fila in lectura.tabla("visitas_iniciales").to_dict("records"):
        evento("visitas_iniciales", fila, "visita_inicial", fila["fecha_visita"], "exacto")
    for fila in lectura.tabla("etapas").to_dict("records"):
        numero = _entero(fila["numero"])
        evento("etapas", fila, "inicio", _dia_a_momento(fila["fecha_inicio"]), "dia", numero=numero)
        evento("etapas", fila, "envio", fila["fecha_envio"], "exacto", numero=numero)
        revision = {"APROBADA": "aprobacion", "RECHAZADA": "rechazo"}.get(fila["estado"], "observacion")
        evento("etapas", fila, revision, fila["fecha_revision"], "exacto", numero=numero)
        if not es_vacio(fila["fecha_limite"]) and not es_vacio(fila["fecha_limite_original"]) \
                and fila["fecha_limite"] != fila["fecha_limite_original"]:
            evento("etapas", fila, "prorroga", lectura.leido_en, "intervalo", numero=numero,
                   detalle={"limite_anterior": _iso(fila["fecha_limite_original"]), "limite_nuevo": _iso(fila["fecha_limite"]),
                            "motivo": None if es_vacio(fila["motivo_prorroga"]) else fila["motivo_prorroga"],
                            "neta": True})
    for fila in lectura.tabla("fotos_etapa").to_dict("records"):
        evento("fotos_etapa", fila, "foto_subida", fila["fecha_subida"], "exacto")
    for fila in lectura.tabla("documentos").to_dict("records"):
        evento("documentos", fila, "documento_subido", fila["fecha_subida"], "exacto")
        if fila["estado"] == "A_CORREGIR":
            evento("documentos", fila, "documento_a_corregir", fila["fecha_revision"], "exacto")
    for fila in lectura.tabla("solicitudes_organizacion").to_dict("records"):
        evento("solicitudes_organizacion", fila, "alta_registrada", _dia_a_momento(fila["fecha_solicitud"]), "dia")
        evento("solicitudes_organizacion", fila, "alta_aprobada", _dia_a_momento(fila["fecha_aprobacion"]), "dia")
        evento("solicitudes_organizacion", fila, "alta_rechazada", _dia_a_momento(fila["fecha_rechazo"]), "dia")
    return tabla_eventos(filas)


def _dia_a_momento(dia) -> datetime | None:
    return None if es_vacio(dia) else _a_las_cero(dia)


# --- elegir la historia de cada obra ---

def _primera_notificacion(de_notificaciones: pd.DataFrame) -> dict[int, pd.Timestamp]:
    return {int(s): t for s, t in de_notificaciones.groupby("id_solicitud")["momento"].min().items()}


def obras_con_notificaciones_incompletas(de_notificaciones: pd.DataFrame, etapas: pd.DataFrame) -> set[int]:
    """Las obras con menos aprobaciones notificadas que etapas aprobadas desde su primera notificación (por ejemplo,
    una organización sin integrantes con usuario no recibe avisos y Java no los guarda)."""
    incompletas = set()
    for id_solicitud, t0 in _primera_notificacion(de_notificaciones).items():
        notificadas = int(((de_notificaciones["id_solicitud"] == id_solicitud)
                           & (de_notificaciones["tipo"] == "aprobacion")).sum())
        de_la_obra = etapas[etapas["id_solicitud"] == id_solicitud]
        aprobadas = int(((de_la_obra["estado"] == "APROBADA") & (de_la_obra["fecha_revision"] >= t0.floor("min"))).sum())
        if notificadas < aprobadas:
            incompletas.add(id_solicitud)
    return incompletas


def _coincide(evento, notificados: pd.DataFrame) -> bool:
    """Un evento de otra fuente que es el mismo que uno notificado: misma etapa y tipo, y el mismo día (precisión día) o
    el mismo minuto (precisión exacta; Java guarda envíos y revisiones truncados al minuto)."""
    mismos = notificados[(notificados["numero"] == evento.numero) & (notificados["tipo"] == evento.tipo)]
    if evento.precision == "dia":
        return bool((mismos["momento"].dt.normalize() == evento.momento.normalize()).any())
    if evento.precision == "exacto":
        return bool((mismos["momento"].dt.floor("min") == evento.momento.floor("min")).any())
    return False


def elegir_historia_de_etapas(de_notificaciones: pd.DataFrame, otros: pd.DataFrame, etapas: pd.DataFrame) -> pd.DataFrame:
    """La historia de cada obra: sus notificaciones desde la primera, más los eventos de etapa de otra fuente anteriores
    a ella que no coincidan con uno notificado. Una obra con notificaciones incompletas usa solo la otra fuente. Los
    eventos de otras entidades pasan siempre."""
    incompletas = obras_con_notificaciones_incompletas(de_notificaciones, etapas)
    primera = {s: t for s, t in _primera_notificacion(de_notificaciones).items() if s not in incompletas}
    notificados = de_notificaciones[de_notificaciones["id_solicitud"].isin(list(primera))]
    de_etapas = otros["entidad"] == "etapas"
    conservar = []
    for evento in otros[de_etapas].itertuples():
        id_solicitud = None if pd.isna(evento.id_solicitud) else int(evento.id_solicitud)
        t0 = primera.get(id_solicitud)
        if t0 is None:
            conservar.append(evento.Index)
        elif evento.momento < t0 and not _coincide(evento, notificados[notificados["id_solicitud"] == id_solicitud]):
            conservar.append(evento.Index)
    partes = [p for p in (notificados, otros[de_etapas].loc[conservar], otros[~de_etapas]) if not p.empty]
    return _ordenar(pd.concat(partes, ignore_index=True) if partes else tabla_eventos([]))


def _ordenar(eventos: pd.DataFrame) -> pd.DataFrame:
    return eventos.sort_values(["momento", "id_solicitud", "entidad", "tipo"], kind="stable").reset_index(drop=True)


def eventos_para_contexto(lectura: Lectura, eventos_guardados: pd.DataFrame | None = None,
                          desfase_horas: int | None = None) -> pd.DataFrame:
    """Todos los eventos que usan los indicadores y la API: la historia de etapas elegida (notificaciones primero) y los
    del resto de las entidades. Sin base propia, la otra fuente es lo que fecha la lectura misma."""
    otros = eventos_guardados if eventos_guardados is not None else eventos_de_la_lectura(lectura)
    return elegir_historia_de_etapas(eventos_de_notificaciones(lectura, desfase_horas), otros, lectura.tabla("etapas"))
