# tasas_referenciales

Scraper de **Tasas Referenciales del BCE** — Data Engineering, Banco Guayaquil.

Extrae las tablas de tasas de interés publicadas por el Banco Central del Ecuador,
las transforma al formato estándar y las carga de forma incremental por periodo en
SQL Server. Notifica el resultado mediante la cola de correos interna.

---

## Fuente

`https://contenido.bce.fin.ec/documentos/Estadisticas/SectorMonFin/TasasInteres/Indice.htm`

---

## Tablas destino

Todas en la base `DN_STAGING`, schema configurado en `DB_SCHEMA` (`settings.py`).

| Tabla | Contenido |
|---|---|
| `ISC_VIZ_MK_TASAS_MAXIMAS_REFERENCIALES` | Tasa efectiva máxima + referencial por segmento |
| `ISC_VIZ_OTRAS_TASAS_REFERENCIALES` | Otras tasas y tasas por plazo |

La carga es **incremental**: solo inserta si el `PERIODO` (formato AAAAMM) publicado
por el BCE supera el máximo ya presente en la tabla destino.

---

## Estructura

```
tasas_referenciales/
├── README.md
├── requirements.txt
├── main.py                          # Orquestador principal
├── config/
│   └── settings.py                  # Única fuente de configuración
└── src/
    ├── database/
    │   ├── connections.py            # Engine SQLAlchemy (único punto de conexión)
    │   └── operations.py            # Lógica de lectura/escritura en BD
    ├── scraper/
    │   ├── http_client.py           # Descarga HTTP con reintentos y rotación de user-agents
    │   └── tasas_max_referenciales.py  # Extracción y transformación de tablas BCE
    ├── transform/
    │   └── cleaners.py              # Normalización de columnas y limpieza de texto
    └── utils/
        ├── logger.py                # Logger con resumen de métricas al final
        └── notifications.py         # Notificaciones vía cola de correos (t_cola_mensajes)
```

---

## Configuración

Editar `config/settings.py`:

| Variable | Descripción |
|---|---|
| `DRIVER` | Driver ODBC para SQL Server |
| `SERVERNAME` | Host y puerto del servidor SQL Server |
| `DB` | Nombre de la base de datos |
| `DB_SCHEMA` | Schema destino de todas las tablas |
| `TABLA_TASAS_MAXIMAS` | Nombre de la tabla de tasas máximas |
| `TABLA_OTRAS_TASAS` | Nombre de la tabla de otras tasas |
| `TABLA_COLA_MENSAJES` | Tabla de cola de correos para notificaciones |
| `PERIODO_BASE` | Periodo mínimo (AAAAMM) cuando la tabla está vacía |
| `COLA_CORREO_NOTIFICAR` | Activar/desactivar notificaciones (`True`/`False`) |
| `COLA_CORREO_NOMBRE_PERSONA` | Nombre del destinatario en la cola |
| `COLA_CORREO_USUARIO_PERSONA` | Usuario(s) destinatario(s), separados por `&` |
| `VERIFY_SSL` | `False` requerido por el portal BCE (certificado TLS inválido) |
| `NUMERO_INTENTOS_MAX` | Reintentos de descarga HTTP |
| `TIMEOUT_SEG` | Timeout en segundos para cada petición HTTP |

---

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecución

```bash
python main.py
```

---

## Flujo de ejecución

```
main.py
  │
  ├─ ejecutar_scraping()          ← descarga HTML del BCE y extrae DataFrames
  │     ├─ obtener_html()         ← HTTP con reintentos
  │     ├─ construir_tasas_maximas()
  │     ├─ construir_otras_tasas()
  │     └─ asignar_periodo()      ← PERIODO (AAAAMM) desde cabecera de la página
  │
  ├─ cargar_si_hay_periodo_nuevo()   ← por cada tabla
  │     ├─ obtener_max_periodo()     ← consulta MAX(PERIODO) en BD
  │     └─ crear_y_cargar()         ← solo si hay periodo nuevo
  │           ├─ crear_tabla_si_no_existe()
  │           └─ insertar_en_chunks()  ← pandas to_sql vía SQLAlchemy
  │
  ├─ notificar_exito()   ← si se insertó algo
  └─ notificar_error()   ← si ocurrió cualquier excepción
```

---

## Notificaciones

Al finalizar se inserta una fila en `t_cola_mensajes` (`DB_SCHEMA`):

- **Éxito**: registros y periodo cargados por tabla.
- **Error**: tipo de excepción y detalle del fallo.

Controlado con `COLA_CORREO_NOTIFICAR` en `settings.py`. Si está en `False`, no se encola nada pero el proceso sigue ejecutándose.

---

## Notas

- El portal del BCE requiere `VERIFY_SSL = False` por su certificado TLS; configurado en `settings.py`.
- La conexión a SQL Server usa Windows Authentication (sin credenciales en código).
- La inferencia de tipos SQL para tablas nuevas usa DuckDB; si no está disponible, cae a pandas como alternativa.