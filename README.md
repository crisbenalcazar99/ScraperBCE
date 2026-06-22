# tasas_referenciales

Scraper de **Tasas Referenciales del BCE** generado a partir de `scraper-template`
(Data Engineering — Banco Guayaquil).

Extrae las tablas de tasas de interés publicadas por el Banco Central del Ecuador,
las transforma al formato estándar y las carga de forma incremental por periodo en
SQL Server. Notifica el resultado por Microsoft Teams.

---

## Fuente

`https://contenido.bce.fin.ec/documentos/Estadisticas/SectorMonFin/TasasInteres/Indice.htm`

## Tablas destino (schema `dbo` / base `ANALYTICS`)

| Tabla                                      | Contenido                                       |
|--------------------------------------------|-------------------------------------------------|
| `ISC_VIZ_MK_TASAS_MAXIMAS_REFERENCIALES`   | Tasa efectiva máxima + referencial por segmento |
| `ISC_VIZ_OTRAS_TASAS_REFERENCIALES`        | Otras tasas y tasas por plazo                   |

La carga es **incremental**: solo inserta si el `PERIODO` (AAAAMM) publicado supera
el máximo ya presente en la tabla destino.

---

## Estructura

```
tasas_referenciales/
├── README.md
├── requirements.txt
├── main.py
├── config/
│   ├── __init__.py
│   └── settings.py
└── src/
    ├── __init__.py
    ├── database/
    │   ├── __init__.py
    │   ├── connections.py       # engine SQLAlchemy (Windows Auth)
    │   └── operations.py        # carga fast_executemany + chunks 10k + diagnóstico
    ├── scraper/
    │   ├── __init__.py
    │   ├── http_client.py       # descarga HTTP con requests + reintentos + rotación de user-agents
    │   └── tasas_referenciales.py
    ├── transform/
    │   ├── __init__.py
    │   └── cleaners.py          # normalizar_columnas / limpiar_texto_df (mayúsculas, conserva tildes)
    └── utils/
        ├── __init__.py
        ├── logger.py            # scraper.tasas_referenciales
        └── notifications.py     # Microsoft Teams (webhook)
```

---

## Instalación

```bash
pip install -r requirements.txt
```

## Configuración

Editar `config/settings.py`:

- `DB_CONNECTION_STRING` — cadena de conexión SQL Server (Windows Auth, sin credenciales en código).
- `TEAMS_WEBHOOK_URL` — webhook del canal de Teams del equipo (reemplazar valor).
- `TEAMS_NOTIFICAR` — activar/desactivar el envío de notificaciones (`True` / `False`).

## Ejecución

```bash
python main.py
```

---

## Notificaciones

Al finalizar, el scraper envía una tarjeta a Microsoft Teams:

- **Éxito**: registros y periodo cargados por tabla.
- **Sin cambios**: el periodo publicado ya estaba cargado.
- **Error**: detalle del error crítico de ejecución.

Configurable con `TEAMS_NOTIFICAR` y `TEAMS_WEBHOOK_URL` en `settings.py`.

---

## Notas

- Generado desde `scraper-template`. Es una copia independiente: no se actualiza
  automáticamente si el template cambia.
- El portal del BCE requiere `VERIFY_SSL = False` por su certificado TLS;
  controlado con `VERIFY_SSL` en `settings.py`.