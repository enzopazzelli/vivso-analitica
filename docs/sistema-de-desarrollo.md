# El sistema de Desarrollo que leemos

Este documento describe el sistema que construye el equipo de Desarrollo y que este servicio lee: quién hace qué,
por qué estados pasa cada cosa, qué tablas guarda y qué huecos tiene para el análisis. Todo lo que dice sale de su
código y de lo que nos respondieron; el servicio copia de ahí el dominio en vez de inventarlo.

## 1. Qué es

- **Repositorio:** `PaganiB/vivso`, rama `develop`, revisada el 04/11/2026 (último commit `5b36d7d`, del 03/11/2026).
  Ese mismo día la rama `main` quedó casi vacía (se borraron sus carpetas a mano), así que la referencia es `develop`.
- **Tecnología:** Java 17, Spring Boot y JPA. La base es MySQL (`vivso3`), administrada en Aiven. El esquema lo genera
  Hibernate con `ddl-auto=update`: agrega columnas pero nunca las borra.
- **Enums:** se guardan como texto (`EnumType.STRING`), así que la base tiene el nombre del enum (`ETAPA_1`, `TIPO_1A`)
  y la API devuelve su valor (`"1a"`).
- **Zona horaria:** `America/Argentina/Buenos_Aires` en las etapas y las fotos (ver el punto 7.10).
- **Auditoría de JPA** activa (`@EnableJpaAuditing`).

```mermaid
flowchart LR
    personas["Organizaciones, operadores,<br/>arquitecto y técnicos"] --> web
    subgraph desarrollo["Sistema de Desarrollo (PaganiB/vivso)"]
        web["Web y app móvil"] --> java["Backend Java<br/>Spring Boot"]
        java --> base[("vivso3<br/>MySQL en Aiven")]
    end
    base -->|"usuario lector, solo lectura"| servicio["vivso-analitica"]
    simulador["Origen simulado<br/>mismas tablas y reglas"] -.->|"mientras no haya acceso"| servicio
    servicio --> api["API /v1"]
    servicio --> tablero["Tablero"]
    api -->|"con clave"| java
```

## 2. Roles

| Rol | Qué hace |
| :--- | :--- |
| `ADMIN` | Todo, incluido borrar |
| `OPERADOR` | Asigna el expediente; aprueba, semiaprueba y rechaza solicitudes; aprueba, observa y rechaza altas de organización; marca documentos para corregir |
| `ARQUITECTO` | Completa los datos de la vivienda; asigna el técnico de cada solicitud, mientras no tenga visita inicial |
| `TECNICO` | Solo en las solicitudes que tiene asignadas: hace la visita inicial, inicia la obra, aprueba, observa, prorroga y rechaza etapas |
| `INTEGRANTE` | Registra solicitudes de familias, confirma correcciones, reemplaza documentos, sube las fotos de las etapas y las envía a revisión |

## 3. Flujos

### 3.1 Alta de organización

Una organización pide el alta con un formulario público: queda una solicitud de organización `Pendiente` con
`fechaSolicitud` y sus documentos en `PENDIENTE`. El operador puede observarla (`SemiAprobada`, con un motivo, los
campos observados y los documentos a corregir), y la organización corrige con un enlace de edición. Al aprobarla se crea
la organización, y el presidente y el tesorero quedan como integrantes activos, cada uno con un usuario `INTEGRANTE`
(`username` = `nombre.apellido`). Al rechazarla, sus documentos quedan `RECHAZADO`: se borra el archivo, la fila queda.

```mermaid
stateDiagram-v2
    [*] --> Pendiente: registrar_alta (formulario público, 10 documentos)
    Pendiente --> SemiAprobada: observar_alta (operador marca documentos A_CORREGIR)
    SemiAprobada --> Pendiente: corregir_alta (la organización, con el token)
    Pendiente --> Aprobada: aprobar_alta (crea la organización y al presidente y tesorero con usuario)
    SemiAprobada --> Aprobada: aprobar_alta
    Pendiente --> Rechazada: rechazar_alta (documentos RECHAZADO)
    SemiAprobada --> Rechazada: rechazar_alta
    Aprobada --> [*]
    Rechazada --> [*]
    note right of Rechazada
        el cuit es único en la tabla:
        no puede volver a pedir el alta
    end note
```

