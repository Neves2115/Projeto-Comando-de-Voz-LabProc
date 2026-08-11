import pytest

from centralvoz.commands.intents import Intent
from centralvoz.commands.router import CommandRouter


@pytest.fixture
def router() -> CommandRouter:
    return CommandRouter()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ligar led", Intent.LED_ON),
        ("Ligar LED", Intent.LED_ON),
        ("acender a luz", Intent.LED_ON),
        ("desligar led", Intent.LED_OFF),
        ("abrir servo", Intent.SERVO_OPEN),
        ("fechar a porta", Intent.SERVO_CLOSE),
        ("mostrar distancia", Intent.DISTANCE_READ),
        ("mostrar distância", Intent.DISTANCE_READ),
        ("modo alerta", Intent.DISTANCE_MONITOR),
        ("transcrever", Intent.DICTATION_START),
        ("que horas sao", Intent.CLOCK),
        ("ajuda", Intent.HELP),
    ],
)
def test_comandos_exatos(router: CommandRouter, text: str, expected: Intent) -> None:
    assert router.route(text).intent is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Erros tipicos do Vosk com o modelo pequeno.
        ("ligar lede", Intent.LED_ON),
        ("liga a luz", Intent.LED_ON),
        ("abre o servo", Intent.SERVO_OPEN),
        ("qual a distancia", Intent.DISTANCE_READ),
    ],
)
def test_tolera_transcricao_imperfeita(
    router: CommandRouter, text: str, expected: Intent
) -> None:
    match = router.route(text)
    assert match.intent is expected
    assert 0.0 < match.score <= 1.0


def test_negacao_nao_dispara_comando(router: CommandRouter) -> None:
    """Regressao: o roteador antigo acendia o LED com 'nao ligar led'."""
    assert router.route("nao ligar led").intent is Intent.UNKNOWN
    assert router.route("não ligar led").intent is Intent.UNKNOWN


def test_texto_irrelevante_vira_unknown(router: CommandRouter) -> None:
    assert router.route("o gato subiu no telhado").intent is Intent.UNKNOWN
    assert router.route("").intent is Intent.UNKNOWN


def test_score_perfeito_em_frase_exata(router: CommandRouter) -> None:
    assert router.route("ligar led").score == 1.0


def test_vocabulario_para_gramatica(router: CommandRouter) -> None:
    vocab = router.vocabulary()
    assert "ligar led" in vocab
    assert all(v == v.lower() for v in vocab)
    assert len(vocab) == len(set(vocab))


def test_limiar_configuravel() -> None:
    exigente = CommandRouter(threshold=0.99)
    assert exigente.route("ligar lede").intent is Intent.UNKNOWN
    assert exigente.route("ligar led").intent is Intent.LED_ON


# --------------------------------------------------------------------------- #
# Comandos com parametro numerico
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "esperado"),
    [
        ("servo trinta graus", 30),
        ("servo noventa graus", 90),
        ("servo cento e oitenta graus", 180),
        ("colocar servo em quarenta e cinco graus", 45),
        ("servo 45 graus", 45),
    ],
)
def test_servo_extrai_o_angulo(router: CommandRouter, text: str, esperado: int) -> None:
    match = router.route(text)
    assert match.intent is Intent.SERVO_ANGLE
    assert match.number == esperado


def test_desempate_prefere_a_frase_mais_especifica(router: CommandRouter) -> None:
    """Regressao: 'piscar led N vezes' nao pode perder para 'piscar led'."""
    assert router.route("piscar led").intent is Intent.LED_BLINK

    match = router.route("piscar led cinco vezes")
    assert match.intent is Intent.LED_BLINK_N
    assert match.number == 5


def test_comando_sem_numero_nao_ganha_parametro(router: CommandRouter) -> None:
    assert router.route("ligar led").number is None


def test_gramatica_expande_frases_com_parametro(router: CommandRouter) -> None:
    vocab = router.vocabulary()
    # O Vosk precisa dos numeros por extenso no vocabulario.
    assert "servo noventa graus" in vocab
    assert "servo cento e oitenta graus" in vocab
    # O placeholder nunca pode vazar para a gramatica.
    assert not any("numero" in frase for frase in vocab)


def test_novos_comandos_roteiam(router: CommandRouter) -> None:
    assert router.route("modo festa").intent is Intent.PARTY_MODE
    assert router.route("desenhar coracao").intent is Intent.MATRIX_DRAW
    assert router.route("apagar recados").intent is Intent.NOTES_CLEAR
