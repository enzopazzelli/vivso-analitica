# El origen simulado

## 1. Para qué

El servicio tiene que funcionar de punta a punta **sin depender de Desarrollo**: mientras no haya acceso a la base
real, lee un mundo inventado que tiene las mismas 13 tablas y respeta las mismas reglas que el sistema de Java
(ver [sistema-de-desarrollo.md](sistema-de-desarrollo.md)). Además, como el simulador sabe lo que pasó de verdad, sirve
de vara para evaluar el servicio: cuánta historia recupera, qué tan exacto es el avance de obra y cuánto se equivocan
los indicadores.

## 2. Cómo funciona

El simulador tiene dos capas:

1. **La verdad:** los hechos de cada flujo —un alta de organización, el registro de una solicitud, una foto, un envío,
   una revisión, una prórroga—, cada uno con su **momento real** (cuándo pasó), su **momento registrado** (cuándo llegó
   al servidor, que es la hora que guarda Java) y su **autor**. Las personas, los CUIT y los textos son inventados
   (Faker en español de Argentina y correos `@example.com`). Todo sale de generadores sembrados: la misma semilla da
   siempre el mismo mundo.
2. **La proyección:** aplica los hechos, en el orden en que llegaron al servidor, con las reglas de los servicios de
   Java: las mismas precondiciones, los mismos campos que se pisan, la vivienda vacía al aprobar, las fotos que se
   borran sin rastro. Los ids se asignan como el autoincremental de MySQL: en orden de llegada.

```mermaid
flowchart LR
    P["parametros_simulacion.py"] --> O["simulado_organizaciones<br/>personal y altas"]
    O --> S["simulado_solicitudes<br/>trámite, familias, visitas, viviendas"]
    S --> B["simulado_obras<br/>etapas, fotos, avance físico"]
    O --> H["hechos con Ref"]
    S --> H
    B --> H
    H --> I["asignar_ids<br/>autoincremental por llegada"]
    I --> V["verdad()"]
    I --> PR["proyectar(hechos, corte)<br/>reglas de Java"]
    PR --> A["armar_tabla de las 13"]
    A --> L["Lectura<br/>verificar_lectura"]
    B --> AV["avance_real()"]
```

Una lectura muestra el mundo **a un corte**: solo lo que llegó al servidor hasta ese momento. Un envío hecho sin
conexión antes del corte, pero que llegó después, todavía no aparece.

```mermaid
flowchart LR
    V["todos los hechos del mundo"] --> F{"¿momento registrado<br/>menor o igual al corte?"}
    F -->|"sí"| P["se aplica con su regla de Java<br/>en orden de llegada"]
    F -->|"no"| N["todavía no llegó al servidor"]
    P --> T["13 tablas al corte"]
```

## 3. El mundo alrededor de la fecha de referencia

El mundo se arma alrededor de una **fecha de referencia fija** (15/10/2026) y no depende del corte. Así, dos lecturas
con cortes distintos ven el mismo mundo en dos momentos —lo que necesita la sincronización para reconstruir la
historia— y la demo sigue viva con el paso de los días: después de la referencia siguen llegando obras al mismo ritmo.

```mermaid
gantt
    title Mundo simulado alrededor de la fecha de referencia
    dateFormat YYYY-MM-DD
    axisFormat %m/%y
    todayMarker off
    section Personal
    Usuarios del personal :milestone, hito1, 2025-04-23, 0d
    section Organizaciones
    Registro de las 12 altas aprobadas :2025-05-23, 30d
    Altas pendientes y rechazadas :2026-08-16, 60d
    section Solicitudes
    Registro de las que no llegan a obra :2025-11-19, 690d
    section Obras
    120 obras iniciadas antes de la referencia :2026-02-17, 240d
    180 obras más al mismo ritmo :2026-10-16, 360d
```

## 4. Un trámite y una etapa simulados

El trámite de una solicitud (días corridos):

```mermaid
flowchart LR
    R["registro<br/>5 a 7 documentos"] -->|"2 a 15 días"| X["expediente"]
    R -->|"3 a 30 días"| V["visita inicial"]
    V -->|"30 %"| S["semiaprobación<br/>documentos a corregir"]
    S -->|"3 a 20 días"| C["corrección confirmada"]
    C --> A
    V -->|"5 a 45 días"| A["aprobación<br/>vivienda vacía"]
    X --> A
    A -->|"0 a 9 días"| I["inicio de obra"]
    A -->|"70 %, 1 a 20 días"| VC["vivienda completada<br/>por el arquitecto"]
```

Las solicitudes que no llegan a obra se reparten por partes iguales:

