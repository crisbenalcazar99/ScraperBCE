"""
Notificaciones - Banco Guayaquil.

Canal de notificación: inserta fila en la tabla de cola de mensajes.
"""
from datetime import datetime

import pandas as pd

from config.settings import (
    TABLA_OTRAS_TASAS,
    TABLA_TASAS_MAXIMAS,
    TABLA_COLA_MENSAJES,
    COLA_CORREO_NOTIFICAR,
    COLA_CORREO_NOMBRE_PERSONA,
    COLA_CORREO_USUARIO_PERSONA,
    DB_SCHEMA,
)
from src.database.connections import engine
from src.utils.logger import LOGGER


def _construir_html(titulo: str, color: str, hechos: list[dict], texto: str) -> str:
    filas = "".join(
        f"""
        <tr>
            <td style="padding:6px 12px;border:1px solid #ddd;font-weight:bold;
                       background:#f7f7f7;">{h['name']}</td>
            <td style="padding:6px 12px;border:1px solid #ddd;">{h['value']}</td>
        </tr>"""
        for h in hechos
    )
    return f"""\
<html>
  <body style="font-family:Segoe UI,Arial,sans-serif;color:#333;">
    <div style="border-left:6px solid #{color};padding:12px 20px;
                background:#fafafa;max-width:640px;">
      <h2 style="margin:0 0 4px 0;">{titulo}</h2>
      <p style="margin:0 0 16px 0;">{texto}</p>
      <table style="border-collapse:collapse;width:100%;font-size:14px;">
        {filas}
      </table>
    </div>
  </body>
</html>"""


def _encolar_correo(titulo: str, color: str, hechos: list[dict], texto: str) -> bool:
    if not COLA_CORREO_NOTIFICAR:
        LOGGER.info("Cola de correos desactivada (COLA_CORREO_NOTIFICAR=False).")
        return False

    cuerpo_html = _construir_html(titulo, color, hechos, texto)
    df_correo = pd.DataFrame({
        "nombre_persona": [COLA_CORREO_NOMBRE_PERSONA],
        "usuario_persona": [COLA_CORREO_USUARIO_PERSONA],
        "asunto_correo": [titulo],
        "cuerpo_correo": [cuerpo_html],
        "enviado": [0],
        "FECHA_INGRESO_EN_COLA": [datetime.now()],
    })
    try:
        df_correo.to_sql(
            name=TABLA_COLA_MENSAJES,
            con=engine,
            if_exists="append",
            index=False,
            schema=DB_SCHEMA,
            chunksize=1,
        )
        LOGGER.info("Correo encolado en %s: %s", TABLA_COLA_MENSAJES, titulo)
        return True
    except Exception as exc:
        LOGGER.warning("No se pudo encolar correo en %s: %s", TABLA_COLA_MENSAJES, exc)
        return False


def notificar_exito(
    registros_maximas: int,
    periodo_maximas: int,
    registros_otras: int,
    periodo_otras: int,
) -> bool:
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hechos = [
        {"name": "Tabla", "value": TABLA_TASAS_MAXIMAS},
        {"name": "Registros (máximas)", "value": f"{registros_maximas:,}"},
        {"name": "Periodo (máximas)", "value": str(periodo_maximas)},
        {"name": "Tabla", "value": TABLA_OTRAS_TASAS},
        {"name": "Registros (otras)", "value": f"{registros_otras:,}"},
        {"name": "Periodo (otras)", "value": str(periodo_otras)},
        {"name": "Fecha", "value": ahora},
    ]
    return _encolar_correo(
        titulo="Actualización exitosa: TASAS REFERENCIALES",
        color="2EB67D",
        hechos=hechos,
        texto="La carga de tasas referenciales del BCE finalizó correctamente.",
    )


def notificar_error(mensaje: str) -> bool:
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hechos = [
        {"name": "Fecha", "value": ahora},
        {"name": "Detalle", "value": mensaje[:500]},
    ]
    return _encolar_correo(
        titulo="Tasas Referenciales: error de ejecución",
        color="E01E5A",
        hechos=hechos,
        texto="Ocurrió un error durante la ejecución del scraper.",
    )