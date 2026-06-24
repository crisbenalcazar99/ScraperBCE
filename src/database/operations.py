import duckdb
import pandas as pd
from sqlalchemy import text

from src.database.connections import engine
from src.utils.logger import LOGGER, registrar_carga

CHUNK_SIZE = 10_000

# Campos que SIEMPRE son VARCHAR sin importar su contenido numérico
_CAMPOS_FORZAR_VARCHAR = {"ruc", "cedula", "identificacion", "pasaporte"}


def insertar_en_chunks(df, table_name, schema, chunk_size=CHUNK_SIZE) -> int:
    total = len(df)
    LOGGER.info("EJECUTANDO ACCIÓN: Insertando %d registros en [%s].[%s]", total, schema, table_name)
    try:
        df.to_sql(
            name=table_name,
            con=engine,
            schema=schema,
            if_exists="append",
            index=False,
            chunksize=chunk_size,
        )
        registrar_carga(table_name, procesados=total, cargados=total)
        LOGGER.info("Carga finalizada: %d registros insertados en [%s].[%s]", total, schema, table_name)
        return total
    except Exception as e:
        LOGGER.error("ERROR: No se pudo insertar en [%s].[%s]: %s", schema, table_name, e)
        raise

def crear_tabla_si_no_existe(table_name, schema):
    try:
        with engine.begin() as conn:
            existe = conn.execute(
                text("""
                    SELECT 1
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = :schema
                      AND TABLE_NAME = :table_name
                """),
                {
                    "schema": schema,
                    "table_name": table_name
                }
            ).fetchone()

            if not existe:
                return False
            else:
                LOGGER.info(
                    "EJECUTANDO: La tabla %s.%s ya existe",
                    schema,
                    table_name
                )

        return True

    except Exception as e:
        LOGGER.error(
            "ERROR: No se pudo crear/verificar la tabla %s: %s",
            table_name,
            e
        )
        return False

def crear_y_cargar(df, table_name, schema,ddl=None) -> int:
    if ddl is None:
        LOGGER.info("EJECUTANDO: Autocalculando DDL para [%s] desde el DataFrame", table_name)
        ddl = _autocalcular_ddl(df, table_name, schema)
    else:
        LOGGER.info("EJECUTANDO: Usando DDL proporcionado para [%s]", table_name)

    LOGGER.info("EJECUTANDO ACCIÓN: DDL:\n%s", ddl)

    tabla_existe = crear_tabla_si_no_existe(table_name, schema)
    if not tabla_existe:
        with engine.begin() as conn:
            conn.execute(text(ddl))
        LOGGER.info("EJECUTANDO: Tabla [%s] creada. Insertando %d registros.", table_name, len(df))
    else:
        LOGGER.info("EJECUTANDO: La tabla %s.%s ya existe. Insertando datos nuevos.", schema, table_name)
    return insertar_en_chunks(df, table_name, schema)



def obtener_max_periodo(tabla, schema, periodo_base) -> int:
    query = text(f"SELECT MAX(PERIODO) AS max_periodo FROM [{schema}].[{tabla}]")
    try:
        with engine.connect() as conn:
            resultado = conn.execute(query).scalar()
        if resultado is None:
            LOGGER.info("EJECUTANDO: Tabla %s.%s vacía; usando periodo base.", schema, tabla)
            return periodo_base
        return int(resultado)
    except Exception as e:
        LOGGER.error("ERROR: No se pudo consultar %s.%s: %s", schema, tabla, e)
        return periodo_base


def cargar_si_hay_periodo_nuevo(df, tabla, schema, periodo_base) -> int:
    if df.empty or "PERIODO" not in df.columns:
        LOGGER.info("EJECUTANDO: Sin datos o sin columna PERIODO para %s.%s", schema, tabla)
        return 0

    max_periodo_df = int(df["PERIODO"].max())
    max_periodo_db = obtener_max_periodo(tabla, schema, periodo_base)

    LOGGER.info("EJECUTANDO: %s.%s -> periodo origen=%d | periodo BD=%d", schema, tabla, max_periodo_df, max_periodo_db)

    if max_periodo_df > max_periodo_db:
        return crear_y_cargar(df, tabla, schema)

    LOGGER.info("EJECUTANDO: No hay datos nuevos para %s.%s", schema, tabla)
    return 0


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _es_campo_forzar_varchar(nombre_col):
    nombre_lower = nombre_col.lower()
    return any(k in nombre_lower for k in _CAMPOS_FORZAR_VARCHAR)


