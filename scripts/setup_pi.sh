#!/usr/bin/env bash
# Instala as dependencias de sistema no Raspberry Pi OS (Bookworm/Trixie).
set -euo pipefail

echo ">> Atualizando indices do apt..."
sudo apt update

echo ">> GPIO (lgpio: backend com suporte a PWM, resolve o erro do servo)..."
sudo apt install -y python3-lgpio python3-gpiozero

echo ">> I2C para o LCD 1602..."
sudo apt install -y i2c-tools python3-smbus2

echo ">> Audio (PortAudio, usado pelo sounddevice)..."
sudo apt install -y libportaudio2 portaudio19-dev

echo ">> Utilitarios..."
sudo apt install -y python3-venv unzip wget

# Habilita o I2C sem precisar entrar no raspi-config na mao.
if command -v raspi-config >/dev/null 2>&1; then
    echo ">> Habilitando a interface I2C..."
    sudo raspi-config nonint do_i2c 0 || true
fi

# Permissoes: sem isso da "Permission denied" no /dev/i2c-1 e no GPIO.
echo ">> Adicionando $USER aos grupos i2c, gpio, spi e audio..."
for grupo in i2c gpio spi audio; do
    getent group "$grupo" >/dev/null && sudo usermod -aG "$grupo" "$USER" || true
done

echo
echo "Dispositivos no barramento I2C (o LCD costuma ser 0x27 ou 0x3f):"
sudo i2cdetect -y 1 || echo "  (i2cdetect falhou -- reinicie e tente de novo)"

echo
echo "Microfones detectados:"
arecord -l || echo "  (nenhum. conecte o microfone USB)"

cat <<'FIM'

Pronto. Proximos passos:

    # FACA LOGOUT E LOGIN (ou reinicie) para os grupos valerem
    python3 -m venv --system-site-packages .venv
    source .venv/bin/activate
    pip install -e ".[voice,pi]"
    bash scripts/download_model.sh
    voz doctor

O --system-site-packages e obrigatorio: sem ele o venv nao enxerga o
python3-lgpio instalado pelo apt, e o servo volta a falhar com
"PWM is not supported".
FIM