### 3.2 Solicitud de vivienda

Un integrante registra a la familia, sus familiares y sus documentos: la solicitud queda `Pendiente`. El operador le
asigna el número de expediente, que es obligatorio para aprobar. **El arquitecto le asigna un técnico** (desde el
27/10/2026): tiene que ser un usuario con rol de técnico, y solo se puede asignar o cambiar mientras la solicitud no
tenga visita inicial. Puede semiaprobarla (`SemiAprobada`, con una
observación y los campos observados); el integrante confirma la corrección cuando no quedan documentos para corregir, y
la solicitud vuelve a `Pendiente` sin la observación. Al aprobarla se guarda `fechaActivacion` y el revisor, y se crea
la vivienda **vacía**: solo con la familia y la solicitud. Java solo impide aprobar una solicitud ya aprobada.

```mermaid
stateDiagram-v2
    [*] --> Pendiente: registrar_solicitud (integrante, familia y documentos)
    Pendiente --> Pendiente: asignar_expediente (operador)
    Pendiente --> Pendiente: asignar_tecnico (arquitecto, antes de la visita)
    Pendiente --> SemiAprobada: semiaprobar_solicitud (operador)
    SemiAprobada --> Pendiente: confirmar_correccion (sin documentos A_CORREGIR)
    Pendiente --> Aprobada: aprobar_solicitud (exige num_exp y crea la vivienda vacía)
    SemiAprobada --> Aprobada: aprobar_solicitud
    Pendiente --> Rechazada: rechazar_solicitud
    SemiAprobada --> Rechazada: rechazar_solicitud
    Rechazada --> Aprobada: aprobar_solicitud (Java no lo impide)
    Aprobada --> [*]
```

### 3.3 Vivienda

El arquitecto completa departamento, localidad, dirección, barrio, superficie, tipo, dormitorios y coordenadas. El
tipo (`URBANA`, `RURAL`, `ECONOMICA`) es el **prototipo**: define el presupuesto y los planos, no la ubicación.
`fechaInic` y `fechaFin` no las completa ningún flujo.

### 3.4 Documentos

```mermaid
stateDiagram-v2
    [*] --> PENDIENTE: subir (fecha_subida)
    PENDIENTE --> A_CORREGIR: marcar (operador, motivo y fecha_revision)
    A_CORREGIR --> PENDIENTE: reemplazar (borra motivo y revisor, la fecha queda)
    PENDIENTE --> APROBADO: aprobar_alta
    PENDIENTE --> RECHAZADO: rechazar_alta
    A_CORREGIR --> RECHAZADO: rechazar_alta
    note right of RECHAZADO
        se borra el archivo,
        la fila queda
    end note
```

`APROBADO` y `RECHAZADO` solo existen en el alta de organizaciones. Hay 19 tipos de documento: 10 de la organización,
7 de la familia (entre ellos el certificado de discapacidad), la foto de avance de obra y «otro».

### 3.5 Visita inicial

La hace **el técnico asignado** a la solicitud (otro técnico no puede registrarla) con la app y el GPS: clasificación
preliminar, coordenadas, localidad, departamento, observaciones, habitantes encontrados, prioridad social y fotos. Es la
única fecha que viene del celular. Después de la visita, el técnico asignado ya no se puede cambiar.

```mermaid
sequenceDiagram
    participant A as Arquitecto
    participant T as Técnico (app con GPS)
    participant J as Backend Java
    A->>J: asigna el técnico a la solicitud
    T->>J: visita inicial con clasificación, coordenadas, habitantes, prioridad social y fotos
    Note right of J: solo el técnico asignado,<br/>fecha_visita es la hora del celular
    J-->>T: visita registrada
```

### 3.6 Etapas de obra

