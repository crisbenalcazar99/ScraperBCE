"""
Punto de entrada del scraper de Tasas Referenciales del BCE - Banco Guayaquil.
Ejecuta el scraping (extracción + transformación) y carga los resultados a
la base de datos solo si hay un periodo más reciente.
"""
from src.scraper.tasas_max_referenciales import ejecutar_scraping
from src.utils.logger import LOGGER, resumen_errores
from src.database.operations import cargar_si_hay_periodo_nuevo
from src.utils.notifications import notificar_exito, notificar_error
from src.utils.logger import registrar_error_no_critico
from config import settings


def main() -> None:
    LOGGER.info("=== Inicio scraper Tasas Referenciales ===")
    try:
        df_maximas, df_otras = ejecutar_scraping()

        LOGGER.info("Tasas máximas referenciales: %d filas", len(df_maximas))
        print("\n=== TASAS MÁXIMAS REFERENCIALES ===")
        print(df_maximas.to_string(index=False))

        LOGGER.info("Otras tasas: %d filas", len(df_otras))
        print("\n=== OTRAS TASAS ===")
        print(df_otras.to_string(index=False))

        # --- Carga a base de datos ---
        cargado_maximas = cargar_si_hay_periodo_nuevo(
            df_maximas,
            tabla=settings.TABLA_TASAS_MAXIMAS,
            schema=settings.DB_SCHEMA,
            periodo_base=settings.PERIODO_BASE,
        )
        cargado_otras = cargar_si_hay_periodo_nuevo(
            df_otras,
            tabla=settings.TABLA_OTRAS_TASAS,
            schema=settings.DB_SCHEMA,
            periodo_base=settings.PERIODO_BASE,
        )

        if cargado_maximas or cargado_otras:
            LOGGER.info("Carga completada. Enviando notificación de éxito.")
            notificar_exito(
                registros_maximas=cargado_maximas,
                periodo_maximas=int(df_maximas["PERIODO"].iloc[0]),
                registros_otras=cargado_otras,
                periodo_otras=int(df_otras["PERIODO"].iloc[0]),
            )
        else:
            LOGGER.info("No hubo periodo nuevo; no se cargó nada.")
    except Exception as exc:
        LOGGER.exception("Error crítico en la ejecución del scraper")
        registrar_error_no_critico(str(exc))
        notificar_error(f"{type(exc).__name__}: {exc}")
    finally:
        resumen_errores()


if __name__ == "__main__":
    main()
