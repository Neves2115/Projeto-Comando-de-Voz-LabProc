"""Traducao de texto reconhecido em intencao.

Problemas do roteador antigo, todos corrigidos aqui:

* `"ligar led" in texto` -> "**nao** ligar led" acendia o LED.
* Exigia transcricao literal perfeita. O Vosk entrega "ligar lede",
  "abre servo", "liga a luz"... e nada casava.
* Nao havia como saber o quao confiante o casamento foi.

A estrategia agora e: normaliza, quebra em tokens e procura cada frase-alvo em
janelas deslizantes do que foi ouvido, pontuando por similaridade (difflib, da
biblioteca padrao -- nada para compilar no Pi 3). O melhor resultado acima do
limiar vence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ..hardware.rgb import COLORS
from ..utils import normalize_text, tokens
from .intents import Intent
from .numbers import PLACEHOLDER, number_to_words, replace_numbers

#: Token que representa uma cor qualquer dentro de uma frase.
COLOR_SLOT = "cor"

NEGATIONS = {"nao", "nunca", "jamais", "para", "pare"}


@dataclass(frozen=True)
class Match:
    intent: Intent
    score: float
    heard: str
    phrase: str = ""
    #: Numero dito pelo usuario, quando o comando aceita parametro
    #: ("servo trinta graus" -> 30).
    number: int | None = None
    #: Cor dita pelo usuario ("acender azul" -> "azul").
    color: str | None = None

    @property
    def understood(self) -> bool:
        return self.intent is not Intent.UNKNOWN


@dataclass
class Rule:
    intent: Intent
    phrases: tuple[str, ...]
    #: Frase curta mostrada no comando "ajuda".
    help_text: str = ""
    #: Valores usados so para expandir a gramatica do Vosk quando a frase tem
    #: o token `numero`. O Vosk precisa ter "trinta" no vocabulario para
    #: conseguir reconhecer "servo trinta graus".
    numbers: tuple[int, ...] = ()
    #: False para frases que NAO devem entrar na gramatica do Vosk.
    #: Usado nas variantes em ingles: o modelo de portugues nao tem essas
    #: palavras no lexico, e incluir palavras desconhecidas faz o Vosk
    #: rejeitar a gramatica inteira.
    in_grammar: bool = True
    _token_phrases: list[list[str]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._token_phrases = [tokens(phrase) for phrase in self.phrases]


class CommandRouter:
    def __init__(self, threshold: float = 0.70) -> None:
        self.threshold = threshold
        self._rules: list[Rule] = []
        self._install_defaults()

    # -- registro ----------------------------------------------------- #

    def register(
        self,
        intent: Intent,
        *phrases: str,
        help_text: str = "",
        numbers: tuple[int, ...] = (),
        in_grammar: bool = True,
    ) -> None:
        """Registra um comando.

        Use o token `numero` na frase para aceitar parametro:
            register(Intent.SERVO_ANGLE, "servo numero graus", numbers=ANGULOS)
        """
        self._rules.append(
            Rule(
                intent=intent,
                phrases=phrases,
                help_text=help_text,
                numbers=numbers,
                in_grammar=in_grammar,
            )
        )

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    def vocabulary(self) -> list[str]:
        """Frases para a gramatica do Vosk (uma linha por variacao).

        Frases com parametro viram varias entradas concretas: "servo numero
        graus" com numbers=(0, 30, 90) gera "servo zero graus",
        "servo trinta graus" e "servo noventa graus".
        """
        phrases: set[str] = set()
        for rule in self._rules:
            if not rule.in_grammar:
                continue
            for phrase in rule.phrases:
                for expandida in _expand(normalize_text(phrase), rule.numbers):
                    phrases.add(expandida)
        return sorted(p for p in phrases if p)

    def help_lines(self) -> list[str]:
        return [rule.help_text for rule in self._rules if rule.help_text]

    # -- roteamento --------------------------------------------------- #

    def route(self, text: str) -> Match:
        heard = normalize_text(text)
        if not heard:
            return Match(Intent.UNKNOWN, 0.0, text)

        # Numeros viram um token unico ("trinta" -> "numero"), o que permite
        # que uma so regra cubra qualquer valor.
        spoken, numeros = replace_numbers(heard)
        numero = numeros[0] if numeros else None
        spoken, cor = _replace_color(spoken)
        best = Match(Intent.UNKNOWN, 0.0, text, number=numero, color=cor)
        best_size = 0

        for rule in self._rules:
            for phrase, phrase_tokens in zip(rule.phrases, rule._token_phrases, strict=True):
                if not phrase_tokens:
                    continue
                score, start = _best_window_score(spoken, phrase_tokens)

                # Desempate por especificidade: com a mesma pontuacao, vence a
                # frase mais longa. Sem isso, "piscar led cinco vezes" casaria
                # com "piscar led" (1.00) e o parametro seria perdido.
                if (score, len(phrase_tokens)) <= (best.score, best_size):
                    continue
                if _is_negated(spoken, start):
                    continue
                best = Match(rule.intent, round(score, 3), text, phrase, numero, cor)
                best_size = len(phrase_tokens)

        if best.score < self.threshold:
            return Match(Intent.UNKNOWN, best.score, text, number=numero, color=cor)
        return best

    # -- comandos padrao ---------------------------------------------- #

    #: Angulos oferecidos ao Vosk para "servo N graus".
    ANGULOS = (0, 15, 30, 45, 60, 90, 120, 135, 150, 180)
    #: Contagens oferecidas para "piscar led N vezes".
    CONTAGENS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)

    def _install_defaults(self) -> None:
        r = self.register

        # --- LED RGB -------------------------------------------------- #
        # "led" e uma sigla estrangeira e o modelo pequeno de portugues erra
        # muito nela. Por isso cada comando tem variantes com "luz" (palavra
        # comum, que o modelo acerta) e grafias foneticas do que o Vosk
        # costuma transcrever no lugar de "led": "lede", "lete", "leite".
        r(Intent.LED_ON, "ligar led", "acender led", "ligar luz", "acender a luz",
          "ligar lede", "acender lede", "ligar a lampada", "acender lampada",
          help_text="ligar luz")
        r(Intent.LED_OFF, "desligar led", "apagar led", "desligar luz",
          "apagar a luz", "desligar lede", "apagar lede", "apagar lampada",
          help_text="desligar luz")
        r(Intent.LED_BLINK, "piscar led", "piscar luz", "pisca pisca",
          "piscar lede", help_text="piscar luz")
        r(Intent.LED_BLINK_N, "piscar led numero vezes", "piscar numero vezes",
          "piscar luz numero vezes",
          help_text="piscar luz N vezes", numbers=self.CONTAGENS)

        # Cores. O slot `cor` casa com qualquer nome de COLORS, entao uma unica
        # regra cobre vermelho, amarelo, turquesa e todo o resto.
        r(Intent.LED_COLOR, "acender cor", "ligar cor", "luz cor", "led cor",
          "mudar para cor", "cor", "pintar de cor",
          # Variantes de 3 tokens: sem elas "ligar luz amarela" casaria com
          # "ligar luz" (LED_ON) e a cor seria ignorada. O desempate por
          # especificidade cuida do resto.
          "ligar luz cor", "acender luz cor", "ligar led cor", "acender led cor",
          "deixar a luz cor", "mudar a luz para cor", "acender a luz cor",
          help_text="acender <cor>")
        r(Intent.LED_CYCLE, "trocar de cor", "ciclo de cores", "arco iris",
          "passar as cores", "modo arco iris",
          help_text="trocar de cor")
        r(Intent.LED_BRIGHTNESS, "brilho numero por cento", "brilho numero",
          help_text="brilho N por cento", numbers=(10, 20, 30, 40, 50, 60, 70, 80, 90, 100))

        # --- Servo ---------------------------------------------------- #
        r(Intent.SERVO_OPEN, "abrir servo", "abrir porta", "girar servo",
          help_text="abrir servo")
        r(Intent.SERVO_CLOSE, "fechar servo", "fechar porta", "voltar servo",
          help_text="fechar servo")
        r(Intent.SERVO_SWEEP, "varrer servo", "girar tudo", "testar servo",
          help_text="varrer servo")
        r(Intent.SERVO_ANGLE, "servo numero graus", "girar servo para numero graus",
          "colocar servo em numero graus",
          help_text="servo N graus", numbers=self.ANGULOS)

        # --- Distancia ------------------------------------------------ #
        r(Intent.DISTANCE_READ, "mostrar distancia", "ler distancia", "ver distancia",
          "qual a distancia", help_text="mostrar distancia")
        r(Intent.DISTANCE_MONITOR, "monitorar distancia", "modo alerta", "ativar alerta",
          "vigiar distancia", help_text="monitorar distancia")
        r(Intent.STOP_TASK, "parar", "pare", "cancelar", "chega", "parar tudo",
          help_text="parar (cancela o que esta rodando)")

        # --- Buzzers -------------------------------------------------- #
        r(Intent.BUZZER_BEEP, "apitar", "bipar", "dar um bipe", "buzina",
          "tocar bipe", help_text="apitar")
        r(Intent.BUZZER_MELODY, "tocar musica", "tocar melodia", "tocar escala",
          "tocar parabens", "tocar uma musica", "cantar parabens",
          help_text="tocar musica")
        r(Intent.BUZZER_ALARM, "tocar alarme", "ligar alarme", "soar alarme",
          "modo alarme", "sirene", help_text="tocar alarme")
        r(Intent.BUZZER_SILENCE, "silenciar", "calar", "parar o som",
          "parar musica", "sem som", help_text="silenciar")

        # --- Ditado e recados ----------------------------------------- #
        r(Intent.DICTATION_START, "transcrever", "modo ditado", "anotar recado",
          "escrever no display", "tomar nota",
          help_text="transcrever (ditado no LCD)")
        r(Intent.DICTATION_STOP, "parar ditado", "encerrar ditado", "sair do ditado",
          help_text="parar ditado")
        r(Intent.NOTES_LIST, "ler recados", "mostrar recados", "listar notas",
          help_text="ler recados")
        r(Intent.NOTES_CLEAR, "apagar recados", "limpar recados", "esquecer tudo",
          help_text="apagar recados")
        r(Intent.REPEAT_LAST, "repetir", "repita", "de novo",
          help_text="repetir")

        # --- Sistema -------------------------------------------------- #
        r(Intent.CLOCK, "que horas sao", "mostrar hora", "ver as horas",
          help_text="que horas sao")
        r(Intent.SYSTEM_STATUS, "status do sistema", "temperatura da cpu", "ver status",
          help_text="status do sistema")
        r(Intent.HELP, "ajuda", "quais comandos", "listar comandos",
          help_text="ajuda")
        r(Intent.PARTY_MODE, "modo festa", "festa", "comemorar",
          help_text="modo festa")
        r(Intent.MATRIX_DRAW, "desenhar coracao", "desenhar casa", "desenhar alerta",
          "desenhar ok", "mostrar desenho",
          help_text="desenhar coracao/casa/alerta")
        r(Intent.CLEAR, "limpar tela", "limpar display", "apagar tudo",
          help_text="limpar tela")
        r(Intent.SHUTDOWN, "desligar sistema", "encerrar programa", "tchau",
          help_text="desligar sistema")

        self._install_english()

    def _install_english(self) -> None:
        """Variantes em ingles.

        `in_grammar=False` e essencial: o modelo pequeno de portugues nao tem
        estas palavras no lexico e nunca vai transcrevê-las. Elas ficam de fora
        da gramatica do Vosk (que rejeitaria o conjunto inteiro) mas continuam
        no casador -- entao funcionam se voce apontar `speech.model_path` para
        um modelo em ingles, ou desligar `speech.use_grammar`.
        """
        r = self.register
        g = {"in_grammar": False}

        r(Intent.LED_ON, "turn on the light", "turn on led", "lights on", **g)
        r(Intent.LED_OFF, "turn off the light", "turn off led", "lights off", **g)
        r(Intent.LED_BLINK, "blink the light", "blink led", **g)
        r(Intent.LED_COLOR, "set color cor", "change color to cor", **g)
        r(Intent.LED_CYCLE, "cycle colors", "rainbow mode", **g)
        r(Intent.SERVO_OPEN, "open the door", "open servo", **g)
        r(Intent.SERVO_CLOSE, "close the door", "close servo", **g)
        r(Intent.DISTANCE_READ, "show distance", "read distance", **g)
        r(Intent.DISTANCE_MONITOR, "monitor distance", "alert mode", **g)
        r(Intent.STOP_TASK, "stop", "cancel", **g)
        r(Intent.CLOCK, "what time is it", "show the time", **g)
        r(Intent.HELP, "help", "list commands", **g)
        r(Intent.PARTY_MODE, "party mode", **g)
        r(Intent.SHUTDOWN, "shut down", "goodbye", **g)
        r(Intent.BUZZER_BEEP, "beep", **g)
        r(Intent.BUZZER_ALARM, "sound the alarm", **g)
        r(Intent.BUZZER_SILENCE, "be quiet", "silence", **g)


# --------------------------------------------------------------------------- #
# Pontuacao
# --------------------------------------------------------------------------- #


def _best_window_score(spoken: list[str], phrase: list[str]) -> tuple[float, int]:
    """Melhor similaridade da frase-alvo em qualquer trecho do que foi ouvido.

    Retorna (score, indice_do_inicio_da_janela).
    """
    size = len(phrase)
    target = " ".join(phrase)

    # Caminho rapido: a frase aparece exatamente como sequencia de tokens.
    for start in range(len(spoken) - size + 1):
        if spoken[start : start + size] == phrase:
            return 1.0, start

    best_score = 0.0
    best_start = 0
    # Janelas do tamanho da frase e um pouco maiores/menores, para tolerar
    # palavras extras ("liga *a* luz") ou faltando.
    for window in {max(1, size - 1), size, size + 1}:
        for start in range(max(1, len(spoken) - window + 1)):
            candidate = " ".join(spoken[start : start + window])
            if not candidate:
                continue
            score = SequenceMatcher(None, target, candidate).ratio()
            if score > best_score:
                best_score, best_start = score, start

    return best_score, best_start


def _replace_color(spoken: list[str]) -> tuple[list[str], str | None]:
    """Troca o nome da cor pelo token `cor` e devolve qual era."""
    from ..hardware.rgb import resolve_color

    saida: list[str] = []
    encontrada: str | None = None
    for palavra in spoken:
        if encontrada is None and resolve_color(palavra) is not None:
            # Guarda o nome canonico ("vermelha" -> "vermelho").
            for nome, valor in COLORS.items():
                if resolve_color(palavra) == valor:
                    encontrada = nome
                    break
            saida.append(COLOR_SLOT)
        else:
            saida.append(palavra)
    return saida, encontrada


def _expand(phrase: str, numbers: tuple[int, ...]) -> list[str]:
    """Expande os slots `numero` e `cor` em frases concretas para a gramatica."""
    resultado = [phrase]

    if PLACEHOLDER in phrase.split():
        resultado = [
            frase.replace(PLACEHOLDER, number_to_words(valor))
            for frase in resultado
            for valor in (numbers or ())
        ]

    if COLOR_SLOT in phrase.split():
        resultado = [
            frase.replace(COLOR_SLOT, nome)
            for frase in resultado
            for nome in COLORS
            if nome != "preto"
        ]

    return [r for r in resultado if r and PLACEHOLDER not in r.split()]


def _is_negated(spoken: list[str], start: int) -> bool:
    """Verifica se ha uma negacao imediatamente antes do trecho casado."""
    return start > 0 and spoken[start - 1] in NEGATIONS
