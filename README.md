# Central de comandos por voz — Raspberry Pi 3 + kit Freenove

Reconhecimento de fala **offline** (Vosk) acionando LED, servomotor, LCD 16x2 I2C,
sensor ultrassônico e matriz de LEDs. Sem internet, sem API externa, sem nuvem.

Funciona por **push-to-talk**: segure o botão, fale, solte.

---

## Instalação rápida no Raspberry Pi

```bash
git clone <este-repo> centralvoz && cd centralvoz

# 1. dependências de sistema (GPIO, I2C, áudio)
bash scripts/setup_pi.sh

# 2. ambiente Python (--system-site-packages é obrigatório, veja abaixo)
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e ".[voice,pi]"

# 3. modelo de fala em português (~50 MB)
bash scripts/download_model.sh

# 4. confira se está tudo de pé
voz doctor
```

## Uso

```bash
voz doctor            # diagnóstico: GPIO, I2C, microfone, modelo
voz hello             # teste mínimo: fale e veja o texto no LCD (só I2C)
voz devices           # lista as entradas de áudio
voz selftest          # aciona cada periférico em sequência
voz text --mock       # digita comandos, sem hardware e sem microfone
voz say "ligar led"   # executa um comando único
voz run               # loop de voz completo (push-to-talk)
```

Todo subcomando aceita `--mock` (simula tudo), `--real` (força hardware) e
`--trigger keyboard` (usa ENTER em vez do botão físico).

### Primeiro teste: `voz hello`

Antes de ligar LED, servo e sensor, valide o caminho mais curto — microfone →
Vosk → LCD:

```bash
voz hello --trigger keyboard
```

São três etapas: escreve `OLA MUNDO` no LCD, abre o microfone e carrega o
modelo, e então tudo que você falar aparece no display.

As opções globais (`--mock`, `--trigger`, `--rate`, `--device`...) funcionam
antes ou depois do subcomando — tanto faz.

**Microfone que recusa 16 kHz.** Muitos USB (Fifine, Snowball, webcams) só
abrem em 44,1 ou 48 kHz e o PortAudio responde `Invalid sample rate
[PaErrorCode -9997]`. O projeto negocia a taxa sozinho e repassa ao Vosk, que
reamostra internamente; microfones que só abrem em estéreo também são
convertidos para mono automaticamente. Para fixar na mão:
`voz hello --rate 48000 --device 2`.

Esse comando **não usa GPIO nenhum**. O LCD I2C fala por `smbus2`, então ele
funciona mesmo com o backend de GPIO quebrado — o que isola áudio e I2C de
qualquer problema de PWM.

## Comandos de voz

| Diga | O que acontece |
|---|---|
| ligar led / acender a luz | acende o LED |
| desligar led / apagar a luz | apaga o LED |
| piscar led | pisca 5 vezes |
| abrir servo / abrir porta | servo vai para 90° |
| fechar servo / fechar porta | servo volta para 0° |
| varrer servo | varredura completa (teste) |
| mostrar distância | lê o HC-SR04 e mostra no LCD |
| monitorar distância / modo alerta | vigia por 15 s, alerta com LED e matriz |
| **transcrever / modo ditado** | **tudo que você falar vira texto no LCD e é salvo** |
| parar ditado | volta ao modo de comandos |
| ler recados | mostra as últimas anotações, paginadas no LCD |
| repetir | mostra de novo o último conteúdo |
| que horas são | relógio no LCD |
| status do sistema | temperatura da CPU, uptime, IP |
| ajuda | lista os comandos no próprio LCD |
| limpar tela | apaga LCD, LED e matriz |
| desligar sistema | encerra o programa |

O reconhecimento é **tolerante**: "ligar lede", "liga a luz" e "abre o servo"
funcionam. E "**não** ligar led" corretamente *não* liga nada.

### Modo ditado

`transcrever` desliga a gramática restrita do Vosk e passa a reconhecimento
livre. Cada frase falada aparece no LCD (paginada, porque 16x2 não comporta uma
frase inteira) e vai para o SQLite. `ler recados` traz tudo de volta.

## Ligações

Pinagem padrão (numeração BCM), toda configurável em `config.toml`:

| Periférico | Pinos |
|---|---|
| LED | GPIO17 (+ resistor de 220 Ω para o GND) |
| Servo | GPIO18 (PWM por hardware) |
| Botão push-to-talk | GPIO26 → GND (pull-up interno) |
| HC-SR04 | TRIG GPIO23, ECHO GPIO24 **com divisor de tensão** |
| LCD 1602 I2C | SDA GPIO2, SCL GPIO3, VCC 5 V, GND |
| Matriz 8x8 (74HC595) | DS GPIO5, SHCP GPIO6, STCP GPIO13 |

⚠️ O ECHO do HC-SR04 entrega 5 V e o GPIO só aceita 3,3 V. Use divisor
(1 kΩ + 2 kΩ) ou você vai queimar o pino. Detalhes em [`docs/ligacoes.md`](docs/ligacoes.md).

## Configuração

Copie `config.example.toml` para `config.toml` e ajuste. Tudo é opcional.

```toml
mock = false

[pins]
leds = [17, 27]
servo = 18
button = 26

[lcd]
address = "0x3f"     # se o i2cdetect mostrar 3f em vez de 27

[audio]
input_device = 1     # veja com: voz devices

[speech]
match_threshold = 0.70   # menor = aceita mais, erra mais
```

Precedência: argumento de linha de comando → variável de ambiente
(`CENTRALVOZ_MOCK`, `CENTRALVOZ_PIN_FACTORY`, `CENTRALVOZ_MODEL`) →
`config.toml` → padrão.

---

## Erro comum: `No module named 'lgpio'` / `PWM is not supported`

O gpiozero 2.x tenta as *pin factories* nesta ordem:
**lgpio → RPi.GPIO → pigpio → native**. Se nenhuma das três primeiras estiver
instalada, ele cai na `native`, que só faz GPIO digital. O LED até acende, mas o
servo precisa de PWM e quebra.

```bash
sudo apt install -y python3-lgpio
```

Se você usa um venv, o pacote do apt **não** é enxergado. Recrie com
`python3 -m venv --system-site-packages .venv`, ou `pip install lgpio` dentro
do venv.

Para PWM com timing de hardware (servo sem tremer):

```bash
sudo apt install -y pigpio python3-pigpio
sudo systemctl enable --now pigpiod
voz run --pin-factory pigpio
```

`voz doctor` detecta isso sozinho e imprime o comando certo.

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest
```

A suíte roda inteira em modo simulado — não precisa de Raspberry Pi, microfone
nem modelo Vosk. É o que a CI do GitHub Actions executa a cada push.

## Estrutura

```
centralvoz/
├── cli.py            subcomandos (run, text, say, selftest, doctor, devices)
├── config.py         configuração única (TOML + env + CLI)
├── gpio_setup.py     escolhe a pin factory e explica o erro do lgpio
├── doctor.py         diagnóstico do ambiente
├── hardware/         led, servo, lcd (I2C), distance, matrix, trigger, factory
├── audio/            captura em streaming pelo microfone
├── speech/           motor Vosk com gramática restrita
├── commands/         intents, roteador aproximado, handlers
├── app/              controller (despacho) e runner (loop push-to-talk)
└── storage/          SQLite de eventos e recados
```

Cada periférico tem duas implementações — real e simulada — escolhidas **uma
única vez** em `hardware/factory.py`, sempre registradas no log. Se o LCD não
responder no I2C, só ele cai para simulado e o resto continua funcionando.
