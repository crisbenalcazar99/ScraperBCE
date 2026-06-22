"""
Funciones de limpieza y normalización - Banco Guayaquil.

Estándares del template:
- `normalizar_columnas()`  -> nombres en UPPER_SNAKE_CASE
- `limpieza_basica()`      -> retorna siempre (df_limpio, df_descartados)
- `limpiar_texto_df()`     -> normaliza acentos y caracteres raros en celdas

Campos especiales (ruc, cedula, identificacion, pasaporte) se fuerzan a texto.
"""

import re
import unicodedata

import pandas as pd


_MESES = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}


def _quitar_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _limpiar_celda(valor):
    """Normaliza espacios, caracteres no estándar y pone en mayúsculas. Conserva tildes."""
    if not isinstance(valor, str):
        return valor
    valor = re.sub(r"\s+", " ", valor)
    valor = re.sub(r"[^\w\s.,%-]", "", valor, flags=re.UNICODE)
    return valor.strip().upper()


def limpiar_texto_df(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica `_limpiar_celda` a todas las celdas de texto del DataFrame."""
    out = df.copy()
    try:
        return out.map(_limpiar_celda)
    except TypeError:
        return out.applymap(_limpiar_celda)


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte los nombres de columnas a UPPER_SNAKE_CASE.
    Quita saltos de línea, acentos, dígitos sueltos y normaliza separadores.
    """
    df = df.copy()
    nuevas = []
    for col in df.columns:
        nombre = str(col)
        nombre = nombre.replace("\r", " ").replace("\n", " ")
        nombre = _quitar_acentos(nombre)
        nombre = re.sub(r"\d+", "", nombre)          # quita números sueltos
        nombre = re.sub(r"[^\w\s]", " ", nombre)      # símbolos -> espacio
        nombre = re.sub(r"\s+", "_", nombre.strip())  # espacios -> underscore
        nombre = re.sub(r"_+", "_", nombre).strip("_")
        nuevas.append(nombre.upper())
    df.columns = nuevas
    return df


def convertir_a_aaaamm(texto: str) -> str:
    """Convierte 'Mes AAAA' (ej. 'Junio 2025') al formato AAAAMM (ej. '202506')."""
    partes = str(texto).strip().split()
    if len(partes) != 2:
        return "000000"
    mes, anio = partes
    mes_num = _MESES.get(_quitar_acentos(mes).lower(), "00")
    return f"{anio}{mes_num}"
