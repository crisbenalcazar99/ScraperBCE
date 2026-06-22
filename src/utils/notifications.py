"""
Notificaciones - Banco Guayaquil.

Tres canales de notificación al finalizar la carga:
- Teams   : MessageCard vía Incoming Webhook (_enviar_card)
- SMTP    : correo directo vía servidor SMTP (_enviar_correo)
- BD cola : inserta fila en dbo.t_cola_mensajes (_encolar_correo)
"""
from datetime import datetime
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

import pandas as pd

from config.settings import (
    EQUIPO_RESPONSABLE,
    TABLA_OTRAS_TASAS,
    TABLA_TASAS_MAXIMAS,
    CORREO_NOTIFICAR,
    TEAMS_NOTIFICAR,
    TEAMS_WEBHOOK_URL,
    TIMEOUT_SEG,
    SMTP_DESTINATARIOS,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_REMITENTE,
    SMTP_USAR_TLS,
    SMTP_USUARIO,
    SMTP_PASSWORD,
    COLA_CORREO_NOTIFICAR,
    COLA_CORREO_NOMBRE_PERSONA,
    COLA_CORREO_USUARIO_PERSONA,
)
from src.database.connections import engine
from src.utils.logger import LOGGER


def _enviar_card(titulo: str, color: str, hechos: list[dict], texto: str) -> bool:
    if not TEAMS_NOTIFICAR:
        LOGGER.info("Notificaciones Teams desactivadas (TEAMS_NOTIFICAR=False).")
        return False

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": titulo,
        "sections": [
            {
                "activityTitle": titulo,
                "activitySubtitle": EQUIPO_RESPONSABLE,
                "facts": hechos,
                "text": texto,
                "markdown": True,
            }
        ],
    }

    try:
        LOGGER.info("Intento de Envio de Notificaciones")
        resp = requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=TIMEOUT_SEG)
        resp.raise_for_status()
        LOGGER.info("Notificación Teams enviada: %s", titulo)
        return True
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("No se pudo enviar notificación a Teams: %s", exc)
        return False


def _construir_html(titulo: str, color: str, hechos: list[dict], texto: str) -> str:
    """Genera el cuerpo HTML del correo a partir de los hechos."""
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
      <p style="margin:0 0 16px 0;color:#666;font-size:13px;">{EQUIPO_RESPONSABLE}</p>
      <p style="margin:0 0 16px 0;">{texto}</p>
      <table style="border-collapse:collapse;width:100%;font-size:14px;">
        {filas}
      </table>
    </div>
  </body>
</html>"""


def _enviar_correo(titulo: str, color: str, hechos: list[dict], texto: str) -> bool:
    if not CORREO_NOTIFICAR:
        LOGGER.info("Notificaciones por correo desactivadas (CORREO_NOTIFICAR=False).")
        return False

    msg = MIMEMultipart("alternative")
    # El asunto suele llevar texto plano; quitamos posibles emojis si tu MTA los rechaza.
    msg["Subject"] = titulo
    msg["From"] = SMTP_REMITENTE
    msg["To"] = ", ".join(SMTP_DESTINATARIOS)

    cuerpo_html = _construir_html(titulo, color, hechos, texto)
    msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

    try:
        LOGGER.info("Intento de Envio de Notificaciones por correo")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT_SEG) as server:
            if SMTP_USAR_TLS:
                server.starttls()
            if SMTP_USUARIO and SMTP_PASSWORD:
                server.login(SMTP_USUARIO, SMTP_PASSWORD)
            server.send_message(msg)
        LOGGER.info("Notificación por correo enviada: %s", titulo)
        return True
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("No se pudo enviar notificación por correo: %s", exc)
        return False


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
            name="t_cola_mensajes",
            con=engine,
            if_exists="append",
            index=False,
            schema="dbo",
            chunksize=1,
        )
        LOGGER.info("Correo encolado en t_cola_mensajes: %s", titulo)
        return True
    except Exception as exc:
        LOGGER.warning("No se pudo encolar correo en t_cola_mensajes: %s", exc)
        return False


def notificar_exito(
    registros_maximas: int,
    periodo_maximas: int,
    registros_otras: int,
    periodo_otras: int,
) -> bool:
    """Notifica a Teams una carga exitosa de las tablas de tasas."""
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

    _enviar_correo(
        titulo="✅ Tasas Referenciales actualizadas",
        color="2EB67D",
        hechos=hechos,
        texto="La carga de tasas referenciales del BCE finalizó correctamente.",
    )
    _encolar_correo(
        titulo="✅ Tasas Referenciales actualizadas",
        color="2EB67D",
        hechos=hechos,
        texto="La carga de tasas referenciales del BCE finalizó correctamente.",
    )
    return _enviar_card(
        titulo="✅ Tasas Referenciales actualizadas",
        color="2EB67D",
        hechos=hechos,
        texto="La carga de tasas referenciales del BCE finalizó correctamente.",
    )


def notificar_error(mensaje: str) -> bool:
    """Notifica a Teams un error crítico de ejecución."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hechos = [
        {"name": "Fecha", "value": ahora},
        {"name": "Detalle", "value": mensaje[:500]},
    ]
    _enviar_correo(
        titulo="❌ Tasas Referenciales: error de ejecución",
        color="E01E5A",
        hechos=hechos,
        texto="Ocurrió un error durante la ejecución del scraper.",
    )
    _encolar_correo(
        titulo="❌ Tasas Referenciales: error de ejecución",
        color="E01E5A",
        hechos=hechos,
        texto="Ocurrió un error durante la ejecución del scraper.",
    )
    return _enviar_card(
        titulo="❌ Tasas Referenciales: error de ejecución",
        color="E01E5A",
        hechos=hechos,
        texto="Ocurrió un error durante la ejecución del scraper.",
    )
