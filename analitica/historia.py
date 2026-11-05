"""La historia de las etapas: cuándo empezó, se envió, se observó, se prorrogó, se aprobó o se rechazó cada una.

El sistema de Desarrollo pisa esos datos en cada ronda, pero desde el 03/11/2026 guarda una notificación por cada acción
sobre una etapa, con su hora exacta y sin borrarla nunca: es la fuente principal de la historia. La notificación no dice
de qué etapa se trata (solo la solicitud), así que la etapa se deduce contando las aprobaciones anteriores. Todos los
eventos del servicio comparten el contrato de `COLUMNAS_EVENTOS`.
"""
from collections.abc import Iterable, Mapping
from datetime import timedelta

import pandas as pd

from analitica.esquema import es_vacio
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
        t0 = de_la_solicitud["fecha"].iloc[0]
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