Las organizaciones registran el avance y el técnico lo aprueba a distancia, con las fotos (los técnicos a veces no dan
abasto para ir). El técnico inicia la obra cuando la solicitud está aprobada: se crean las 6 etapas en `PENDIENTE` y se
activa la primera. Activar una etapa es ponerla `EN_CURSO` con `fecha_inicio` = hoy y `fecha_limite` =
`fecha_limite_original` = hoy más sus días hábiles estimados.

- El integrante sube fotos con la etapa `EN_CURSO`, `OBSERVADA` o `PRORROGADA` (con la hora del servidor) y puede
  borrarlas solo en `EN_CURSO` u `OBSERVADA`; el borrado no deja rastro. Desde el 22/10/2026 los archivos se guardan
  en Cloudinary.
- Enviar: desde `EN_CURSO`, `OBSERVADA` o `PRORROGADA` → `EN_REVISION`, con la hora truncada al minuto, una observación
  de la organización (que pisa la anterior) y quién la envió. (Hasta el 31/10/2026 una etapa `PRORROGADA` no se podía
  enviar y quedaba trabada; Desarrollo lo arregló.)
- Aprobar (técnico): desde `EN_REVISION` → `APROBADA`, y en el mismo momento se activa la siguiente. La última
  observación del técnico no se borra.
- Observar (técnico): desde `EN_REVISION` → `OBSERVADA`, con su observación y la fecha de revisión.
- Rechazar (técnico, nuevo): desde `EN_REVISION` → `RECHAZADA`, con el motivo y la fecha de revisión. Ninguna regla
  saca una etapa de `RECHAZADA`: la obra queda detenida (ver el punto 7.11).
- Prorrogar (técnico): desde `EN_CURSO`, `OBSERVADA`, `EN_REVISION` o `PRORROGADA`; el técnico elige la fecha nueva,
  que tiene que ser posterior a la vigente y hábil → `PRORROGADA`; pisa `fecha_limite` y el motivo. El tope de 14 días
  está declarado pero no se aplica, y no queda registrado quién prorrogó.
- Solo el **técnico asignado** a la solicitud puede iniciar la obra y aprobar, observar, prorrogar o rechazar sus
  etapas (`validarTecnicoAsignado`, sin excepción para `ADMIN`).
- Ninguna de estas acciones recibe la hora del celular: el servidor pone la suya.
- Cada una deja una **notificación** (sección 3.9).

```mermaid
stateDiagram-v2
    [*] --> PENDIENTE: iniciar_obra crea las 6
    PENDIENTE --> EN_CURSO: activar (fecha_inicio y fecha_limite de Java)
    EN_CURSO --> EN_REVISION: enviar_etapa (integrante)
    OBSERVADA --> EN_REVISION: enviar_etapa
    PRORROGADA --> EN_REVISION: enviar_etapa (desde el 31/10/2026)
    EN_REVISION --> APROBADA: aprobar_etapa (técnico, activa la siguiente)
    EN_REVISION --> OBSERVADA: observar_etapa (técnico)
    EN_REVISION --> RECHAZADA: rechazar_etapa (técnico)
    EN_CURSO --> PRORROGADA: prorrogar_etapa (técnico)
    OBSERVADA --> PRORROGADA: prorrogar_etapa
    EN_REVISION --> PRORROGADA: prorrogar_etapa
    PRORROGADA --> PRORROGADA: prorrogar_etapa
    APROBADA --> [*]
    RECHAZADA --> [*]
    note left of EN_CURSO
        fotos: se suben en EN_CURSO, OBSERVADA
        y PRORROGADA; se borran solo en
        EN_CURSO y OBSERVADA
    end note
    note right of RECHAZADA
        sin salida:
        la obra queda detenida
    end note
```

Cuando el celular no tiene señal, las fotos y el envío quedan en el teléfono y llegan juntos al reconectarse. Lo que
guarda Java es la hora de llegada:

