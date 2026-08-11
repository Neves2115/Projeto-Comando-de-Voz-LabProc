# Jarvis — central de comandos por voz

**Raspberry Pi 3 + kit Freenove.**

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
voz mic               # mede o nível de captura e diz se o ganho está bom
voz selftest          # aciona cada periférico em sequência
voz text --mock       # digita comandos, sem hardware e sem microfone
voz say "ligar led"   # executa um comando único
voz run               # Jarvis: interface completa (push-to-talk)
voz run --plain       # mesma coisa, sem interface
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
| ligar luz / acender led | acende o LED RGB em branco |
| desligar luz / apagar led | apaga |
| **acender \<cor\>** | vermelho, verde, azul, amarelo, ciano, magenta, rosa, laranja, roxo, violeta, turquesa, lima, dourado, branco |
| trocar de cor / arco íris | passa pelas cores |
| brilho N por cento | escala a cor atual |
| piscar led | pisca 5 vezes |
| abrir servo / abrir porta | servo vai para 90° |
| fechar servo / fechar porta | servo volta para 0° |
| varrer servo | varredura completa (teste) |
| mostrar distância | lê o HC-SR04 e mostra no LCD |
| monitorar distância / modo alerta | sensor de ré: verde e bipe lento = livre, amarelo = aproximando, vermelho e bipe rápido = perto |
| **parar / cancelar** | interrompe o que estiver rodando |
| **transcrever / modo ditado** | **tudo que você falar vira texto no LCD e é salvo** |
| parar ditado | volta ao modo de comandos |
| ler recados | mostra as últimas anotações, paginadas no LCD |
| repetir | mostra de novo o último conteúdo |
| que horas são | relógio no LCD |
| status do sistema | temperatura da CPU, uptime, IP |
| ajuda | lista os comandos no próprio LCD |
| limpar tela | apaga LCD, LED e matriz |
| piscar led N vezes | ex.: "piscar led cinco vezes" |
| servo N graus | ex.: "servo cento e oitenta graus" |
| desenhar coração / sorriso / estrela / casa / gato / seta / triste | ícone na matriz |
| modo festa | LED, servo e matriz juntos por 12 s (bom para demo) |
| apagar recados | limpa as anotações |
| apitar / bipar | bipes no buzzer ativo |
| tocar música / escala / parabéns | melodia no buzzer passivo |
| tocar alarme / sirene | alarme sonoro e visual até mandar parar |
| silenciar / calar | corta o som |
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
| LED RGB | R=GPIO5, G=GPIO6, B=GPIO13, comum=3,3 V (ânodo comum) |
| Servo | GPIO18 (PWM por hardware) |
| Botão push-to-talk | GPIO26 → GND (pull-up interno) |
| HC-SR04 | TRIG GPIO14, ECHO GPIO15 **com divisor de tensão** — desative o console serial |
| LCD 1602 I2C | SDA GPIO2, SCL GPIO3, VCC 5 V, GND |
| Buzzer ativo | GPIO12 |
| Buzzer passivo | GPIO4 (PWM para tocar notas) |
| Matriz 8x8 (74HC595) | SHCP GPIO17, DS GPIO22, STCP GPIO27 |

⚠️ O ECHO do HC-SR04 entrega 5 V e o GPIO só aceita 3,3 V. Use divisor
(1 kΩ + 2 kΩ) ou você vai queimar o pino. Detalhes em [`docs/ligacoes.md`](docs/ligacoes.md).

## Reconhecimento ruim? Meça o microfone antes de mexer em qualquer outra coisa

```bash
voz mic
```

Grava 5 s, mostra o RMS em dBFS por canal e diz o que fazer. A faixa boa para
voz é **RMS entre -30 e -12 dBFS**, com picos abaixo de -3.

Ganho baixo é de longe a causa mais comum de transcrição ruim — adaptadores USB
genéricos costumam vir com o capture quase no mínimo:

```bash
alsamixer          # F4 (Capture), setas para cima, ligue "Mic Boost"
sudo alsactl store # salva para o próximo boot
```

Sinal saturado atrapalha tanto quanto sinal fraco; se o `voz mic` acusar
saturação, **baixe** o ganho.

Duas coisas que o projeto já resolve sozinho e vale saber:

- **Canais.** Muitos adaptadores USB (CM108 e similares) expõem entrada estéreo
  com o microfone ligado em só um dos canais. O projeto faz a média dos canais,
  então isso não te prejudica — e o `voz mic` avisa quando detecta um canal mudo.
- **Taxa.** Quando 16 kHz não está disponível, múltiplos exatos (48 kHz, 32 kHz)
  são preferidos a 44,1 kHz: a reamostragem 3:1 é limpa, enquanto 44100 → 16000
  tem razão 2,75625 e deixa artefato que o modelo pequeno sente. Para forçar:
  `voz run --rate 48000`.

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


---

## A matriz não desenha nada?

Ela agora vem **habilitada** por padrão (`[matrix] enabled = true`). Se estiver
desligada, `desenhar coração` avisa em vez de dizer que desenhou — antes o
comando mentia, porque a chamada era engolida em silêncio.

Confira os pinos em [`docs/ligacoes.md`](docs/ligacoes.md): DS=GPIO16,
SHCP=GPIO20, STCP=GPIO21. Eles mudaram na v0.3.0 porque colidiam com o LED RGB.

## A interface

`voz run` abre o Jarvis, uma interface de terminal que mostra os comandos
disponíveis, explica cada um e acompanha a execução ao vivo.

```
════════════════════════════════════════════════════════════════
   J A R V I S   central de comandos por voz      [ PRONTO ]  14:32:05
════════════════════════════════════════════════════════════════
 COMANDOS          │  LUZ RGB
                   │
 ▸ Luz RGB         │  LED RGB de ânodo comum. Aceita 15 cores,
   Servo           │  incluindo misturas como amarelo e turquesa.
   Distância       │
   Som             │    "ligar luz"
   Desenhos        │    "acender <cor>"
   Ditado          │      também: acender cor / ligar cor / luz cor
   Sistema         │    "trocar de cor"
══ ATIVIDADE ═══════════════════════════════════════════════════
  14:31:58  "acender azul" → Luz azul
  14:32:03  "monitorar distância" → Monitorando por 20 s
════════════════════════════════════════════════════════════════
  ENTER falar   ↑↓ navegar   TAB seção   / buscar   q sair
```

| Tecla | O que faz |
|---|---|
| `ENTER` | começa e termina a fala (push-to-talk) |
| `↑` `↓` | navega; `j`/`k` também funcionam |
| `TAB` | alterna entre a lista de grupos e a de comandos |
| `/` | busca um comando pelo nome |
| `q` | sai |

O botão físico do GPIO26 continua funcionando junto com o ENTER. Se o terminal
não suportar (`TERM` vazio, saída redirecionada), o Jarvis cai sozinho para o
modo texto — ou force com `--plain`.

Avisos e erros aparecem no painel ATIVIDADE em vez de sujarem a tela. O log
completo continua em `logs/centralvoz.log`.

## O sensor de distância não responde?

```bash
voz doctor
```

Ele faz uma leitura real com prazo. Se acusar "não respondeu no prazo", o ECHO
nunca subiu — confira, nesta ordem: VCC do HC-SR04 nos **5 V** (não 3,3 V), GND
comum com o Pi, TRIG/ECHO não trocados, e o **divisor de tensão** no ECHO.

Nenhuma leitura bloqueia mais que 1 segundo. Antes, um ECHO mudo prendia a
thread principal e nem Ctrl+C encerrava o programa.

**Se aparecer sempre 0.0 cm**, atualize: até a v0.3.1 o projeto usava o
`DistanceSensor` do gpiozero com `partial=True`, que devolve a média de uma fila
vazia — ou seja, zero — mesmo com o sensor perfeito. Agora o HC-SR04 é lido
diretamente, com prazo próprio em cada etapa, e uma leitura inválida vira erro
explícito em vez de um número inventado.

## Comandos longos rodam em segundo plano

`monitorar distância`, `modo festa` e `trocar de cor` não bloqueiam a central:
ela continua ouvindo enquanto eles rodam, e **`parar`** cancela a qualquer
momento. Um comando novo também cancela o anterior.

Isso é uma correção, não um enfeite — a versão anterior travava o loop principal
durante o monitoramento. Os detalhes estão em [`docs/CODE_REVIEW.md`](docs/CODE_REVIEW.md).

