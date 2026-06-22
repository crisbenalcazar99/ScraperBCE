#!/bin/bash
RutaScript="/opt/apps/python/projects/data-eng-webscraping/PREMISE/TASAS_REFERENCIALES"

echo "Iniciando actualizacion de tasas..."
USUARIO_PRINCIPAL="apl_bdwebscrapping@BGGRUPO.BANK"
RUTA_KEYTAB="/opt/apps/python/projects/apl_bdwebscrapping.keytab"

kinit -kt "$RUTA_KEYTAB" "$USUARIO_PRINCIPAL"

if ! klist -s; then
    echo "[ERROR] Falló la autenticación con Keytab. Abortando."
    exit 1
fi

echo "Activando ambiente virtual y ejecutando Script..."
cd "$RutaScript" || exit 1

ResultadoScript=$("./venv/bin/python3.12" "main.py" 2>&1)
if echo "$ResultadoScript" | grep -q "RESUMEN: SIN ERRORES"; then
    Status="OK"
    Detalle="Ejecución finalizada sin errores."
else
    Status="ERROR"
    Detalle=$(echo "$ResultadoScript" | tail -n 5 | tr '\n' ' ')
fi

Fecha=$(date +"%Y-%m-%d %H:%M:%S")
DetalleF=$(echo "$Detalle" | sed -E 's/[[:space:]]*\|[[:space:]]*/\\n/g' | sed 's/"/\\"/g')
TextoMensaje="Resumen Tasas\\nEstado: $Status\\nFecha: $Fecha\\n\\nDetalle:\\n$DetalleF"

echo -e "$TextoMensaje"

# curl --location --request POST 'http://localhost:8080/notificacionestlg/v1/logs' \
     # --header 'content-type: application/json' \
     # --data-raw "{\"usuario\": \"ingenieria\", \"mensaje\": \"$TextoMensaje\", \"plataforma\": \"-1002788889050\"}"
# echo ""