"""
Scraper de Tasas Referenciales del BCE - Banco Guayaquil.

Descarga el HTML del portal del BCE (vía requests), extrae las tablas
clave-valor con BeautifulSoup y arma los DataFrames finales:

- df_tasas_maximas : SEGMENTO_CREDITO, TASA_EFECTIVA_MAXIMA, TASA_REFERENCIAL, PERIODO
- df_otras_tasas   : TASAS_REFERENCIALES, TASA_PORCENTUAL, CATEGORIA, PERIODO

La carga a BD y las notificaciones se orquestan desde main.py.
"""

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from config.settings import SOURCE_URL
from src.scraper.http_client import obtener_html
from src.transform.cleaners import (
    convertir_a_aaaamm,
    limpiar_texto_df,
    normalizar_columnas,
)
from src.utils.logger import LOGGER



# ---------------------------------------------------------------------------
# Extracción de tablas crudas
# ---------------------------------------------------------------------------
def _extraer_tabla_clave_valor(table) -> pd.DataFrame:
    """Convierte una tabla HTML clave-valor (con celdas colspan>=3) en DataFrame."""
    data = []
    current_key = None
    values: list = []

    for td in table.find_all("td"):
        colspan = td.get("colspan")
        text = td.get_text(strip=True)

        if colspan and int(colspan) >= 3:
            if current_key is not None:
                data.append([current_key] + values)
            current_key = text
            values = []
        else:
            if current_key is not None:
                val = text.replace(".", "").replace(",", ".")
                try:
                    val = float(val)
                except ValueError:
                    pass
                values.append(val)

    if current_key is not None:
        data.append([current_key] + values)

    if not data:
        return pd.DataFrame()

    max_cols = max(len(row) for row in data)
    columns = ["Concepto"] + [f"Valor{i}" for i in range(1, max_cols)]
    # Rellenar filas cortas para que todas tengan max_cols
    data = [row + [np.nan] * (max_cols - len(row)) for row in data]
    return pd.DataFrame(data, columns=columns)


def obtener_tablas(url: str = SOURCE_URL) -> dict[str, pd.DataFrame]:
    """Descarga el HTML y retorna las tablas clave-valor detectadas."""
    html = obtener_html(url)
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    LOGGER.info("Se encontraron %d tablas en la página.", len(tables))

    extraidas: dict[str, pd.DataFrame] = {}
    contador = 0
    for i, table in enumerate(tables):
        tds = table.find_all("td")
        tiene_colspan = any(
            td.get("colspan") and int(td.get("colspan")) >= 3 for td in tds
        )
        if not tiene_colspan:
            continue
        df = _extraer_tabla_clave_valor(table)
        if df.empty:
            continue
        contador += 1
        clave = f"tabla_extraida_{contador}_indice_{i}"
        extraidas[clave] = df
        LOGGER.info("Tabla clave-valor extraída: %s (%d filas)", clave, len(df))

    LOGGER.info("Total de tablas clave-valor extraídas: %d", len(extraidas))
    return extraidas


# ---------------------------------------------------------------------------
# Transformaciones específicas
# ---------------------------------------------------------------------------
def _pares_desde_fila(fila, palabra_clave: str) -> pd.DataFrame:
    """Reconstruye pares (Tasa, Valor) a partir de una fila aplanada."""
    valores = fila.values.flatten().tolist()
    limpios = []
    for v in valores:
        if isinstance(v, (int, float, np.float64)) and not (
            isinstance(v, float) and np.isnan(v)
        ):
            limpios.append(v)
        elif isinstance(v, str) and palabra_clave in v:
            limpios.append(v.strip().replace("\r\n", " "))

    pares = [(limpios[i], limpios[i + 1]) for i in range(0, len(limpios) - 1, 2)]
    df = pd.DataFrame(pares, columns=["Tasa", "Valor"])
    df["Valor"] = df["Valor"].astype(float).round(2)
    return df


