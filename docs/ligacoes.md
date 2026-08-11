# Ligações — Raspberry Pi 3 + kit Freenove

Numeração **BCM** (a mesma do gpiozero e do `config.toml`), não a numeração
física da barra de pinos.

## Tabela geral

| Periférico | Sinal | GPIO (BCM) | Pino físico | Observação |
|---|---|---|---|---|
| LED RGB (R) | vermelho | 5 | 29 | módulo Freenove |
| LED RGB (G) | verde | 6 | 31 | |
| LED RGB (B) | azul | 13 | 33 | |
| LED RGB (comum) | 3,3 V | — | 1 ou 17 | **ânodo comum**: acende em nível baixo |
| Servo SG90 | sinal | 18 | 12 | PWM por hardware |
| Servo SG90 | VCC | — | 2 ou 4 (5 V) | **fonte externa se o servo tiver carga** |
| Servo SG90 | GND | — | 6 | GND comum com o Pi |
| Botão push-to-talk | — | 26 | 37 | outro terminal no GND (pino 39) |
| Buzzer ativo | sinal | 12 | 32 | módulo com transistor |
| Buzzer passivo | sinal | 4 | 7 | precisa de PWM para tocar notas |
| HC-SR04 | TRIG | 14 | 8 | **UART TXD** — veja o aviso abaixo |
| HC-SR04 | ECHO | 15 | 10 | **UART RXD** + divisor de tensão obrigatório |
| HC-SR04 | VCC | — | 2 (5 V) | |
| LCD 1602 I2C | SDA | 2 | 3 | |
| LCD 1602 I2C | SCL | 3 | 5 | |
| LCD 1602 I2C | VCC | — | 4 (5 V) | o módulo aceita 5 V; o I2C é tolerante |
| Matriz 8x8 (74HC595) | SHCP | 17 | 11 | clock do shift |
| Matriz 8x8 (74HC595) | DS | 22 | 15 | dados |
| Matriz 8x8 (74HC595) | STCP | 27 | 13 | latch |

## ⚠️ GPIO14 e GPIO15 são o UART

O sensor de distância usa esses dois pinos, que por padrão pertencem ao console
serial. Enquanto o console estiver ligado, o kernel fica escrevendo pela TXD e o
sensor lê lixo (ou nada).

```bash
sudo raspi-config
# Interface Options -> Serial Port
#   "login shell acessível pela serial?"  -> NÃO
#   "hardware serial habilitado?"          -> NÃO
sudo reboot
```

Confira depois com `voz doctor`: ele faz uma leitura real do sensor.

## ⚠️ Matriz: clock e latch precisam ser pinos diferentes

Você passou `(17, 22, 17)` para clock, data e latch — o 17 repetido. Isso não
funciona: o latch pulsaria junto com o clock e a imagem sairia embaralhada, sem
dar erro nenhum. Adotei **STCP = GPIO27**, que é o valor usado nos tutoriais
Freenove. Se o seu latch estiver em outro pino, ajuste no `config.toml`:

```toml
[pins]
matrix_latch = 27
```

`voz doctor` avisa quando dois periféricos disputam o mesmo GPIO.

## LED RGB: ânodo comum

Com o terminal comum ligado no **3,3 V**, o módulo é de ânodo comum — a corrente
sai do comum e entra pelo GPIO, então o LED acende quando o pino vai para nível
**baixo**. É por isso que o código usa `active_high=False`.

Se as cores saírem trocadas (você pede vermelho e acende ciano), o seu módulo é
de cátodo comum: mude no `config.toml`.

```toml
[pins]
rgb_active_high = true
```

Os módulos Freenove já trazem resistores embutidos. Se você montou com LED RGB
avulso na protoboard, coloque um resistor de 220 Ω em **cada** perna de cor.

Teste rápido de cada canal:

```bash
voz say --mock "acender vermelho"   # confere a lógica
voz say "acender vermelho"          # confere o hardware
voz say "acender verde"
voz say "acender azul"
```

Se só uma cor não acende, é aquele fio/pino. Se todas acendem na cor errada, é o
`rgb_active_high`.

## Buzzers: ativo × passivo

A diferença muda o que dá para fazer:

| | Ativo | Passivo |
|---|---|---|
| Oscilador | interno | nenhum |
| Frequência | fixa | você define |
| Toca melodia | não | sim |
| Marcação | costuma ter etiqueta/tampa | placa aberta, bobina à vista |

Na dúvida: ligue direto em 3,3 V. Se apitar sozinho, é ativo. Se ficar mudo (ou
só estalar), é passivo.

O projeto usa os dois: bipes vão para o ativo (mais alto e seco), melodias para
o passivo (o único que reproduz notas).

```bash
voz say "apitar"           # testa o ativo
voz say "tocar escala"     # testa o passivo
```

Se o buzzer apitar continuamente assim que o programa sobe, seu módulo aciona em
nível baixo:

```toml
[pins]
buzzer_active_high = false
```

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
- GPIO18 é PWM de hardware. Deixe para o servo — o LED RGB usa PWM por software,
  que é suficiente para luz mas não para servo.
- GPIO5, 6 e 13: LED RGB. GPIO4 e 12: buzzers. GPIO17, 22 e 27: matriz.
- GPIO14 e 15: sensor de distância (eram o UART — desative o console serial).
- GPIO7–11 são SPI. Livres se você não usar SPI, mas evite por segurança.
