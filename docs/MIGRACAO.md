# Migração — o que mudou e por quê

De `Projeto-Comando-de-Voz-LabProc` (v0.1.0) para `centralvoz` (v0.2.0).

## 1. Bugs corrigidos

### 1.1 `No module named 'lgpio'` / `PWM is not supported`

**Antes.** Ao criar `AngularServo(18)`, o gpiozero percorria as *pin factories*
na ordem `lgpio → RPi.GPIO → pigpio → native`. Sem nenhuma das três primeiras
instaladas, caía na `native`, que só faz GPIO digital. O LED acendia; o servo
quebrava.

**Agora.** `centralvoz/gpio_setup.py` verifica os backends **antes** de o
gpiozero criar a fábrica padrão, define `GPIOZERO_PIN_FACTORY` e, se nada
servir, aborta com o comando de instalação na tela. `voz doctor` faz o mesmo
diagnóstico sem tocar em hardware.

### 1.2 O microfone nunca era usado

**Antes.** `src/main.py` chamava `input()` e nada mais. `src/audio/recorder.py`
não era importado por nenhum módulo e `VoskSpeechRecognizer` nunca era
instanciado — código morto. Não havia caminho de execução que abrisse o
microfone.

**Agora.** `centralvoz/app/runner.py` é o loop push-to-talk de verdade:
`sounddevice.RawInputStream` → `KaldiRecognizer` → roteador → handlers.

### 1.3 Duas flags de mock desconectadas

**Antes.** `AppConfig.use_mock_hardware` (padrão `False`) não era lido em lugar
nenhum, e `main()` chamava `build_demo_controller(use_mock=True)` fixo no
código. Mudar a configuração não mudava nada.

**Agora.** Uma única fonte de verdade: `AppConfig.mock`, com precedência
CLI (`--mock`/`--real`) → env (`CENTRALVOZ_MOCK`) → `config.toml` → padrão.

### 1.4 Fallback silencioso para simulado

**Antes.** `if self.mock or GpioLED is None:` dentro de cada classe. Se o
gpiozero falhasse ao importar, o objeto virava mock **sem avisar** — você achava
que estava acionando o pino e não estava.

**Agora.** O backend é escolhido em um único lugar (`hardware/factory.py`),
sempre registrado no log, e cada periférico degrada individualmente com
`logger.error`. `hardware.summary()` imprime o estado real de cada um.

### 1.5 Roteamento por substring

**Antes.** `if "ligar led" in texto` — "**não** ligar led" acendia o LED. E
exigia transcrição literal perfeita, coisa que o modelo pequeno do Vosk
raramente entrega.

**Agora.** Normalização + janelas deslizantes com `difflib` (biblioteca padrão,
nada para compilar no Pi 3), pontuação de confiança, limiar configurável e
guarda de negação. Coberto por testes de regressão.

### 1.6 Todos os exemplos quebrados

**Antes.** Os seis arquivos em `examples/` importavam `central_voz_freenove.*`,
pacote que não existia. Nenhum rodava.

**Agora.** Cinco exemplos numerados na ordem de integração, todos executados
pela CI a cada push.

### 1.7 LCD e matriz sem implementação

**Antes.** Ambos tinham apenas `# Substituir pelo driver real`. Com
`mock=False` não faziam nada e não davam erro.

**Agora.** LCD: driver PCF8574/HD44780 completo em 4 bits, com autodescoberta de
endereço e paginação de texto longo. Matriz: bit-bang nos 74HC595 com thread de
multiplexação (desligada por padrão até você conferir a fiação).

### 1.8 Sem limpeza de recursos

**Antes.** `Ctrl+C` saía com traceback, GPIO em estado indefinido, servo
energizado zumbindo.

**Agora.** `HardwareSet` é context manager, `SIGINT`/`SIGTERM` são tratados, e o
servo faz `detach()` automático 0,8 s após cada movimento.

## 2. Requisitos do relatório que agora estão implementados

| Requisito (entrega 1) | Antes | Agora |
|---|---|---|
| Capturar áudio por microfone | ✗ código morto | ✓ `audio/microphone.py` |
| Reconhecer comandos curtos em português | ✗ nunca chamado | ✓ Vosk com gramática restrita |
| Executar ações no hardware | parcial | ✓ 17 intenções |
| Exibir o estado no LCD | ✗ sem driver | ✓ driver I2C real |
| Acionar LEDs e servomotor | parcial | ✓ |
| Ler o sensor de distância | ✓ | ✓ com filtro de mediana |
| **Registrar eventos em arquivo ou SQLite** | ✗ | ✓ `storage/db.py` + log rotativo |
| **Modo manual por botões ou teclado** | ✗ | ✓ `voz text` e `voz say` |

## 3. De-para de arquivos

| Antes | Agora |
|---|---|
| `src/config.py` | `centralvoz/config.py` (TOML + env + CLI) |
| `src/utils.py` | `centralvoz/utils.py` (+ `to_ascii`, `paginate`) |
| `src/hardware/base.py` | `centralvoz/hardware/base.py` (ABC + `NullPeripheral`) |
| `src/hardware/led.py` | `centralvoz/hardware/led.py` (`MockLeds` / `GpioLeds`) |
| `src/hardware/servo.py` | `centralvoz/hardware/servo.py` (+ auto-detach) |
| `src/hardware/lcd.py` | `centralvoz/hardware/lcd.py` (**driver I2C real**) |
| `src/hardware/distance.py` | `centralvoz/hardware/distance.py` (+ mediana) |
| `src/hardware/matrix.py` | `centralvoz/hardware/matrix.py` (**74HC595 real**) |
| — | `centralvoz/hardware/trigger.py` (**push-to-talk**) |
| — | `centralvoz/hardware/factory.py` (montagem única) |
| `src/audio/recorder.py` | `centralvoz/audio/microphone.py` (**streaming**) |
| `src/recognition/vosk_engine.py` | `centralvoz/speech/vosk_engine.py` (+ gramática, parciais) |
| `src/recognition/commands.py` | `centralvoz/commands/router.py` + `intents.py` |
| `src/app/controller.py` | `centralvoz/app/controller.py` + `commands/handlers.py` |
| `src/main.py` | `centralvoz/cli.py` + `app/runner.py` |
| — | `centralvoz/gpio_setup.py`, `doctor.py`, `logging_setup.py`, `storage/db.py` |

## 4. Comandos novos

Além dos oito originais: `piscar led`, `varrer servo`, `monitorar distância`,
**`transcrever` (ditado no LCD)**, `parar ditado`, `ler recados`, `repetir`,
`que horas são`, `status do sistema`, `ajuda`, `desligar sistema`.

## 5. O que ficou de fora, e por quê

- **Wake word contínua.** Você escolheu push-to-talk. O botão gasta menos CPU no
  Pi 3 e elimina falso disparo na apresentação. Se quiser adicionar depois, o
  ponto de extensão é `hardware/trigger.py`: basta uma classe nova com a mesma
  interface, sem tocar no resto.
- **Matriz habilitada por padrão.** A fiação dos 74HC595 muda entre versões do
  kit. Confira `docs/ligacoes.md` e ligue com `[matrix] enabled = true`.
- **`rapidfuzz`** para o casamento aproximado. Tem wheel para aarch64, mas em
  Pi 3 de 32 bits (armv7l) precisaria compilar. O `difflib` da biblioteca padrão
  resolve com folga neste volume de frases.
