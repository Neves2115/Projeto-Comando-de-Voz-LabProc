# Qualidade do reconhecimento — por que o ditado é pior

## O resumo

Comandos e ditado usam o **mesmo modelo**, mas em dois regimes diferentes:

| | Comandos | Ditado |
|---|---|---|
| Vocabulário possível | ~400 frases fixas | ~200.000 palavras |
| O decodificador pode errar para | só outro comando válido | qualquer palavra do português |
| Erro típico | raro | frequente |

Não é bug. A gramática restrita é uma **restrição de busca**: o Vosk fica
proibido de produzir qualquer coisa fora da lista. Mesmo com áudio ruim, ele é
forçado a escolher entre "ligar luz" e "abrir servo" — e acerta. No ditado essa
rede de segurança some.

Ou seja: o ditado não piorou o modelo. Ele apenas mostra a qualidade real do
modelo pequeno, que a gramática vinha escondendo.

## O bug que estava piorando tudo (corrigido na v0.4.1)

Havia um problema real por trás da impressão de que "às vezes até os comandos
ficam ruins".

A gramática era montada com o texto **sem acento** — "coracao", "distancia",
"musica". O léxico do modelo de português conhece "coração", "distância",
"música". Uma palavra fora do léxico faz o Vosk **rejeitar a gramática inteira**
e cair no reconhecimento livre.

Resultado: em parte das sessões o sistema rodava em modo livre sem avisar, e
todo comando ficava tão impreciso quanto o ditado. Isso explicava o "coração não
funciona de jeito nenhum" — a palavra literalmente não existia no vocabulário
que o decodificador podia produzir.

**Correção:** frases agora são escritas acentuadas e a gramática as usa como
estão. A comparação com o que foi ouvido continua ignorando acentos, então nada
quebra. E `voz doctor` passou a testar se o Vosk aceita a gramática.

## Vale um modelo maior?

**No Pi 3 B+, não.** A conta de memória decide:

| Modelo | Tamanho | RAM em uso | Cabe no Pi 3 (1 GB)? |
|---|---|---|---|
| `vosk-model-small-pt-0.3` | ~50 MB | ~180 MB | sim, com folga |
| `vosk-model-pt-fb-v0.1.1` | ~1,6 GB | ~2,5 GB | **não** |

O modelo grande nem carrega. Com swap, o carregamento leva minutos e cada
reconhecimento fica na casa das dezenas de segundos — inviável para comando de
voz.

Se você tiver um Pi 4 ou 5 com 4 GB+, aí sim vale, e é só apontar:

```bash
voz run --model models/vosk-model-pt-fb-v0.1.1
```

## O que realmente melhora o ditado no Pi 3

Em ordem de impacto:

**1. Nível de captura correto.** Já ajustado — RMS entre -20 e -15 dBFS, picos
abaixo de -3, saturação zero. Confira com `voz mic`.

**2. Taxa de amostragem.** Seu microfone só aceita 44100 Hz, e 44100 → 16000 tem
razão 2,75625: reamostragem não inteira, que deixa artefato. 48000 → 16000 é 3:1
exato. Se algum dispositivo aceitar 48 kHz ou 16 kHz nativo, prefira:

```bash
voz devices
voz mic --device default   # a camada plug do ALSA às vezes entrega 16 kHz
```

**3. Falar pausado e articulado.** Vale mais do que parece: o modelo pequeno tem
um modelo de linguagem fraco, então não "adivinha" pelo contexto como um grande
faria. Frases curtas, sem engolir sílabas.

**4. Ambiente.** Ventilador, TV e eco de sala derrubam a acurácia rápido. O
microfone a 15–25 cm da boca, ligeiramente de lado (evita o estouro dos "p" e
"t").

**5. Expectativa realista.** Para um modelo *small*, algo em torno de 70–85% de
palavras corretas em ditado livre é o esperado. Ele serve bem para recados
curtos ("comprar pão"), não para transcrever parágrafos.

## Se o ditado precisa ser bom

O caminho não é forçar o Pi 3. É separar as funções: comandos rodam offline no
Pi (que é o requisito do projeto), e o ditado, se precisar de qualidade alta,
usa um modelo maior em outra máquina.

Para o escopo do laboratório, o modelo pequeno com gramática restrita é a
escolha certa — e agora que a gramática funciona de verdade, os comandos devem
estar bem mais confiáveis.