```mermaid
flowchart LR
    N["solicitud sin obra"] --> P1["pendiente<br/>sin resolver"]
    N --> P2["semiaprobada<br/>sin corregir"]
    N --> P3["rechazada<br/>después de la visita"]
    N --> P4["aprobada<br/>sin iniciar"]
```

Una etapa de obra, ronda por ronda:

```mermaid
flowchart TD
    A["activar etapa<br/>inicio y límite de Java"] --> T["trabajo real<br/>D = est × log-normal, mínimo 1 hábil"]
    T --> C{"¿la ronda va sin conexión?<br/>20 % en Capital y Banda, 50 % en el resto"}
    C -->|"no"| F1["fotos en su momento real<br/>10 %: una se borra antes de enviar"]
    C -->|"sí"| F2["fotos y envío en ráfaga<br/>a la reconexión, 1 a 5 días después"]
    F1 --> P{"¿el envío llegaría después<br/>del día del límite?"}
    F2 --> P
    P -->|"sí, 35 %, una vez por etapa"| PR["prorrogar_etapa<br/>2 a 6 hábiles más"]
    PR -->|"con [E10]"| TR["etapa trabada<br/>la obra termina ahí"]
    PR -->|"sin [E10]"| E
    P -->|"no"| E["enviar_etapa"]
    E --> R["revisión del técnico<br/>0 a 4 hábiles después"]
    R -->|"25 %, hasta 3 rondas"| O["observar_etapa<br/>corrección en 1 a 3 hábiles"]
    O --> C
    R -->|"si no"| AP["aprobar_etapa<br/>se activa la siguiente"]
    AP --> A
```

El avance físico real de cada obra ([E18]) es la vara contra la cual se evalúa el AFO:

```mermaid
flowchart LR
    I["inicio de la etapa<br/>aporta 0"] -->|"línea recta en días hábiles"| F["fin físico = primer envío real<br/>aporta sus días estimados"]
    F --> S["avance = 100 × suma de aportes / 29"]
```

**Las obras trabadas.** Como Java no deja enviar una etapa prorrogada ([E10]) y una etapa que se va a vencer se
prorroga el 35 % de las veces ([E7]), la mayoría de las obras simuladas termina trabada en alguna etapa. Con la semilla 8,
a la fecha de referencia, de las 120 obras iniciadas 93 están trabadas, 21 siguen en curso y 6 terminaron. No es un error del simulador: es
lo que haría hoy el sistema real con esos supuestos, y se puede cambiar sin tocar código (bajando `prob_prorroga` o con
`error_prorroga_java=False`).

## 5. Cómo se usa

Desde la línea de comandos:

```powershell
.venv\Scripts\python.exe -m analitica simular --hasta 2026-10-15
.venv\Scripts\python.exe -m analitica simular --hasta 2026-10-15 --csv salidas\simulado
```

Muestra las filas de cada tabla, las obras por etapa actual (como las muestra la web de Desarrollo) y si hay filas
huérfanas; con `--csv` guarda las 13 tablas. La semilla por defecto es 8 y el corte por defecto, ahora.

Desde Python:

```python
from datetime import date
from analitica.origenes.simulado import OrigenSimulado

origen = OrigenSimulado(semilla=8, hasta=date(2026, 10, 15))
lectura = origen.leer()                           # las 13 tablas al corte
antes = origen.leer_al(date(2026, 9, 15))         # el mismo mundo, un mes antes
hechos = origen.verdad()                          # lo que pasó de verdad, con ids
origen.avance_real(id_solicitud=12, dia=date(2026, 10, 15))
```

## 6. Cómo se apaga

Con `ANALITICA_ORIGEN=vacio` el servicio no usa el simulador: el origen vacío devuelve las 13 tablas sin filas. El
comando `simular` sigue mostrando el simulador, pero avisa que el servicio no lo está usando.

```mermaid
flowchart LR
    E["ANALITICA_ORIGEN<br/>o el código que se pasa"] --> C{"crear_origen"}
    C -->|"simulado"| S["OrigenSimulado()"]
    C -->|"vacio"| V["OrigenVacio()<br/>13 tablas vacías"]
    C -->|"mysql o api"| N["OrigenNoDisponible<br/>todavía no está implementado"]
```

## 7. Supuestos

Están en `analitica/parametros_simulacion.py`, cada uno con su etiqueta. Los rangos incluyen los dos extremos y un mes
son 30 días.