```mermaid
sequenceDiagram
    participant O as Integrante (app)
    participant J as Backend Java
    participant T as Técnico
    Note over O: sin señal, todo queda en el celular
    O->>O: saca las fotos y envía la etapa (momento real)
    Note over O: 1 a 5 días después vuelve la señal
    O->>J: fotos en ráfaga (fecha_subida = hora de llegada)
    O->>J: enviar_etapa (fecha_envio = hora de llegada)
    J-->>T: la etapa aparece EN_REVISION
    T->>J: aprobar_etapa u observar_etapa, 0 a 4 días hábiles después
```

### 3.7 El avance de obra (AFO)

Desde el 15/10/2026 el avance de obra son las 6 etapas: la etapa en curso y las aprobadas. La web de Desarrollo lo
muestra como «Etapa N: nombre (estado)» y «Obra Finalizada» cuando las 6 están aprobadas. Java no calcula un porcentaje.
Aprobada la etapa 6, la obra está terminada; la entrega sigue con un trámite administrativo.

### 3.8 Visita de obra

Era un resto del AFO anterior: guardaba la fecha del servidor, un `progreso` de 0 a 100 en la columna `afo` y fotos
como documentos `FOTO_OBRA`. El 30/10/2026 Desarrollo la sacó del código, porque el avance lo registran las
organizaciones. La tabla puede seguir en la base (Hibernate no borra tablas), pero nada la escribe.

### 3.9 Notificaciones

Desde el 03/11/2026, cada acción sobre una etapa guarda **una notificación por destinatario** en la tabla
`notificacion`: el tipo, la solicitud (`id_referencia`), la fecha y hora, el usuario que la recibe y si la leyó. No se
borran nunca (solo se marcan como leídas). Para el análisis es la historia que el sistema no guardaba: cada envío,
observación, prórroga, aprobación y rechazo con su hora exacta.

| Acción | Tipo | Quién la recibe |
| :--- | :--- | :--- |
| Iniciar la obra | `ETAPA_HABILITADA` | cada integrante activo con usuario de la organización |
| Enviar una etapa | `ETAPA_ENVIADA` | el técnico asignado |
| Aprobar | `ETAPA_APROBADA` | cada integrante activo con usuario |
| Observar | `ETAPA_OBSERVADA` | ídem |
| Prorrogar | `ETAPA_PRORROGADA` | ídem |
| Rechazar | `ETAPA_RECHAZADA` | ídem |

Tres cosas para tener en cuenta: la notificación **no dice de qué etapa** se trata (el servicio lo deduce contando las
aprobaciones anteriores de la misma solicitud); habilitar la etapa siguiente al aprobar no genera `ETAPA_HABILITADA`; y
la hora se toma **sin zona horaria** (`LocalDateTime.now()`), así que depende de en qué zona corra el servidor (el
servicio estima la diferencia comparando cada envío notificado con su `fecha_envio`).

```mermaid
sequenceDiagram
    participant O as Integrante
    participant J as Backend Java
    participant N as Tabla notificacion
    participant T as Técnico asignado
    O->>J: enviar_etapa
    J->>N: ETAPA_ENVIADA para el técnico
    J-->>T: aviso en la app
    T->>J: aprobar_etapa
    J->>N: ETAPA_APROBADA, una por integrante activo con usuario
    J-->>O: aviso en la app
    Note over N: no se borran: quedan como historia
```

## 4. Las 6 etapas y los plazos

| N.º | Etapa | Qué incluye | Días hábiles estimados |
| ---: | :--- | :--- | ---: |
| 1 | Replanteo y cimientos | Replanteo, excavación y llenado de cimientos | 2 |
| 2 | Mampostería de cimientos | Mampostería de cimientos, encadenado inferior con tronco de columna y capa aisladora | 2 |
| 3 | Elevación y techo | Mampostería de elevación, columnas de encadenado, encadenado superior, techo completo con aislante, apretada y colocación de aberturas | 10 |
| 4 | Revoques y contrapiso | Revoque grueso y fino interior y exterior, contrapiso y carpeta de nivelación | 8 |
| 5 | Instalaciones | Instalación eléctrica, instalación sanitaria, colocación de mesada, cámaras y pozo | 5 |
| 6 | Pintura y artefactos | Pintura interior y exterior, colocación de artefactos eléctricos y sanitarios | 2 |
| | **Total** | | **29** |

