import pandas as pd
import numpy as np
import warnings
import pyodbc
import sqlalchemy as sql
import requests
import string
import unicodedata
import re  # Para usar expresiones regulares
from datetime import date
from datetime import datetime
from bs4 import BeautifulSoup
import urllib3  
from datetime import datetime



def extract_key_values_table(table):
    data = []
    current_key = None
    values = []

    for td in table.find_all('td'):
        colspan = td.get('colspan')
        text = td.get_text(strip=True)

        if colspan and int(colspan) >= 3:
            if current_key is not None:
                data.append([current_key] + values)
            current_key = text
            values = []
        else:
            if current_key is not None:
                val = text.replace('.', '').replace(',', '.')
                try:
                    val = float(val)
                except:
                    pass
                values.append(val)

    if current_key is not None:
        data.append([current_key] + values)

    max_cols = max(len(row) for row in data)
    columns = ['Concepto'] + [f'Valor{i}' for i in range(1, max_cols)]
    return pd.DataFrame(data, columns=columns)

#Método de limpieza para caracteres raros
def limpiar_texto_df(df): 
    df_limpio = df.copy()

    def limpiar_texto(valor):
        if isinstance(valor, str):
            valor = unicodedata.normalize('NFD', valor)
            valor = ''.join(c for c in valor if unicodedata.category(c) != 'Mn')
            valor = re.sub(r'\s+', ' ', valor)
            valor = re.sub(r'[^\w\s.,%-]', '', valor)
            valor = valor.strip()
        return valor

    return df_limpio.map(limpiar_texto)

def limpiar_nombres_columnas(df: pd.DataFrame) -> pd.DataFrame:  
    df = df.copy()  # Para no modificar el df original
    df.columns = (
        df.columns
        .str.replace(r'[\r\n]', ' ', regex=True)
        .str.replace(r'\d+', '', regex=True)
        .str.strip()
    )
    return df

def convertir_a_aaaamm(texto):
    meses_dict = {
        'Enero': '01',
        'Febrero': '02',
        'Marzo': '03',
        'Abril': '04',
        'Mayo': '05',
        'Junio': '06',
        'Julio': '07',
        'Agosto': '08',
        'Septiembre': '09',
        'Octubre': '10',
        'Noviembre': '11',
        'Diciembre': '12'
    }
    mes, anio = texto.split()
    mes_num = meses_dict.get(mes, '00')
    return f"{anio}{mes_num}"

# Conexión de SQL ALCHEMY a DN_STAGING
def get_engine(sql): 
    DRIVER = "ODBC Driver 17 for SQL Server"
    SERVERNAME = "GYEINTNEGDB01,4433"
    DB = "DN_STAGING"
    engine = sql.create_engine(
    f"mssql+pyodbc://@{SERVERNAME}/{DB}?driver={DRIVER}")

    return engine

def get_tablas(url):
    ## Traer tablas
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    response = requests.get(url, verify=False)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, 'html.parser')

    tables = soup.find_all('table')
    print(f"Se encontraron {len(tables)} tablas en total.")
    
    # Lista para guardar todas las tablas que cumplen el formato
    tablas_extraidas = []

    for i, table in enumerate(tables):
        # Chequear si la tabla tiene al menos un td con colspan >= 3
        tds = table.find_all('td')
        if any(td.get('colspan') and int(td.get('colspan')) >= 3 for td in tds):
            print(f"Tabla {i} parece tener formato clave-valor, extrayendo...")
            df = extract_key_values_table(table)
            tablas_extraidas.append((i, df))
        else:
            print(f"Tabla {i} no tiene formato clave-valor, ignorando.")

    # Mostrar resumen
    print(f"\nSe extrajeron {len(tablas_extraidas)} tablas con formato clave-valor.\n")

    list_df = {}
    for idx, (i, df) in enumerate(tablas_extraidas):
        print(f"--- Tabla extraída {idx+1} (índice original {i}) ---")
        print(df.head(10))
        print("\n")
        list_df[f"tabla_extraida_{idx+1}_indice_{i}"] = df

    return list_df

def get_otras_tablas(list_df):
    df_otras_tasas = list_df['tabla_extraida_2_indice_1'].iloc[23]
    valores = df_otras_tasas.values.flatten().tolist()
    valores_limpios = []
    for v in valores:
        if isinstance(v, (int, float, np.float64)) and not (isinstance(v, float) and np.isnan(v)): # números (tasas)
            valores_limpios.append(v)
        elif isinstance(v, str) and "Tasa" in v:   # textos de plazos
            valores_limpios.append(v.strip().replace("\r\n", " "))
            
    # Ahora ya está limpio: [Plazo, Tasa, Plazo, Tasa, ...]
    pares = [(valores_limpios[i], valores_limpios[i+1]) for i in range(0, len(valores_limpios), 2)]

    # Construimos el DataFrame final
    df_reordenado_otras_tasas = pd.DataFrame(pares, columns=["Tasa", "Valor"])

    # Ajustamos decimales
    df_reordenado_otras_tasas["Valor"] = df_reordenado_otras_tasas["Valor"].astype(float).round(2)
    df_reordenado_otras_tasas["Categoria"] = 'OTRAS TASAS'
    
    return df_reordenado_otras_tasas