| Etiqueta | Supuesto | Valor |
| :--- | :--- | :--- |
| `[E1]` | Obras | 120 iniciadas en los 8 meses previos a la fecha de referencia (15/10/2026) y el mismo ritmo (15 por mes) durante los 12 meses siguientes: 300 en total |
| `[E2]` | Organizaciones | 12 altas aprobadas, 2 pendientes y 2 rechazadas; el 30 % de las aprobadas pasa por una observación; cada paso del alta tarda 3 a 20 días; 30 % de OG (Municipio y Comisión Municipal, sin repetir departamento) y el resto ONG (Asociación civil y Cooperativa) |
| `[E3]` | Usuarios | 6 técnicos, 2 operadores, 1 arquitecto y 1 administrador; presidente y tesorero de cada organización con usuario `INTEGRANTE`; de 0 a 3 integrantes más sin usuario |
| `[E4]` | Duración real de una etapa | días estimados × factor log-normal (mediana 1,2; desvío 0,35), en días hábiles, mínimo 1 |
| `[E5]` | Observación de un envío | 0,25 por ronda; a lo sumo 3 rondas |
| `[E6]` | Corrección tras una observación | 1 a 3 días hábiles |
| `[E7]` | Prórroga cuando la etapa se va a vencer | probabilidad 0,35, a lo sumo una por etapa; agrega 2 a 6 días hábiles |
| `[E8]` | Espera de la revisión del técnico | 0 a 4 días hábiles |
| `[E9]` | Carga sin conexión | envíos y fotos de etapa que llegan 1 a 5 días después (más 0 a 10 horas): 20 % de las rondas en Capital y Banda, 50 % en el resto |
| `[E10]` | Error de Java en etapas prorrogadas | activado: una etapa prorrogada no puede enviarse y queda trabada |
| `[E11]` | Solicitudes que no llegan a obra | 25 % (100): pendientes, semiaprobadas, rechazadas o aprobadas sin iniciar, por partes iguales |
| `[E12]` | Familias | 1 a 8 familiares; antigüedad del rancho de 5 a 40 años |
| `[E13]` | Trámite de la solicitud | expediente a los 2 a 15 días; visita inicial a los 3 a 30 días del registro; 30 % semiaprobadas, con corrección en 3 a 20 días; aprobación 5 a 45 días después de la visita; obra iniciada 0 a 9 días después de aprobada |
| `[E14]` | Documentos de familia | 5 a 7 al registrar la solicitud; el 20 % se marca para corregir y se reemplaza en 2 a 10 días |
| `[E15]` | Vivienda | el arquitecto la completa en el 70 % de los casos, 1 a 20 días después de aprobada; tipo `URBANA` 45 %, `RURAL` 45 %, `ECONOMICA` 10 %; 40 a 60 m²; 2 o 3 dormitorios |
| `[E16]` | Visitas de obra | ninguna, como en el flujo nuevo; un parámetro las activa (una por etapa aprobada) |
| `[E17]` | Fotos de etapa | 2 a 6 por ronda; en el 10 % de las rondas con conexión se borra una antes de enviar; en el 5 % de las rondas se envía sin fotos |
| `[E18]` | Avance físico real | crece en línea recta con los días hábiles de cada etapa, desde que se activa hasta su primer envío real |
| `[E19]` | Técnico asignado | se asigna al aprobar la solicitud. Java no deja iniciar ni revisar una obra sin técnico asignado, y hoy ningún flujo lo completa: el simulador supone que ya existe la vista del arquitecto. Con el parámetro apagado (como hoy en Java) ninguna obra podría iniciarse |
| `[E20]` | Visita inicial | clasificación con pesos inventados (la más frecuente, `TIPO_2A`, 20 %); habitantes = familiares ± 1; prioridad social 30 %; 2 a 5 fotos |
| `[E21]` | Textos | motivos y observaciones de listas fijas inventadas; la organización deja un texto en el 50 % de los envíos |
| `[E22]` | Ubicación | el 70 % de las solicitudes en el departamento de la organización; coordenadas alrededor de la cabecera (desvío 0,05°) dentro de la provincia |
| `[S15]` | Departamentos | los 18 departamentos de Santiago del Estero con su cabecera, sus coordenadas y su peso de población, del simulador de PP2 |

## 8. Lo que no modela

- Supone que ya existe la vista del arquitecto que asigna el técnico de cada solicitud: sin ella, Java no deja iniciar
  ninguna obra.
- El calendario del simulador no cuenta feriados, como Java hoy.
- A lo sumo una prórroga por etapa.
- Las visitas iniciales no tienen demora de conexión (guardan la hora del celular, como en Java).
- Lo que se borra en el celular sin conexión nunca llega al servidor, así que no se ve.
- Las personas, los CUIT, las direcciones y los textos son inventados: no describen el programa real.
