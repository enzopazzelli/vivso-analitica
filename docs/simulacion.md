# El origen simulado

## 1. Para qué

El servicio tiene que funcionar de punta a punta **sin depender de Desarrollo**: mientras no haya acceso a la base
real, lee un mundo inventado que tiene las mismas 14 tablas y respeta las mismas reglas que el sistema de Java
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
   borran sin rastro y las notificaciones que deja cada acción sobre una etapa. Los ids se asignan como el
   autoincremental de MySQL: en orden de llegada.

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
    PR --> A["armar_tabla de las 14"]
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
    P --> T["14 tablas al corte"]
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
    R -->|"1 a 10 días"| TA["técnico asignado<br/>por el arquitecto"]
    TA -->|"antes de la visita"| V["visita inicial<br/>la hace ese técnico"]
    R -->|"3 a 30 días"| V
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
    P -->|"sí, 35 %, una vez por etapa"| PR["prorrogar_etapa<br/>2 a 6 hábiles más<br/>se siguen subiendo fotos"]
    PR -->|"como hoy en Java"| E
    PR -->|"con [E10], el Java anterior al 31/10"| TR["etapa trabada<br/>la obra termina ahí"]
    P -->|"no"| E["enviar_etapa"]
    E --> R["revisión del técnico<br/>0 a 4 hábiles después"]
    R -->|"[E23], 0 % por defecto"| RE["rechazar_etapa<br/>la obra se detiene"]
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

Cada acción sobre una etapa deja notificaciones, como en el sistema de Desarrollo ([E24]): son las que después permiten
reconstruir la historia de cada obra.

```mermaid
sequenceDiagram
    participant T as Técnico asignado
    participant J as Proyección (reglas de Java)
    participant O as Integrantes de la organización
    T->>J: iniciar_obra
    J-->>O: ETAPA_HABILITADA (una por integrante activo con usuario)
    O->>J: enviar_etapa
    J-->>T: ETAPA_ENVIADA
    T->>J: observar, prorrogar, aprobar o rechazar
    J-->>O: ETAPA_OBSERVADA, ETAPA_PRORROGADA, ETAPA_APROBADA o ETAPA_RECHAZADA
```

**Cómo queda el mundo a la fecha de referencia.** Con la semilla 8, de las 120 obras iniciadas, 74 terminaron y 46 siguen
en curso (7 de ellas prorrogadas, que se pueden enviar igual); ninguna queda trabada y hay 2766 notificaciones. Hasta el
31/10/2026 el sistema de Desarrollo no dejaba enviar una etapa prorrogada, y con los mismos supuestos 93 de las 120 obras
quedaban trabadas: Desarrollo lo arregló, y el simulador puede reproducir el comportamiento anterior con
`error_prorroga_java=True` ([E10]).

## 5. Cómo se usa

Desde la línea de comandos:

```powershell
.venv\Scripts\python.exe -m analitica simular --hasta 2026-10-15
.venv\Scripts\python.exe -m analitica simular --hasta 2026-10-15 --csv salidas\simulado
```

Muestra las filas de cada tabla, las obras por etapa actual (como las muestra la web de Desarrollo) y si hay filas
huérfanas; con `--csv` guarda las 14 tablas. La semilla por defecto es 8 y el corte por defecto, ahora.

Desde Python:

```python
from datetime import date
from analitica.origenes.simulado import OrigenSimulado

origen = OrigenSimulado(semilla=8, hasta=date(2026, 10, 15))
lectura = origen.leer()                           # las 14 tablas al corte
antes = origen.leer_al(date(2026, 9, 15))         # el mismo mundo, un mes antes
hechos = origen.verdad()                          # lo que pasó de verdad, con ids
origen.avance_real(id_solicitud=12, dia=date(2026, 10, 15))
```

## 6. Cómo se apaga

Con `ANALITICA_ORIGEN=vacio` el servicio no usa el simulador: el origen vacío devuelve las 14 tablas sin filas. El
comando `simular` sigue mostrando el simulador, pero avisa que el servicio no lo está usando.

```mermaid
flowchart LR
    E["ANALITICA_ORIGEN<br/>o el código que se pasa"] --> C{"crear_origen"}
    C -->|"simulado"| S["OrigenSimulado()"]
    C -->|"vacio"| V["OrigenVacio()<br/>14 tablas vacías"]
    C -->|"mysql o api"| N["OrigenNoDisponible<br/>todavía no está implementado"]
```

## 7. Supuestos

Están en `analitica/parametros_simulacion.py`, cada uno con su etiqueta. Los rangos incluyen los dos extremos y un mes
son 30 días.