def get_tablas_plazo(list_df):
    df_tasas_ref_plazo = list_df['tabla_extraida_2_indice_1'].iloc[22]
    valores = df_tasas_ref_plazo.values.flatten().tolist()

    # Filtrar: nos quedamos solo con plazos y números
    valores_limpios = []
    for v in valores:
        if isinstance(v, (int, float, np.float64)):  # números (tasas)
            valores_limpios.append(v)
        elif isinstance(v, str) and "Plazo" in v:   # textos de plazos
            valores_limpios.append(v.strip().replace("\r\n", " "))
    pares = [(valores_limpios[i], valores_limpios[i+1]) for i in range(0, len(valores_limpios), 2)]

    # Construimos el DataFrame final
    df_reordenado_ref_plazo = pd.DataFrame(pares, columns=["Tasa", "Valor"])

    # Ajustamos decimales
    df_reordenado_ref_plazo["Valor"] = df_reordenado_ref_plazo["Valor"].astype(float).round(2)
    df_reordenado_ref_plazo["Categoria"] = 'TASAS POR PLAZO'

    return df_reordenado_ref_plazo

def subir_tablas(df_merged,engine):
    max_periodo = df_merged['PERIODO'].max()
    print("Máximo periodo en df_merged:", max_periodo)

    query = "SELECT MAX(PERIODO) as max_periodo FROM [DN_STAGING].[ANALYTICS].[ISC_VIZ_MK_TASAS_MAXIMAS_REFERENCIALES]"

    try:
        result = pd.read_sql_query(query, engine)
        max_periodo_db = result['max_periodo'].iloc[0]

        # Si el resultado es None (tabla vacía), asignar valor estándar también
        if max_periodo_db is None:
            max_periodo_db = 199101
    except Exception as e:
        print(f"No se pudo consultar la tabla, error: {e}")
        max_periodo_db = 199101

    print("Máximo periodo en BD (o valor estándar):", max_periodo_db)

    if max_periodo > max_periodo_db:
        # df_merged.to_sql("ISC_VIZ_MK_TASAS_MAXIMAS_REFERENCIALES", con=engine, 
        #     if_exists="append", 
        #     index=False, 
        #     schema='ANALYTICS', 
        #     chunksize=20)
        print("Subido con éxito")
        return True
    else:
        print("No hay datos nuevos")
        return False

def subir_otras_tablas(df_merged_otras,engine):

    df_merged_otras = df_merged_otras.rename(columns={"Tasa":"TASAS_REFERENCIALES", 
                                                  "Valor":"TASA_PORCENTUAL",
                                                  "Categoria":"CATEGORIA",})

    max_periodo = df_merged_otras['PERIODO'].max()
    print("Máximo periodo en df_merged otras:", max_periodo)

    query = "SELECT MAX(PERIODO) as max_periodo FROM [DN_STAGING].[ANALYTICS].[ISC_VIZ_OTRAS_TASAS_REFERENCIALES]"

    try:
        result = pd.read_sql_query(query, engine)
        max_periodo_db = result['max_periodo'].iloc[0]

        # Si el resultado es None (tabla vacía), asignar valor estándar también
        if max_periodo_db is None:
            max_periodo_db = 199101

    except Exception as e:
        print(f"No se pudo consultar la tabla, error: {e}")
        max_periodo_db = 199101

    print("Máximo periodo en BD otras (o valor estándar):", max_periodo_db)

    if max_periodo > max_periodo_db:
        # df_merged_otras.to_sql("ISC_VIZ_OTRAS_TASAS_REFERENCIALES", con=engine, 
        #     if_exists="append", 
        #     index=False, 
        #     schema='ANALYTICS', 
        #     chunksize=20)
        print("Subido con éxito")
        return True
    else:
        print("No hay datos nuevos")
        return False

def enviar_notificacion_exito(registros_otros, registros, periodo_otros, periodo, engine):
    cuerpo_html = f"""
        <html>
        <body>
            <p>La tabla <b>ISC_VIZ_MK_TASAS_MAXIMAS_REFERENCIALES</b> se ha actualizado correctamente.</p>
            <ul>
                <li><b>Registros procesados:</b> {registros:,}</li>
                <li><b>Periodo:</b> {periodo}</li>
                <li><b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
            </ul>
            </p>
            <p>La tabla <b>ISC_VIZ_OTRAS_TASAS_REFERENCIALES</b> se ha actualizado correctamente.</p>
            <ul>
                <li><b>Registros procesados:</b> {registros_otros:,}</li>
                <li><b>Periodo:</b> {periodo_otros}</li>
                <li><b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
            </ul>
            </p>
        </body>
        </html>
        """
        # Crear DataFrame con los datos a insertar
    df_correo = pd.DataFrame({
            'nombre_persona': ['Equipo de Ing de datos'],
            'usuario_persona': ['gcortez&jbustamante2&wflores&jrojas1&jquimi&gaguilar'],
            'asunto_correo': ['Actualización exitosa: TASAS REFERENCIALES'],
            'cuerpo_correo': [cuerpo_html],
            'enviado': [0],
            'FECHA_INGRESO_EN_COLA': [datetime.now()]
        })

        # Insertar en la tabla
    df_correo.to_sql(
            name="t_cola_mensajes",
            con=engine,
            if_exists="append",
            index=False,
            schema='dbo',
            chunksize=1
        )

    print("✅ Correo insertado en cola de mensajes")
 


