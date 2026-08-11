# Code review — v0.3.0

Revisão completa antes da entrega. Método: leitura módulo a módulo, `ruff` com
as regras de erro real (`E9,F,B,ARG,SIM,RUF`), teste de importação isolada de
cada módulo e execução ponta a ponta em modo simulado.

## Bugs encontrados e corrigidos

### 1. Import circular (crítico — quebrava em uso normal)

`commands.handlers` importava `app.tasks`; `app/__init__` importa `controller`,
que importa `commands.handlers`. Ciclo fechado.

```
ImportError: cannot import name 'HANDLERS' from partially initialized module
```

A suíte não pegava porque todos os testes importavam `app.controller` primeiro
— a ordem que funciona por acaso. Mas `import centralvoz.commands` puro
quebrava, e qualquer refatoração de ordem quebraria o programa.

**Correção:** `tasks.py` foi para o pacote raiz (`centralvoz/tasks.py`), fora de
`app/`. **Prevenção:** `tests/test_imports.py` importa cada módulo num
interpretador novo, via `subprocess`.

### 2. `monitorar distância` travava a central

O laço de 15 s rodava **dentro do handler**, bloqueando o loop principal.
Consequências em cadeia:

1. A central ficava surda durante todo o monitoramento.
2. Com gatilho de teclado, cada ENTER apertado nesse intervalo ficava na fila do
   stdin. Ao terminar, o loop consumia todos de uma vez, disparando capturas
   vazias em sequência — o "loop" que parecia travamento.
3. Não havia como cancelar: só Ctrl+C.

**Correção:** tarefas longas agora rodam em `BackgroundTask` com evento de
cancelamento; o loop principal continua ouvindo; `Trigger.flush()` descarta
ativações acumuladas; e existe o comando `parar`.

### 3. `config.example.toml` inválido

Após a troca do LED simples pelo RGB, o arquivo de exemplo ainda tinha
`leds = [17]`. Qualquer pessoa que fizesse `cp config.example.toml config.toml`
receberia `ValueError: Chave de configuracao desconhecida: 'leds'`.

**Correção:** arquivo atualizado. **Prevenção:** teste que carrega o
`config.example.toml` de verdade.

### 4. Conflito de pinos entre matriz e LED RGB

Os defaults da matriz (`5, 6, 13`) eram exatamente os pinos do LED RGB. Como a
matriz vem desabilitada, ninguém tinha notado — mas quem ligasse
`[matrix] enabled = true` teria dois periféricos disputando os mesmos GPIOs.

**Correção:** matriz movida para 16/20/21. **Prevenção:** teste que verifica
pinos duplicados e uso indevido de GPIO2/GPIO3 (reservados ao I2C).

### 5. `NullPeripheral` devolvia função onde se esperava valor

`__getattr__` retornava um no-op para **qualquer** atributo. Então
`hardware.leds.is_on` devolvia uma função — sempre *truthy*. Handlers tomavam
decisões erradas quando o periférico estava ausente (modo `voz hello`).

**Correção:** lista `_VALUE_ATTRS` com valores corretos para `is_on`, `color`,
`angle`, `simulated` e afins.

### 6. `blink` não era cancelável

O laço usava `time.sleep` sem checar o evento de parada, então `stop_effect()`
esperava o join inteiro. Agora usa `Event.wait()`, que retorna assim que
cancelado.

### 7. Modo festa durava ~1 s

Percorria quatro ícones com `sleep(0.35)`. Agora respeita
`behavior.party_duration_s` (12 s), com ciclo de cores, servo alternando e
contagem regressiva no LCD.

### 8. Menores

- `zip()` sem `strict=` no roteador — truncaria em silêncio se as listas
  divergissem.
- `hardware/led.py` virou código morto após a migração para RGB. Removido.
- 26 `# noqa` obsoletos removidos.

## Verificações que ficaram no CI

| Teste | O que previne |
|---|---|
| `test_importa_isolado` | import circular (parametrizado por módulo) |
| `test_todos_os_handlers_estao_registrados` | intenção sem handler cai em UNKNOWN calado |
| `test_toda_intencao_tem_pelo_menos_uma_frase` | comando que nunca pode ser dito |
| `test_config_exemplo_e_valido` | exemplo desatualizado |
| `test_pinos_nao_conflitam` | dois periféricos no mesmo GPIO |
| `test_monitorar_distancia_nao_bloqueia` | volta do bug do travamento |
| `test_modo_festa_respeita_a_duracao_configurada` | volta da festa curta |
| `test_mono_faz_media_dos_canais` | canal mudo em adaptador USB |
| `test_desempate_prefere_a_frase_mais_especifica` | parâmetro perdido para regra curta |
| `test_aceita_modelo_com_layout_compilado` | rejeição de modelo Vosk válido |

## O que revisei e está correto

- **Limpeza de recursos.** Todo periférico tem `close()` idempotente;
  `HardwareSet` é context manager; `SIGINT`/`SIGTERM` tratados; servo faz
  `detach()` automático.
- **Threads.** Todas `daemon=True`; `RLock` no LCD; `Event` para cancelamento;
  nenhum `join()` sem timeout.
- **Degradação.** Cada periférico cai para simulado individualmente, sempre com
  `logger.error` — nunca em silêncio.
- **I/O.** SQLite e I2C nunca derrubam a aplicação; falhas viram aviso.

## Limitações conhecidas (por decisão, não por descuido)

- **A matriz continua desabilitada por padrão.** A fiação dos 74HC595 varia
  entre versões do kit; ligar às cegas pode danificar o CI.
- **Variantes em inglês não entram na gramática do Vosk.** O modelo pequeno de
  português não tem essas palavras no léxico, e incluí-las faria o Vosk rejeitar
  a gramática inteira. Elas funcionam se você apontar `speech.model_path` para
  um modelo em inglês ou desligar `use_grammar`.
- **`RGBLED` usa PWM por software.** Para LED é irrelevante (jitter de
  microssegundos é invisível). Para servo importaria — por isso o servo continua
  no GPIO18, que tem PWM por hardware.
