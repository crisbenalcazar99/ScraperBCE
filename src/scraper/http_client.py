"""
Descarga de HTML con requests - Banco Guayaquil.

Envuelta en la interfaz estándar del template (`obtener_html`) con reintentos
configurables y rotación de user-agents.
"""
import random
import time

import requests
import urllib3

from config.settings import (
    NUMERO_INTENTOS_MAX,
    TIMEOUT_SEG,
    USER_AGENTS,
    VERIFY_SSL,
)
from src.utils.logger import LOGGER

# Igual que en el script original: el portal del BCE usa un certificado que
# obliga a verify=False; se silencia la advertencia de petición insegura.
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def obtener_html(
    url: str,
    reintentos: int = NUMERO_INTENTOS_MAX,
    timeout_seg: int = TIMEOUT_SEG,
) -> str:
    """
    Descarga el HTML de `url` con requests (verify=VERIFY_SSL), rotando
    user-agents y reintentando hasta `reintentos` veces ante fallos.
    Relanza la última excepción si se agotan los intentos.
    """
    ultimo_error: Exception | None = None

    for intento in range(1, reintentos + 1):
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        LOGGER.info("Descargando HTML (intento %d/%d): %s", intento, reintentos, url)
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout_seg,
                verify=VERIFY_SSL,
            )
            response.raise_for_status()
            # El BCE declara/asume latin-1 pero el contenido real es UTF-8.
            # Forzar la detección por contenido evita el mojibake (MÃ¡xima).
            response.encoding = response.apparent_encoding
            html = response.text

            LOGGER.info("HTML descargado correctamente (%d caracteres)", len(html))
            return html
        except Exception as exc:  # noqa: BLE001
            ultimo_error = exc
            LOGGER.warning("Intento %d falló: %s", intento, exc)
            if intento < reintentos:
                espera = 2 ** intento
                LOGGER.info("Esperando %ds antes de reintentar...", espera)
                time.sleep(espera)

    LOGGER.error("Se agotaron los reintentos para %s", url)
    raise ultimo_error  # type: ignore[misc]