def construir_otras_tasas(tablas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Arma el DataFrame de 'OTRAS TASAS' + 'TASAS POR PLAZO'."""
    tabla_ref = tablas["tabla_extraida_2_indice_1"]

    df_otras = _pares_desde_fila(tabla_ref.iloc[23], "Tasa")
    df_otras["Categoria"] = "OTRAS TASAS"

    df_plazo = _pares_desde_fila(tabla_ref.iloc[22], "Plazo")
    df_plazo["Categoria"] = "TASAS POR PLAZO"

    return pd.concat([df_plazo, df_otras], ignore_index=True)


def construir_tasas_maximas(tablas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Arma el DataFrame de tasas activas máximas + referenciales por segmento."""
    df_activas_raw = tablas["tabla_extraida_1_indice_0"].iloc[:, :2]
    df_referenciales_raw = tablas["tabla_extraida_2_indice_1"].iloc[:, :2]

    # Activas: cabecera real en fila 3, datos desde fila 5
    df_activas = df_activas_raw.iloc[5:].copy()
    df_activas.columns = df_activas_raw.iloc[3]
    df_activas.reset_index(drop=True, inplace=True)

    # Referenciales: cabecera real en fila 4, datos desde fila 6
    df_referenciales = df_referenciales_raw.iloc[6:, :2].copy()
    df_referenciales.columns = df_referenciales_raw.iloc[4, :2]
    df_referenciales.reset_index(drop=True, inplace=True)

    # Quedarse solo con filas que tengan tasa numérica
    df_activas["% anual"] = pd.to_numeric(df_activas["% anual"], errors="coerce")
    df_activas = df_activas[df_activas["% anual"].notna()].copy()

    df_referenciales["% anual"] = pd.to_numeric(
        df_referenciales["% anual"], errors="coerce"
    )
    df_referenciales = df_referenciales[df_referenciales["% anual"].notna()].copy()

    # Limpieza de texto y normalización de columnas
    df_activas = normalizar_columnas(limpiar_texto_df(df_activas))
    df_referenciales = normalizar_columnas(limpiar_texto_df(df_referenciales))

    # Renombrar a nombres estándar de destino
    df_activas = df_activas.rename(
        columns={
            df_activas.columns[0]: "SEGMENTO",
            "ANUAL": "TASA_EFECTIVA_MAXIMA",
        }
    )
    df_referenciales = df_referenciales.rename(
        columns={
            df_referenciales.columns[0]: "SEGMENTO_CREDITO",
            "ANUAL": "TASA_REFERENCIAL",
        }
    )

    df1 = df_activas[["SEGMENTO", "TASA_EFECTIVA_MAXIMA"]]
    df2 = df_referenciales[["SEGMENTO_CREDITO", "TASA_REFERENCIAL"]]
    df_merged = pd.merge(
        df1, df2, left_on="SEGMENTO", right_on="SEGMENTO_CREDITO", how="inner"
    ).drop(columns=["SEGMENTO"])

    cols = ["SEGMENTO_CREDITO"] + [
        c for c in df_merged.columns if c != "SEGMENTO_CREDITO"
    ]
    return df_merged[cols]


def asignar_periodo(
    df_maximas: pd.DataFrame,
    df_otras: pd.DataFrame,
    tablas: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula el PERIODO (AAAAMM) desde la cabecera y lo aplica a ambos DataFrames."""
    df_periodo = tablas["tabla_extraida_1_indice_0"].iloc[:1, :1]
    valor_periodo = df_periodo["Concepto"].iloc[0]
    periodo = int(convertir_a_aaaamm(valor_periodo))
    LOGGER.info("Periodo detectado: %s -> %d", valor_periodo, periodo)

    df_maximas = df_maximas.copy()
    df_otras = df_otras.copy()
    df_maximas["PERIODO"] = periodo
    df_otras["PERIODO"] = periodo
    return df_maximas, df_otras


def normalizar_otras_a_destino(df_otras: pd.DataFrame) -> pd.DataFrame:
    """Renombra columnas de 'otras tasas' a los nombres de la tabla destino."""
    return df_otras.rename(
        columns={
            "Tasa": "TASAS_REFERENCIALES",
            "Valor": "TASA_PORCENTUAL",
            "Categoria": "CATEGORIA",
        }
    )


# ---------------------------------------------------------------------------
# Orquestación de la extracción completa
# ---------------------------------------------------------------------------
def ejecutar_scraping() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Ejecuta el flujo completo de extracción y transformación.
    Retorna (df_tasas_maximas, df_otras_tasas) listos para cargar.
    """
    tablas = obtener_tablas()

    df_maximas = construir_tasas_maximas(tablas)
    df_otras = construir_otras_tasas(tablas)
    df_otras = limpiar_texto_df(df_otras)
    df_maximas, df_otras = asignar_periodo(df_maximas, df_otras, tablas)
    df_otras = normalizar_otras_a_destino(df_otras)

    LOGGER.info(
        "Scraping completo -> máximas: %d filas | otras: %d filas",
        len(df_maximas),
        len(df_otras),
    )
    return df_maximas, df_otras