| Etiqueta | Supuesto | Valor |
| :--- | :--- | :--- |
| `[E1]` | Obras | 120 iniciadas en los 8 meses previos a la fecha de referencia (15/10/2026) y el mismo ritmo (15 por mes) durante los 12 meses siguientes: 300 en total |
| `[E2]` | Organizaciones | 12 altas aprobadas, 2 pendientes y 2 rechazadas; el 30 % de las aprobadas pasa por una observación; cada paso del alta tarda 3 a 20 días; 30 % de OG (municipalidades y comisiones municipales, sin repetir departamento) con tipo «Otra», porque el sistema de Desarrollo no tiene un tipo para ellas, y el resto ONG («Asociación Civil» y «Cooperativa») |
| `[E3]` | Usuarios | 6 técnicos, 2 operadores, 1 arquitecto y 1 administrador, con nombre y apellido; presidente y tesorero de cada organización con usuario `INTEGRANTE`, sin nombre ni apellido (como los crea el alta); de 0 a 3 integrantes más sin usuario |
| `[E4]` | Duración real de una etapa | días estimados × factor log-normal (mediana 1,2; desvío 0,35), en días hábiles, mínimo 1 |
| `[E5]` | Observación de un envío | 0,25 por ronda; a lo sumo 3 rondas |
| `[E6]` | Corrección tras una observación | 1 a 3 días hábiles |
| `[E7]` | Prórroga cuando la etapa se va a vencer | probabilidad 0,35, a lo sumo una por etapa; agrega 2 a 6 días hábiles; después de la prórroga se pueden seguir subiendo fotos, pero no borrarlas |
| `[E8]` | Espera de la revisión del técnico | 0 a 4 días hábiles |
| `[E9]` | Carga sin conexión | envíos y fotos de etapa que llegan 1 a 5 días después (más 0 a 10 horas): 20 % de las rondas en Capital y Banda, 50 % en el resto |
| `[E10]` | Error de Java en etapas prorrogadas | desactivado, como en el sistema de Desarrollo desde el 31/10/2026; activado reproduce el comportamiento anterior: una etapa prorrogada no puede enviarse y queda trabada |
| `[E11]` | Solicitudes que no llegan a obra | 25 % (100): pendientes, semiaprobadas, rechazadas o aprobadas sin iniciar, por partes iguales |
| `[E12]` | Familias | 1 a 8 familiares; antigüedad del rancho de 5 a 40 años |
| `[E13]` | Trámite de la solicitud | expediente a los 2 a 15 días; visita inicial a los 3 a 30 días del registro; 30 % semiaprobadas, con corrección en 3 a 20 días; aprobación 5 a 45 días después de la visita; obra iniciada 0 a 9 días después de aprobada |
| `[E14]` | Documentos de familia | 5 a 7 al registrar la solicitud; el 20 % se marca para corregir y se reemplaza en 2 a 10 días |
| `[E15]` | Vivienda | el arquitecto la completa en el 70 % de los casos, 1 a 20 días después de aprobada; tipo `URBANA` 45 %, `RURAL` 45 %, `ECONOMICA` 10 %; 40 a 60 m²; 2 o 3 dormitorios |
| `[E16]` | Visitas de obra | ninguna, como en el flujo nuevo; un parámetro las activa (una por etapa aprobada) |
| `[E17]` | Fotos de etapa | 2 a 6 por ronda; en el 10 % de las rondas con conexión se borra una antes de enviar; en el 5 % de las rondas se envía sin fotos |
| `[E18]` | Avance físico real | crece en línea recta con los días hábiles de cada etapa, desde que se activa hasta su primer envío real |
| `[E19]` | Técnico asignado | el arquitecto lo asigna 1 a 10 días después del registro y siempre antes de la visita inicial, que hace ese técnico; de las solicitudes que quedan pendientes sin visita, la mitad ya tiene técnico. Con el parámetro apagado no se asigna ninguno y ninguna solicitud pasa de pendiente (sin técnico asignado, el sistema de Desarrollo no deja hacer la visita ni iniciar la obra) |
| `[E20]` | Visita inicial | clasificación con pesos inventados (la más frecuente, `TIPO_2A`, 20 %); habitantes = familiares ± 1; prioridad social 30 %; 2 a 5 fotos |
| `[E21]` | Textos | motivos y observaciones de listas fijas inventadas; la organización deja un texto en el 50 % de los envíos |
| `[E22]` | Ubicación | el 70 % de las solicitudes en el departamento de la organización; coordenadas alrededor de la cabecera (desvío 0,05°) dentro de la provincia |
| `[E23]` | Rechazo de etapa | probabilidad 0 en cada revisión, porque hoy nadie puede rechazar una etapa en el sistema de Desarrollo; con un valor mayor, el técnico rechaza en vez de aprobar u observar y la obra se detiene ahí |
| `[E24]` | Notificaciones | se guardan como en el sistema de Desarrollo: una por integrante activo con usuario (inicio de obra, aprobación, observación, prórroga y rechazo) y una para el técnico asignado (envío), con la hora de llegada más un desfase de 0 horas (3 sirve para probar un servidor en hora UTC), sin marcar como leídas |
| `[S15]` | Departamentos | los 18 departamentos de Santiago del Estero con su cabecera, sus coordenadas y su peso de población, del simulador de PP2 |

## 8. Lo que no modela

- No reasigna técnicos: el que asigna el arquitecto hace la visita, inicia la obra y revisa todas sus etapas.
- No rechaza etapas por defecto ([E23]), porque hoy nadie puede hacerlo en el sistema de Desarrollo.
- Nadie lee las notificaciones: quedan todas sin leer.
- El calendario del simulador no cuenta feriados, como Java hoy.
- A lo sumo una prórroga por etapa.
- Las visitas iniciales no tienen demora de conexión (guardan la hora del celular, como en Java).
- Lo que se borra en el celular sin conexión nunca llega al servidor, así que no se ve.
- Las personas, los CUIT, las direcciones y los textos son inventados: no describen el programa real.