```mermaid
flowchart LR
    S["Solicitud Aprobada"] -->|"iniciar_obra"| E1["Etapa 1<br/>2 días"]
    E1 -->|"aprobar"| E2["Etapa 2<br/>2 días"]
    E2 -->|"aprobar"| E3["Etapa 3<br/>10 días"]
    E3 -->|"aprobar"| E4["Etapa 4<br/>8 días"]
    E4 -->|"aprobar"| E5["Etapa 5<br/>5 días"]
    E5 -->|"aprobar"| E6["Etapa 6<br/>2 días"]
    E6 -->|"aprobar"| F["Obra finalizada"]
```

**Días hábiles** (`CalendarioService`): de lunes a viernes. Para el límite, el día de inicio no cuenta; para los días
que faltan, no cuenta hoy y sí cuenta el día del límite. El ejemplo de Java: una etapa habilitada un viernes con 2 días
vence el martes.

```mermaid
flowchart LR
    V["viernes 16/10<br/>se habilita, no cuenta"] --> S["sábado<br/>no cuenta"]
    S --> D["domingo<br/>no cuenta"]
    D --> L["lunes 19/10<br/>día 1"]
    L --> M["martes 20/10<br/>día 2 = límite"]
```

Los feriados todavía no se cuentan: están previstos con la API de ArgentinaDatos.

## 5. Las 14 tablas que leemos

El servicio pasa cada tabla a su formato (columnas en minúsculas con guion bajo). Solo cambian de nombre estas columnas;
las columnas completas de cada tabla están en [analitica/esquema.py](../analitica/esquema.py). Las 13 primeras salen del
`SHOW CREATE TABLE` que mandó Desarrollo el 19/10; la tabla `notificacion` y las columnas nuevas de `usuario` salen de su
código del 03/11 y se confirman en la primera lectura de la base real.

| Tabla de Java | Nuestra tabla | Columnas que cambian de nombre |
| :--- | :--- | :--- |
| `solicitud` | `solicitudes` | `numExp` → `num_exp`, `fechaSolicitud` → `fecha_solicitud`, `fechaActivacion` → `fecha_activacion`, `CUIT_org` → `cuit_org`, `camposObservados` → `campos_observados` |
| `familia` + `familiar` | `familias` | `id_familia`, la cantidad de familiares → `cantidad_familiares`, `antiguedadRancho` → `antiguedad_rancho`. De `familiar` solo se leen `id_familiar` e `id_familia` |
| `vivienda` | `viviendas` | `fechaInic` → `fecha_inicio`, `fechaFin` → `fecha_fin`, `tipoVivienda` → `tipo_vivienda`; `avance_obra` (resto del AFO anterior) se lee tal cual. La columna es `barrio`, sin espacio (en la entidad figura `"barrio "`) |
| `etapa_obra` | `etapas` | Sin cambios, más `numero` (del catálogo) |
| `foto_etapa` | `fotos_etapa` | `id_etapa` → `id_etapa_obra` |
| `visitaInicial` | `visitas_iniciales` | `id` → `id_visita`, `clasificacion_preliminar` → `clasificacion`, `cantHabitantesReal` → `habitantes`, `tienePrioridadSocial` → `prioridad_social` |
| `visita_fotos` | `fotos_visita` | Sin cambios (la tabla no tiene clave primaria) |
| `visitaObra` | `visitas_obra` | `id_usuario_tecnico` → `id_tecnico`. Si Desarrollo la borra, queda vacía sin error |
| `organizacion` | `organizaciones` | `CUIT` → `cuit` |
| `solicitud_organizacion` | `solicitudes_organizacion` | `domLegal` → `dom_legal`, `fechaVencimientoVigencia` → `fecha_vencimiento_vigencia`, `fechaUltimaAsamblea` → `fecha_ultima_asamblea`, los siete datos del presidente y los siete del tesorero (`dniPresidente` → `dni_presidente`, etc.), `fechaRechazo` → `fecha_rechazo`, `fechaAprobacion` → `fecha_aprobacion`, `fechaSolicitud` → `fecha_solicitud` |
| `integrante` | `integrantes` | `id_integranteOrganizacion` → `id_integrante`, `CUIT_org` → `cuit_org`, `DNI` → `dni` |
| `usuario` | `usuarios` | Sin cambios; se suman `nombre` y `apellido` (el personal los tiene, los usuarios de integrantes no) |
| `documento` | `documentos` | `idDocumento` → `id_documento`, `nombreOriginal` → `nombre_original`, `urlPath` → `url`, `motivoObservacion` → `motivo_observacion`, `fechaSubida` → `fecha_subida`, `fechaRevision` → `fecha_revision`, `id_organizacion` → `cuit_org`, `id_usuario_revisor` → `id_revisor` |
| `notificacion` | `notificaciones` | Sin cambios: `id_notificacion`, `id_usuario`, `tipo`, `id_referencia` (la solicitud), `fecha`, `leida`. El título y el mensaje no se leen (son el tipo y el número de expediente) |

