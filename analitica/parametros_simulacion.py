"""Supuestos del origen simulado. Cada uno lleva su etiqueta [E#], documentada en docs/simulacion.md.

Los rangos (a, b) incluyen los dos extremos. Un mes son 30 días.
"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ParametrosSimulacion:
    fecha_referencia: date = date(2026, 10, 15)          # [E1] 120 obras en los 8 meses previos; el mismo
    obras_previas: int = 120                              #      ritmo sigue 12 meses después (un mes = 30 días)
    meses_previos: int = 8
    meses_posteriores: int = 12
    altas_aprobadas: int = 12                             # [E2]
    altas_pendientes: int = 2
    altas_rechazadas: int = 2
    prob_alta_observada: float = 0.30
    revision_alta_dias: tuple[int, int] = (3, 20)
    prob_og: float = 0.30
    tecnicos: int = 6                                     # [E3]
    operadores: int = 2
    arquitectos: int = 1
    administradores: int = 1
    integrantes_extra: tuple[int, int] = (0, 3)
    duracion_mediana: float = 1.2                         # [E4] estimada × log-normal, en hábiles, mínimo 1
    duracion_desvio: float = 0.35
    prob_observacion: float = 0.25                        # [E5]
    rondas_max: int = 3
    correccion_habiles: tuple[int, int] = (1, 3)          # [E6]
    prob_prorroga: float = 0.35                           # [E7]
    prorroga_habiles: tuple[int, int] = (2, 6)
    espera_revision_habiles: tuple[int, int] = (0, 4)     # [E8]
    prob_sin_conexion_urbano: float = 0.20                # [E9]
    prob_sin_conexion_resto: float = 0.50
    demora_sin_conexion_dias: tuple[int, int] = (1, 5)
    error_prorroga_java: bool = False                     # [E10] Java lo arregló el 31/10/2026; True = el Java anterior
    prob_sin_obra: float = 0.25                           # [E11]
    familiares: tuple[int, int] = (1, 8)                  # [E12]
    antiguedad_rancho: tuple[int, int] = (5, 40)
    expediente_dias: tuple[int, int] = (2, 15)            # [E13]
    visita_dias: tuple[int, int] = (3, 30)
    prob_semiaprobada: float = 0.30
    correccion_solicitud_dias: tuple[int, int] = (3, 20)
    aprobacion_dias: tuple[int, int] = (5, 45)
    inicio_obra_dias: tuple[int, int] = (0, 9)
    documentos_familia: tuple[int, int] = (5, 7)          # [E14]
    prob_documento_a_corregir: float = 0.20
    reemplazo_dias: tuple[int, int] = (2, 10)
    prob_vivienda_completada: float = 0.70                # [E15]
    completar_vivienda_dias: tuple[int, int] = (1, 20)
    pesos_tipo_vivienda: tuple[tuple[str, float], ...] = (("URBANA", 0.45), ("RURAL", 0.45), ("ECONOMICA", 0.10))
    superficie_m2: tuple[float, float] = (40.0, 60.0)
    dormitorios: tuple[int, ...] = (2, 3)
    visitas_obra: bool = False                            # [E16]
    fotos_por_ronda: tuple[int, int] = (2, 6)             # [E17]
    prob_foto_borrada: float = 0.10
    prob_ronda_sin_fotos: float = 0.05
    # [E19] El arquitecto asigna el técnico (SolicitudService.asignarTecnico) entre el registro y la visita inicial, y la
    # visita la hace ese técnico; sin técnico asignado no hay visita ni obra (validarTecnicoAsignado). Con False no se
    # asigna ninguno y ninguna solicitud pasa de Pendiente.
    asignar_tecnico: bool = True
    asignacion_tecnico_dias: tuple[int, int] = (1, 10)
    prob_tecnico_sin_visita: float = 0.50                 #      pendientes sin visita que ya tienen técnico
    habitantes_desvio: int = 1                            # [E20] visita inicial
    prob_prioridad_social: float = 0.30
    fotos_visita: tuple[int, int] = (2, 5)
    prob_observacion_organizacion: float = 0.50           # [E21] textos de listas fijas inventadas
    prob_departamento_de_la_organizacion: float = 0.70    # [E22] ubicación
    desvio_coordenadas: float = 0.05
    prob_rechazo_etapa: float = 0.0                       # [E23] hoy nadie puede rechazar en Java
    desfase_notificaciones_horas: int = 0                 # [E24] 3 = una JVM en UTC


PARAMETROS = ParametrosSimulacion()


@dataclass(frozen=True)
class Departamento:
    nombre: str
    localidad: str     # la cabecera
    latitud: float
    longitud: float
    peso: float        # concentración de población


# [S15] Distribución geográfica de Santiago del Estero, copiada del simulador de PP2 (con la corrección de Jiménez,
# cuya cabecera es Pozo Hondo). Los pesos suman 1,00.
DEPARTAMENTOS = (
    Departamento("Capital", "Santiago del Estero", -27.795, -64.261, 0.22),
    Departamento("Banda", "La Banda", -27.735, -64.240, 0.16),
    Departamento("Robles", "Fernández", -27.927, -63.887, 0.07),
    Departamento("Silípica", "Clodomira", -27.571, -64.133, 0.06),
    Departamento("Choya", "Frías", -28.648, -65.137, 0.06),
    Departamento("Moreno", "Quimilí", -27.638, -62.413, 0.05),
    Departamento("Jiménez", "Pozo Hondo", -27.163, -64.491, 0.05),
    Departamento("Figueroa", "Suncho Corral", -28.558, -63.443, 0.04),
    Departamento("Mitre", "Bandera", -29.274, -62.268, 0.04),
    Departamento("General Taboada", "Añatuya", -28.471, -62.829, 0.04),
    Departamento("Copo", "Monte Quemado", -25.800, -62.831, 0.03),
    Departamento("Ojo de Agua", "Ojo de Agua", -29.509, -63.697, 0.03),
    Departamento("Salavina", "Los Telares", -29.221, -63.520, 0.03),
    Departamento("Atamisqui", "Villa Atamisqui", -28.481, -63.821, 0.03),
    Departamento("Aguirre", "Nueva Esperanza", -27.652, -62.418, 0.03),
    Departamento("Guasayán", "El Charco", -28.064, -65.023, 0.02),
    Departamento("Rivadavia", "Pinto", -29.153, -61.897, 0.02),
    Departamento("Pellegrini", "Tintina", -27.034, -62.716, 0.02),
)

# [E9] Se usa la ubicación, no el tipo de vivienda (que es el prototipo).
DEPARTAMENTOS_URBANOS = ("Capital", "Banda")

# [S19] Límites de la provincia (25°35'S–30°41'20"S, 61°34'W–65°34'W).
LIMITES_PROVINCIA = {"latitud": (-30.69, -25.58), "longitud": (-65.57, -61.56)}

# [E20] Clasificación preliminar de la visita inicial (pesos inventados; suman 1,00).
PESOS_CLASIFICACION = {
    "TIPO_1A": 0.15, "TIPO_2A": 0.20, "TIPO_2B": 0.10, "TIPO_3A": 0.10, "TIPO_4A": 0.08, "TIPO_4B": 0.07,
    "TIPO_4C": 0.05, "TIPO_5A": 0.05, "TIPO_5B": 0.05, "TIPO_5C": 0.04, "TIPO_5D": 0.03, "DERRUMBE": 0.05,
    "OTRA": 0.03,
}

# [E21] Textos inventados.
MOTIVOS_SEMIAPROBACION = (
    "Falta la copia del DNI de un familiar",
    "El domicilio declarado no coincide con el certificado de residencia",
    "La declaración jurada está incompleta",
    "Corregir la antigüedad del rancho",
)
CAMPOS_OBSERVABLES = ("dni", "domicilio", "antiguedadRancho", "cantidadFamiliares", "telefono")
MOTIVOS_RECHAZO = (
    "La familia ya fue beneficiaria de otro programa habitacional",
    "El terreno no está a nombre de la familia",
    "No se pudo verificar la situación habitacional en la visita",
)
MOTIVOS_OBSERVACION_ALTA = (
    "La constancia de vigencia está vencida",
    "El acta de asamblea no es la actual",
    "Falta la constancia de la cuenta bancaria",
)
OBSERVACIONES_TECNICO = (
    "Falta la foto del encadenado",
    "Las fotos no muestran la capa aisladora",
    "Corregir el nivel del contrapiso antes de seguir",
    "Las fotos están borrosas, volver a sacarlas",
    "Falta terminar el revoque del lado norte",
)
OBSERVACIONES_ORGANIZACION = (
    "Etapa terminada",
    "Se adjuntan las fotos pedidas",
    "Terminamos con demora por la lluvia",
    "Quedó lista para revisar",
)
MOTIVOS_RECHAZO_ETAPA = (                                 # [E23]
    "La obra no respeta los planos del prototipo",
    "Se usaron materiales distintos de los aprobados",
    "Las fotos no corresponden a la vivienda",
)
MOTIVOS_PRORROGA = (
    "Lluvias",
    "Demora en la entrega de materiales",
    "Falta de mano de obra",
    "Problemas de acceso al terreno",
)
OBSERVACIONES_VISITA = (
    "Rancho de adobe con techo precario",
    "Vivienda con riesgo de derrumbe",
    "Familia numerosa en un solo ambiente",
    "Sin baño instalado",
    "Terreno inundable",
)
MOTIVOS_DOCUMENTO = (
    "El archivo no se lee",
    "El documento está vencido",
    "Falta el dorso",
)
