"""
Logger estándar del template - Banco Guayaquil.

Expone la constante `LOGGER` (usada por operations.py y el resto del proyecto),
con salida a archivo (LOGGER_DIR) y consola. Acumula errores no críticos para
imprimir un resumen al final de la ejecución.
"""
import logging
import sys
import time
from datetime import datetime

from config.settings import LOGGER_DIR

PROJECT_NAME = "tasas_referenciales"

_errores_no_criticos: list[str] = []
_metricas: dict = {
    "tablas": [],          # nombres de tablas cargadas
    "procesados": 0,
    "cargados": 0,
    "descartados": 0,
    "inicio": time.time(), # marca de arranque
}

def registrar_carga(tabla: str, procesados: int, cargados: int) -> None:
    """Acumula métricas de una carga para el resumen final."""
    _metricas["tablas"].append(tabla)
    _metricas["procesados"] += procesados
    _metricas["cargados"] += cargados
    _metricas["descartados"] += (procesados - cargados)


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(f"scraper.{PROJECT_NAME}")
    if logger.handlers:  # evita duplicar handlers en reimportaciones
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    log_file = LOGGER_DIR / f"{PROJECT_NAME}_{datetime.now():%Y%m%d}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


# Constante estándar que importa el resto del proyecto
LOGGER = _build_logger()


def registrar_error_no_critico(mensaje: str) -> None:
    """Acumula un error que no detiene la ejecución, para el resumen final."""
    _errores_no_criticos.append(mensaje)
    LOGGER.warning("Error no crítico: %s", mensaje)


def resumen_errores() -> None:
    """Imprime el resumen de errores no críticos + la línea [RESUMEN] para run.sh."""
    duracion = time.time() - _metricas["inicio"]
    hms = time.strftime("%H:%M:%S", time.gmtime(duracion))
    tablas = ", ".join(_metricas["tablas"]) or "NINGUNA"
    metricas = (
        f'procesados={_metricas["procesados"]} '
        f'cargados={_metricas["cargados"]} '
        f'descartados={_metricas["descartados"]}'
    )

    if not _errores_no_criticos:
        LOGGER.info("RESUMEN: SIN ERRORES")
        # Línea estructurada que parsea run.sh
        LOGGER.info("[RESUMEN] | OK | %s | %s | %s", tablas, metricas, hms)
        return

    detalle = "; ".join(f"{i}. {err}" for i, err in enumerate(_errores_no_criticos, 1))
    LOGGER.warning("=" * 60)
    LOGGER.warning("RESUMEN: TIENE ERRORES (%d): %s", len(_errores_no_criticos), detalle)
    LOGGER.warning("[RESUMEN] | ERROR | %s | %s | %s | %s", tablas, metricas, hms, detalle)