**Lo que no se lee nunca:** tokens, contraseñas y sus hashes (tampoco `push_token` ni `debe_cambiar_password`, nuevas en
`usuario`). De `familia` y `familiar`, solo conteos: cuántos familiares hay y la antigüedad del rancho (no se leen las
columnas nuevas de ubicación del rancho ni el familiar de cada documento). Además, el usuario `lector` ya no puede leer
`password_hash` ni `token_edicion`.

**Detalles de la base:** corre en modo ANSI (los nombres van entre acentos graves y los textos entre comillas simples);
`activo` y `tienePrioridadSocial` son `bit(1)`; `superficie` es `decimal(10,2)`; `fecha_envio`, `fecha_revision` y
`fecha_subida` de las etapas y fotos son `datetime(6)`; `documento.fechaSubida` es `datetime`; `usuario.rol` es
`tinytext`. La tabla `visita` quedó sin uso y no se lee.

## 6. Lo que respondió Desarrollo (19/10/2026)

| Tema | Respuesta | Qué cambia en el servicio |
| :--- | :--- | :--- |
| Entorno de pruebas | Base desplegada en Aiven (MySQL administrado), funcionando. Backend y frontend sin desplegar. La app móvil funciona | El servicio lee la base de Aiven con conexión cifrada |
| Conexión | Un usuario de solo lectura, `lector`. El certificado de la autoridad y la contraseña llegan aparte | Van solo en el `.env` de cada máquina, nunca en el repositorio |
| Esquema | Nos pasaron el `SHOW CREATE TABLE` de las 13 tablas | Nombres de columna reales (sección 5) |
| Porcentaje de la visita de obra | El `progreso` de 0 a 100 queda sin uso; lo van a borrar | No se usa |
| Visitas de obra | `visitaObra` va a quedar sin efecto: el avance lo registran las organizaciones | Sin indicadores de visitas de obra ni tope de visitas; la evidencia del avance son las fotos |
| Tabla `visita` | Quedó de antes y no se usa | No se lee |
| Etapa 6 | Al aprobarla, la obra está terminada; la entrega es un trámite administrativo | «Obra terminada» = etapa 6 aprobada |
| Técnico asignado | Lo va a asignar el arquitecto; falta esa vista | Resuelto el 27/10/2026: lo asigna el arquitecto antes de la visita inicial |
| Feriados | API de ArgentinaDatos, por lo menos los nacionales. Para un feriado provincial, el técnico reasignaría la fecha sin que cuente como prórroga | El servicio cuenta feriados con la misma fuente |
| Hora de captura | Solo la visita inicial guarda la hora del celular | Envíos, fotos y revisiones tienen la hora de llegada al servidor |

## 7. Huecos que afectan a la analítica

La última columna dice cómo lo va a tratar el servicio: la historia, los indicadores y la calidad de datos llegan con
las próximas partes del trabajo.

