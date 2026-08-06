#!/usr/bin/env bash
# Baixa o modelo Vosk pequeno de portugues (~50 MB, roda bem no Pi 3).
set -euo pipefail

MODELO="vosk-model-small-pt-0.3"
URL="https://alphacephei.com/vosk/models/${MODELO}.zip"
DESTINO="models"

mkdir -p "$DESTINO"

if [ -d "${DESTINO}/${MODELO}" ]; then
    echo "Modelo ja existe em ${DESTINO}/${MODELO}. Nada a fazer."
    exit 0
fi

echo ">> Baixando ${MODELO} (~50 MB)..."
wget -q --show-progress -O "/tmp/${MODELO}.zip" "$URL"

echo ">> Extraindo..."
unzip -q "/tmp/${MODELO}.zip" -d "$DESTINO"
rm -f "/tmp/${MODELO}.zip"

echo
echo "Modelo instalado em ${DESTINO}/${MODELO}"
echo "Se quiser mais precisao (e tiver paciencia no Pi 3), existe tambem o"
echo "modelo grande em https://alphacephei.com/vosk/models"