## Reconhecimento ruim? Leia isto antes de trocar de modelo

O ditado é naturalmente pior que os comandos: com gramática restrita o Vosk só
pode produzir ~400 frases conhecidas; no ditado ele escolhe entre ~200.000
palavras. Um modelo maior **não** é a solução no Pi 3 — o modelo grande de
português usa ~2,5 GB de RAM e a placa tem 1 GB.

Até a v0.4.0 havia um bug real por trás disso: a gramática era montada sem
acentos ("coracao"), e o léxico do modelo conhece "coração". Uma palavra
desconhecida faz o Vosk **rejeitar a gramática inteira** e cair no modo livre
sem avisar — daí comandos como "desenhar coração" nunca funcionarem.

`voz doctor` agora testa se a gramática é aceita. A análise completa, com a
tabela de memória e o que de fato melhora a acurácia, está em
[`docs/RECONHECIMENTO.md`](docs/RECONHECIMENTO.md).

## "LED" é difícil para o modelo em português

O modelo pequeno de português erra muito em siglas estrangeiras. Duas coisas
ajudam:

1. **Prefira "luz".** Todo comando de LED aceita "ligar luz", "acender luz
   azul", "piscar luz três vezes". O modelo acerta "luz" com facilidade.
2. **Já existem variantes fonéticas** ("lede", "lâmpada") registradas para o que
   o Vosk costuma transcrever no lugar de "led".

Se o seu Vosk insiste em transcrever alguma outra coisa, veja o que ele ouviu no
log e adicione essa grafia à lista de frases em `commands/router.py` — é uma
linha.

### Comandos em inglês

Existem variantes registradas ("turn on the light", "what time is it"), mas elas
**não entram na gramática do Vosk**: o modelo de português não tem essas
palavras no léxico e incluí-las faria o Vosk rejeitar a gramática inteira. Para
usá-las de fato, baixe um modelo em inglês e aponte para ele:

```bash
voz run --model models/vosk-model-small-en-us-0.15
```

## Como adicionar um comando novo

Três passos, sem tocar no controlador nem no loop de voz.

**1. A intenção** — em `centralvoz/commands/intents.py`:

```python
class Intent(str, Enum):
    ...
    CONTAR_RECADOS = "contar_recados"
```

**2. As frases** — no fim de `_install_defaults()`, em `commands/router.py`:

```python
r(Intent.CONTAR_RECADOS, "quantos recados", "contar recados",
  help_text="quantos recados")
```

Escreva 2–4 variações do jeito que as pessoas realmente falam. O casamento é
aproximado, então não precisa prever cada erro de transcrição.

**3. O que fazer** — em `commands/handlers.py`:

```python
@handles(Intent.CONTAR_RECADOS)
def _contar_recados(ctx: Context) -> Reply:
    total = ctx.storage.count_notes()
    return Reply(f"Voce tem {total} recado(s).", "Recados", str(total), icon="ok")
```

Pronto. O decorator registra sozinho, a gramática do Vosk passa a incluir as
frases novas, e `ajuda` já lista o comando.

### O objeto `Reply`

| Campo | Para quê |
|---|---|
| `message` | texto no terminal e no log |
| `lcd_title` / `lcd_detail` | duas linhas fixas no LCD |
| `lcd_text` | texto longo, pagina sozinho |
| `icon` | ícone na matriz (`ok`, `alerta`, `erro`, `coracao`, `casa`, `ouvindo`) |
| `repeatable` | `True` se o comando `repetir` deve trazê-lo de volta |
| `next_mode` | troca para `AppMode.DICTATION` |
| `stop` | encerra o programa |

### Comandos com parâmetro

Use o token `numero` na frase e informe os valores para a gramática:

```python
r(Intent.SERVO_ANGLE, "servo numero graus",
  help_text="servo N graus", numbers=(0, 45, 90, 180))
```

No handler, o valor chega em `ctx.number`. O roteador entende tanto
"servo trinta graus" quanto "servo 30 graus" — a conversão de português por
extenso está em `commands/numbers.py`.

A lista `numbers` existe porque o Vosk só reconhece palavras que estão na
gramática: sem "noventa" ali, ele nunca transcreveria "servo noventa graus".

### Testando sem falar

```bash
voz say "servo cento e oitenta graus"
voz text --mock
pytest
```