| # | Qué pasa | Cómo lo va a tratar el servicio |
| ---: | :--- | :--- |
| 7.1 | ~~Una etapa `PRORROGADA` no puede enviarse: queda trabada~~ **Resuelto el 31/10/2026.** Las etapas que hayan quedado trabadas antes en la base de pruebas ya se pueden enviar | Una etapa prorrogada vencida cuenta como vencida desde su límite vigente |
| 7.2 | Aprobar la etapa 6 no cierra la solicitud | «Obra terminada» se toma de la etapa 6 aprobada; las obras terminadas sin cerrar se cuentan en la calidad de datos |
| 7.3 | ~~El técnico asignado no lo completa ningún flujo~~ **Resuelto el 27/10/2026:** lo asigna el arquitecto antes de la visita inicial. Java lo sigue exigiendo para la visita, el inicio de obra y cada revisión: las solicitudes cargadas antes sin técnico no pueden avanzar hasta que se lo asignen | Se informa cuántas solicitudes aprobadas no tienen técnico. El simulador lo asigna como el arquitecto, antes de la visita |
| 7.4 | `fechaInic` y `fechaFin` de la vivienda no se completan | El inicio de obra sale de la etapa 1 y el fin, de la aprobación de la etapa 6 |
| 7.5 | Los feriados todavía no se cuentan | El límite oficial es el que guarda Java; nuestros días hábiles cuentan feriados y pueden diferir cuando hay uno en el medio |
| 7.6 | No hay historial: cada ronda pisa fechas y textos; las fotos borradas no dejan rastro; las fechas de semiaprobación y de rechazo de una solicitud no se guardan | El servicio guarda versiones propias desde su primera lectura y deriva los eventos; lo anterior a esa lectura no se puede recuperar |
| 7.7 | Modo sin conexión: el envío, las fotos y la revisión de una etapa tienen la hora de llegada al servidor (solo la visita inicial guarda la del celular) | Se informa como limitación y se buscan señales de carga sin conexión (fotos en ráfaga, fuera de horario) |
| 7.8 | Restos del AFO anterior: `visitaObra.afo` y la columna `vivienda.avance_obra`, que la entidad ya no tiene pero Hibernate no borró | Se leen pero no entran en ningún cálculo |
| 7.9 | `solicitud_organizacion.cuit` es único: una organización rechazada no puede volver a pedir el alta con el mismo CUIT; y la vigencia es obligatoria en la organización pero no en la solicitud, así que aprobar un alta sin esa fecha fallaría | Se informa; no afecta los indicadores de obra |
| 7.10 | Zona horaria: las etapas y las fotos usan la hora de Buenos Aires, pero los documentos, las solicitudes, las altas y las notificaciones usan la zona por defecto de la JVM, y la conexión declara `serverTimezone=UTC` | Pregunta abierta a Desarrollo; mientras tanto se asume Buenos Aires para todo, y para las notificaciones se estima la diferencia comparándolas con `fecha_envio` |
| 7.11 | `RECHAZADA` no tiene salida (ni enviar, ni prorrogar, ni aprobar la aceptan) y hoy nadie puede rechazar: la ruta queda solo para `ADMIN` y el servicio exige que quien rechaza sea el técnico asignado | Se muestra como «rechazada» (obra detenida) y se cuenta en la calidad de datos; el simulador no rechaza etapas mientras tanto |
| 7.12 | Las notificaciones de la organización solo se guardan si tiene integrantes activos con usuario, y la del envío solo si hay técnico asignado; además no dicen de qué etapa son | Si a una obra le faltan notificaciones, su historia sale de las lecturas sucesivas; la etapa se deduce contando las aprobaciones anteriores |

## 8. Para levantar el sistema

Lo que faltaba el 21/10 ya está resuelto en `develop` (04/11/2026): hay `pom.xml`, un solo `SecurityConfig`,
`vivso.upload.dir` sale de la variable de entorno `uploaddir` y quedó un solo mapeador (`VivsoMapper.java`). No lo
compilamos: es lo que se ve en el código.
