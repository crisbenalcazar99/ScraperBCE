#!/bin/bash
# =============================================================================
# run.sh — Ejecutor estándar para TASAS_REFERENCIALES
# =============================================================================
# Responsabilidades:
#   1. Autenticar con Kerberos (kinit)
#   2. Configurar variables de entorno del proyecto
#   3. Ejecutar main.py y capturar su salida
#   4. Parsear la línea [RESUMEN] que main.py siempre imprime
#   5. Enviar notificación al bot de Telegram vía API local
#
# Contrato con main.py:
#   main.py SIEMPRE imprime una línea con este formato antes de terminar:
#     [RESUMEN] | OK    | STG_TABLA | procesados=N cargados=N descartados=N | HH:MM:SS
#     [RESUMEN] | ERROR | STG_TABLA | procesados=N cargados=N descartados=N | HH:MM:SS | Detalle
#
#   Si esa línea NO aparece en la salida, run.sh asume CRITICAL_ERROR
#   (Python colapsó antes de poder imprimirla).
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuración — ajusta estas variables al proyecto
# ---------------------------------------------------------------------------
PROYECTO="TASAS_REFERENCIALES"
RUTA_SCRIPT="/opt/apps/python/projects/data-eng-webscraping/PREMISE/TASAS_REFERENCIALES"

USUARIO_PRINCIPAL="apl_bdwebscrapping@BGGRUPO.BANK"
RUTA_KEYTAB="/opt/apps/python/projects/apl_bdwebscrapping.keytab"

PLATAFORMA_TLG="-1002788889050"   # ID del grupo/canal de Telegram
API_NOTIFICACIONES="http://localhost:8080/notificacionestlg/v1/logs"

# ---------------------------------------------------------------------------
# 1. Autenticación Kerberos
# ---------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Autenticando con Keytab..."
kinit -kt "$RUTA_KEYTAB" "$USUARIO_PRINCIPAL"

if ! klist -s; then
    echo "[ERROR] Falló la autenticación con Keytab. Abortando."
    FECHA=$(date +"%Y-%m-%d %H:%M:%S")
    MENSAJE="Scraper: $PROYECTO\nEstado: CRITICAL_ERROR\nFecha: $FECHA\n\nDetalle:\nFalló la autenticación Kerberos. El script no pudo iniciar."
    curl --silent --location --request POST "$API_NOTIFICACIONES" \
         --header 'Content-Type: application/json' \
         --data-raw "{\"usuario\": \"ingenieria\", \"mensaje\": \"$MENSAJE\", \"plataforma\": \"$PLATAFORMA_TLG\"}"
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Variables de entorno del proyecto
# ---------------------------------------------------------------------------
cd "$RUTA_SCRIPT"
# ---------------------------------------------------------------------------
# 3. Ejecución de main.py
# ---------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando $PROYECTO..."
set +e
SALIDA_SCRIPT=$("$RUTA_SCRIPT/venv/bin/python3.12" "main.py" 2>&1)
CODIGO_SALIDA=$?
set -e

# ---------------------------------------------------------------------------
# 4. Parseo del [RESUMEN]
#
#   Campos esperados (separados por |):
#     [0] = "[RESUMEN]"
#     [1] = Status        (OK / ERROR)
#     [2] = Tabla         (STG_...)
#     [3] = Métricas      (procesados=N cargados=N descartados=N)
#     [4] = Duración      (HH:MM:SS)
#     [5] = Detalle error (solo si ERROR, opcional)
# ---------------------------------------------------------------------------
LINEA_RESUMEN=$(echo "$SALIDA_SCRIPT" | grep "\[RESUMEN\]" | tail -n 1 | sed 's/.*\[RESUMEN\]/[RESUMEN]/') || true

if [[ "$LINEA_RESUMEN" == *"[RESUMEN]"* ]]; then
    STATUS=$(echo   "$LINEA_RESUMEN" | cut -d'|' -f2 | xargs)
    TABLA=$(echo    "$LINEA_RESUMEN" | cut -d'|' -f3 | xargs)
    METRICAS=$(echo "$LINEA_RESUMEN" | cut -d'|' -f4 | xargs)
    DURACION=$(echo "$LINEA_RESUMEN" | cut -d'|' -f5 | xargs)
    DETALLE_ERR=$(echo "$LINEA_RESUMEN" | cut -d'|' -f6- | xargs)
else
    # Python colapsó sin imprimir [RESUMEN] (import error, kill, OOM, etc.)
    STATUS="CRITICAL_ERROR"
    TABLA="DESCONOCIDA"
    METRICAS="procesados=? cargados=? descartados=?"
    DURACION="??:??:??"
    DETALLE_ERR=$(echo "$SALIDA_SCRIPT" | tail -n 5 | tr '\n' ' ' | sed 's/|/ - /g')
    if [ -z "$DETALLE_ERR" ]; then
        DETALLE_ERR="El script Python colapsó abruptamente sin generar salida."
    fi
fi

# ---------------------------------------------------------------------------
# 5. Construcción del mensaje y notificación
# ---------------------------------------------------------------------------
FECHA=$(date +"%Y-%m-%d %H:%M:%S")

if [[ "$STATUS" == "OK" ]]; then
    MENSAJE="✅ $PROYECTO\nEstado: $STATUS\nTabla: $TABLA\nFecha: $FECHA\nDuración: $DURACION\n\n$METRICAS"
else
    DETALLE_F=$(echo "$DETALLE_ERR" | sed 's/"/\\"/g')
    MENSAJE="❌ $PROYECTO\nEstado: $STATUS\nTabla: $TABLA\nFecha: $FECHA\nDuración: $DURACION\n\n$METRICAS\n\nDetalle:\n$DETALLE_F"
fi

echo ""
echo "========================================="
echo "$MENSAJE"
echo "========================================="

curl --silent --location --request POST "$API_NOTIFICACIONES" \
     --header 'Content-Type: application/json' \
     --data-raw "{\"usuario\": \"ingenieria\", \"mensaje\": \"$MENSAJE\", \"plataforma\": \"$PLATAFORMA_TLG\"}"

echo ""
exit ${CODIGO_SALIDA}