try:
    print('inicio')
    
    url = "https://contenido.bce.fin.ec/documentos/Estadisticas/SectorMonFin/TasasInteres/Indice.htm"
    engine = get_engine(sql)

    ## GET Tablas 
    list_df = get_tablas(url)
    df_reordenado_otras_tasas = get_otras_tablas(list_df)
    df_reordenado_ref_plazo = get_tablas_plazo(list_df)

    # Ordenar 
    df_activas_raw = list_df['tabla_extraida_1_indice_0'].iloc[:, :2]
    df_referenciales_raw = list_df['tabla_extraida_2_indice_1'].iloc[:, :2]

    # Usar la fila 4 como cabecera real (índice 3)
    header_activas = df_activas_raw.iloc[3] 
    df_activas = df_activas_raw.iloc[5:].copy() 
    df_activas.columns = header_activas
    df_activas.reset_index(drop=True, inplace=True)

    header_referenciales = df_referenciales_raw.iloc[4, :2] 
    df_referenciales = df_referenciales_raw.iloc[6:, :2].copy()  
    df_referenciales.columns = header_referenciales
    df_referenciales.reset_index(drop=True, inplace=True)

    # Asegúrate de que el nombre de la columna esté correctamente escrito
    df_activas["% anual"] = pd.to_numeric(df_activas ["% anual"], errors='coerce')
    df_activas = df_activas[df_activas["% anual"].notna()].copy()

    # Asegúrate de que el nombre de la columna esté correctamente escrito
    df_referenciales["% anual"] = pd.to_numeric(df_referenciales["% anual"], errors='coerce')
    df_referenciales = df_referenciales[df_referenciales["% anual"].notna()].copy()

    #Aplicamos limpieza
    df_activas = limpiar_texto_df(df_activas)
    df_referenciales = limpiar_texto_df(df_referenciales)
    df_limpieza_otras_tasas = limpiar_texto_df(df_reordenado_otras_tasas)
    df_limpieza_ref_plazo = limpiar_texto_df(df_reordenado_ref_plazo)

    #Mas limpieza
    df_activas_limpio = limpiar_nombres_columnas(df_activas)
    df_referenciales_limpio = limpiar_nombres_columnas(df_referenciales)
    df_limpieza_otras_tasas = limpiar_nombres_columnas(df_reordenado_otras_tasas)
    df_limpieza_ref_plazo = limpiar_nombres_columnas(df_reordenado_ref_plazo)

    df_activas_limpio.rename(columns={'Tasa Activa    Efectiva Máxima para el segmento': 'SEGMENTO'}, inplace=True)
    df_activas_limpio.rename(columns={'% anual': 'TASA_EFECTIVA_MAXIMA'}, inplace=True)

    df_referenciales_limpio.rename(columns={'Segmentos de    Crédito': 'SEGMENTO_CREDITO'}, inplace=True)
    df_referenciales_limpio.rename(columns={'% anual': 'TASA_REFERENCIAL'}, inplace=True)

    #Merge necesitado
    df1 = df_activas_limpio[['SEGMENTO', 'TASA_EFECTIVA_MAXIMA']]
    df2 = df_referenciales_limpio[['SEGMENTO_CREDITO','TASA_REFERENCIAL']]
    df_merged = pd.merge(df1, df2, left_on='SEGMENTO', right_on='SEGMENTO_CREDITO', how='inner')
    df_merged_otras = pd.concat([df_limpieza_ref_plazo, df_limpieza_otras_tasas])   

    # Luego, eliminas la columna 'segmento' del resultado final
    df_merged = df_merged.drop(columns=['SEGMENTO'])

    # Reordenar las columnas para que 'segmento' quede primero
    cols = ['SEGMENTO_CREDITO'] + [col for col in df_merged.columns if col != 'SEGMENTO_CREDITO']
    df_merged = df_merged[cols]

    # Asignacion de periodo
    df_periodocarga = list_df['tabla_extraida_1_indice_0'].iloc[:1, :1]
    valor_periodo = df_periodocarga['Concepto'].iloc[0]  # Tomar el primer valor de 'CONCEPTO'
    df_merged['PERIODO'] = valor_periodo
    df_merged['PERIODO'] = df_merged['PERIODO'].apply(convertir_a_aaaamm)

    #Cambio el tipo de dato 
    df_merged['PERIODO'] = df_merged['PERIODO'].astype(int)
    df_merged_otras['PERIODO'] = df_merged['PERIODO'].astype(int)

    print(df_merged)
    print(df_merged_otras)

except Exception as e:
    print(f"Error de ejecución: {e}")

