# Ligações — Raspberry Pi 3 + kit Freenove

Numeração **BCM** (a mesma do gpiozero e do `config.toml`), não a numeração
física da barra de pinos.

## Tabela geral

| Periférico | Sinal | GPIO (BCM) | Pino físico | Observação |
|---|---|---|---|---|
| LED | ânodo | 17 | 11 | resistor de 220 Ω em série até o GND |
| Servo SG90 | sinal | 18 | 12 | PWM por hardware |
| Servo SG90 | VCC | — | 2 ou 4 (5 V) | **fonte externa se o servo tiver carga** |
| Servo SG90 | GND | — | 6 | GND comum com o Pi |
| Botão push-to-talk | — | 26 | 37 | outro terminal no GND (pino 39) |
| HC-SR04 | TRIG | 23 | 16 | |
| HC-SR04 | ECHO | 24 | 18 | **divisor de tensão obrigatório** |
| HC-SR04 | VCC | — | 2 (5 V) | |
| LCD 1602 I2C | SDA | 2 | 3 | |
| LCD 1602 I2C | SCL | 3 | 5 | |
| LCD 1602 I2C | VCC | — | 4 (5 V) | o módulo aceita 5 V; o I2C é tolerante |
| Matriz 8x8 (74HC595) | DS | 5 | 29 | dados |
| Matriz 8x8 (74HC595) | SHCP | 6 | 31 | clock do shift |
| Matriz 8x8 (74HC595) | STCP | 13 | 33 | latch |

## ⚠️ Divisor de tensão no ECHO

O HC-SR04 alimenta em 5 V e o pino ECHO devolve 5 V. O GPIO do Raspberry Pi
tolera no máximo 3,3 V. Ligar direto queima o pino — e não tem conserto.

```
ECHO ──[ R1 = 1 kΩ ]──┬── GPIO24
                      │
                  [ R2 = 2 kΩ ]
                      │
                     GND
```

Saída = 5 V × 2/(1+2) ≈ 3,3 V. Qualquer par com R2 ≈ 2×R1 serve.

## ⚠️ Alimentação do servo

O SG90 puxa picos de corrente ao iniciar o movimento. Alimentado pelo 5 V do
próprio Pi, ele derruba a tensão e o Pi reinicia no meio da demonstração — algo
que costuma aparecer só na hora de apresentar. Se isso acontecer, use uma fonte
de 5 V separada e **una os GNDs**.

## Botão push-to-talk

Ligado entre o GPIO26 e o GND, sem resistor externo: o código usa o pull-up
interno (`Button(pin, pull_up=True)`). Em repouso o pino lê nível alto; ao
apertar, vai para o GND.

```
GPIO26 ──── [botão] ──── GND
```

## Conferindo o I2C do LCD

```bash
sudo raspi-config nonint do_i2c 0    # habilita
sudo i2cdetect -y 1
```

Deve aparecer `27` ou `3f` na grade. Se aparecer outro endereço, coloque em
`config.toml`:

```toml
[lcd]
address = "0x3f"
```

Se a grade sair toda com `--`, o problema é físico: confira SDA/SCL invertidos,
VCC e GND. Se a luz de fundo acende mas nada aparece, ajuste o potenciômetro de
contraste no verso do módulo — é o erro mais comum e não é software.

## Conflitos de pino a evitar

- GPIO2 e GPIO3 são exclusivos do I2C. Não use para mais nada.
- GPIO14 e GPIO15 são o UART (console serial).
- GPIO18 é PWM de hardware. Deixe para o servo.
- GPIO7–11 são SPI. Livres se você não usar SPI, mas evite por segurança.