def _autocalcular_ddl(df, table_name, schema):
    try:
        con = duckdb.connect()
        con.register("_tmp_df", df)
        columnas = con.execute("PRAGMA table_info('_tmp_df')").fetchall()
        lineas = []
        for col in columnas:
            name = col[1]
            dtype = str(col[2]).upper()
            tipo_sql = _inferir_tipo_sql(con, "_tmp_df", name, dtype)
            lineas.append(f"    [{name}] {tipo_sql} NULL")
        con.close()
    except Exception:
        lineas = []
        for name in df.columns:
            dtype = str(df[name].dtype).upper()
            tipo_sql = _inferir_tipo_sql_pandas(df, name, dtype)
            lineas.append(f"    [{name}] {tipo_sql} NULL")

    ddl = f"CREATE TABLE [{schema}].[{table_name.upper()}] (\n"
    ddl += ",\n".join(lineas)
    ddl += "\n);"
    return ddl


def _inferir_tipo_sql(con, tabla, name, dtype):
    if _es_campo_forzar_varchar(name):
        res = con.execute(f'SELECT MAX(LENGTH("{name}"::VARCHAR)) FROM {tabla}').fetchone()[0]
        max_len = int(res or 0)
        return f"VARCHAR({max(max_len, 20)})" if max_len <= 4000 else "VARCHAR(MAX)"

    if "FECHA_CARGA" in name.upper() or dtype in ("TIMESTAMP", "DATETIME", "DATE"):
        return "DATETIME"

    if dtype in ("INTEGER", "BIGINT", "INT", "HUGEINT", "TINYINT", "SMALLINT"):
        stats = con.execute(f'SELECT MIN("{name}"), MAX("{name}") FROM {tabla}').fetchone()
        v_min, v_max = stats[0] or 0, stats[1] or 0
        if v_min >= 0 and v_max <= 255:                          return "TINYINT"
        if v_min >= -32_768 and v_max <= 32_767:                 return "SMALLINT"
        if v_min >= -2_147_483_648 and v_max <= 2_147_483_647:   return "INT"
        return "BIGINT"

    if any(t in dtype for t in ("DECIMAL", "DOUBLE", "FLOAT", "NUMERIC", "REAL")):
        stats = con.execute(f'SELECT MIN(ABS("{name}")), MAX(ABS("{name}")) FROM {tabla}').fetchone()
        max_abs = max(stats[0] or 0, stats[1] or 0)
        str_val = str(round(max_abs, 4))
        parts = str_val.split(".")
        int_dig = len(parts[0].lstrip("0") or "0")
        dec_dig = max(len(parts[1].rstrip("0")) if len(parts) > 1 else 0, 2)
        precision = max(int_dig + dec_dig, 10)
        return f"DECIMAL({precision},{dec_dig})"

    if dtype in ("VARCHAR", "TEXT", "STR", "OBJECT", "BLOB"):
        res = con.execute(f'SELECT MAX(LENGTH("{name}"::VARCHAR)) FROM {tabla}').fetchone()[0]
        max_len = int(res or 0)
        if max_len == 0:        return "VARCHAR(50)"
        if max_len > 4000:      return "VARCHAR(MAX)"
        return f"VARCHAR({int(max_len * 1.2) + 10})"

    return "VARCHAR(MAX)"


def _inferir_tipo_sql_pandas(df, name, dtype):
    if _es_campo_forzar_varchar(name):
        max_len = df[name].astype(str).str.len().max() or 20
        return f"VARCHAR({max(int(max_len), 20)})" if max_len <= 4000 else "VARCHAR(MAX)"

    if "datetime" in dtype.lower() or "FECHA_CARGA" in name.upper():
        return "DATETIME"

    if "int" in dtype.lower():
        v_min = df[name].min() or 0
        v_max = df[name].max() or 0
        if v_min >= 0 and v_max <= 255:                          return "TINYINT"
        if v_min >= -32_768 and v_max <= 32_767:                 return "SMALLINT"
        if v_min >= -2_147_483_648 and v_max <= 2_147_483_647:   return "INT"
        return "BIGINT"

    if "float" in dtype.lower():
        max_abs = df[name].abs().max() or 0
        str_val = str(round(max_abs, 4))
        parts = str_val.split(".")
        int_dig = len(parts[0].lstrip("0") or "0")
        dec_dig = max(len(parts[1].rstrip("0")) if len(parts) > 1 else 0, 2)
        precision = max(int_dig + dec_dig, 10)
        return f"DECIMAL({precision},{dec_dig})"

    if "object" in dtype.lower() or "string" in dtype.lower():
        max_len = df[name].astype(str).str.len().max() or 0
        if max_len == 0:    return "VARCHAR(50)"
        if max_len > 4000:  return "VARCHAR(MAX)"
        return f"VARCHAR({int(max_len * 1.2) + 10})"

    return "VARCHAR(MAX)"