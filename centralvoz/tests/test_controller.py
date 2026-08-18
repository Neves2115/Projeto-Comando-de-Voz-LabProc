import time

import pytest

from centralvoz.app.controller import VoiceCommandController
from centralvoz.commands.intents import AppMode
from centralvoz.config import AppConfig
from centralvoz.hardware.factory import build_hardware
from centralvoz.storage.db import Storage


@pytest.fixture
def controller(tmp_path):
    config = AppConfig(mock=True, log_dir=tmp_path, db_path=tmp_path / "test.sqlite3")
    hardware = build_hardware(config)
    storage = Storage(config.db_path).open()
    yield VoiceCommandController(config, hardware, storage)
    storage.close()
    hardware.close()


def test_liga_e_desliga_led(controller) -> None:
    controller.handle_text("ligar led")
    assert controller.hardware.leds.is_on is True

    controller.handle_text("desligar led")
    assert controller.hardware.leds.is_on is False


def test_servo_vai_para_os_angulos_configurados(controller) -> None:
    controller.handle_text("abrir servo")
    assert controller.hardware.servo.angle == pytest.approx(90.0)

    controller.handle_text("fechar servo")
    assert controller.hardware.servo.angle == pytest.approx(0.0)


def test_lcd_recebe_a_leitura_de_distancia(controller) -> None:
    controller.hardware.distance.set_value(15.0)
    reply = controller.handle_text("mostrar distancia")

    assert "cm" in reply.message
    assert "Distancia" in controller.hardware.lcd.render()[0]


def test_comando_desconhecido_nao_quebra(controller) -> None:
    reply = controller.handle_text("faz um bolo de cenoura")
    assert "entendi" in reply.message.lower()
    assert "NAO ENTENDI" in controller.hardware.lcd.render()[0].upper()


def test_modo_ditado_grava_recado_e_mostra_no_lcd(controller) -> None:
    controller.handle_text("transcrever")
    assert controller.mode is AppMode.DICTATION

    controller.handle_text("comprar pao e leite amanha cedo")
    notas = controller.storage.recent_notes()
    assert notas and notas[0].text == "comprar pao e leite amanha cedo"

    # O texto e maior que 16 colunas: precisa aparecer paginado.
    assert any(pedaco in "".join(controller.hardware.lcd.render()) for pedaco in ("comprar", "pao"))


def test_sai_do_modo_ditado(controller) -> None:
    controller.handle_text("transcrever")
    assert controller.mode is AppMode.DICTATION

    controller.handle_text("parar ditado")
    assert controller.mode is AppMode.COMMAND


def test_ditado_nao_confunde_frase_comum_com_comando(controller) -> None:
    """No ditado, 'ligar led' e texto, nao comando."""
    controller.handle_text("transcrever")
    controller.handle_text("preciso ligar led amanha")

    assert controller.mode is AppMode.DICTATION
    assert controller.hardware.leds.is_on is False


def test_repetir_ultima_transcricao(controller) -> None:
    controller.handle_text("transcrever")
    controller.handle_text("reuniao as tres horas")
    controller.handle_text("parar ditado")

    reply = controller.handle_text("repetir")
    assert "reuniao as tres horas" in reply.message


def test_eventos_sao_persistidos(controller) -> None:
    controller.handle_text("ligar led")
    controller.handle_text("que horas sao")

    rows = controller.storage._conn.execute("SELECT intent FROM events").fetchall()
    intents = {row[0] for row in rows}
    assert "led_on" in intents
    assert "clock" in intents


def test_gramatica_muda_conforme_o_modo(controller) -> None:
    assert controller.grammar() is not None  # modo comando: vocabulario fechado
    controller.handle_text("transcrever")
    assert controller.grammar() is None  # ditado: reconhecimento livre


def test_shutdown_sinaliza_parada(controller) -> None:
    assert controller.handle_text("desligar sistema").stop is True


def test_servo_vai_para_o_angulo_falado(controller) -> None:
    controller.handle_text("servo cento e vinte graus")
    assert controller.hardware.servo.angle == pytest.approx(120.0)


def test_angulo_fora_da_faixa_e_limitado(controller) -> None:
    controller.handle_text("servo trezentos graus")
    assert controller.hardware.servo.angle <= 180.0


def test_apagar_recados(controller) -> None:
    controller.handle_text("transcrever")
    controller.handle_text("comprar cafe")
    controller.handle_text("parar ditado")
    assert controller.storage.count_notes() >= 1

    controller.handle_text("apagar recados")
    assert controller.storage.count_notes() == 0


# --------------------------------------------------------------------------- #
# LED RGB
# --------------------------------------------------------------------------- #


def test_acende_cor_nomeada(controller) -> None:
    controller.handle_text("acender vermelho")
    assert controller.hardware.leds.color == (1.0, 0.0, 0.0)
    assert controller.hardware.leds.color_name == "vermelho"


def test_cor_misturada(controller) -> None:
    """Amarelo e vermelho + verde, sem azul."""
    controller.handle_text("acender amarelo")
    r, g, b = controller.hardware.leds.color
    assert r > 0 and g > 0 and b == 0


def test_cor_com_genero_flexionado(controller) -> None:
    controller.handle_text("ligar luz amarela")
    assert controller.hardware.leds.color_name == "amarelo"


def test_desligar_apaga_todos_os_canais(controller) -> None:
    controller.handle_text("acender azul")
    assert controller.hardware.leds.is_on is True

    controller.handle_text("desligar luz")
    assert controller.hardware.leds.is_on is False
    assert controller.hardware.leds.color == (0.0, 0.0, 0.0)


def test_brilho_escala_a_cor(controller) -> None:
    controller.handle_text("acender vermelho")
    controller.handle_text("brilho cinquenta por cento")
    r, _, _ = controller.hardware.leds.color
    assert 0.4 < r < 0.6


def test_cor_desconhecida_acende_branco(controller) -> None:
    """'acender bege' nao tem cor conhecida: cai em LED_ON e acende branco."""
    controller.handle_text("acender bege")
    assert controller.hardware.leds.is_on is True


def test_handler_de_cor_sem_cor_pede_esclarecimento(controller) -> None:
    from centralvoz.commands.handlers import HANDLERS
    from centralvoz.commands.intents import Intent

    controller.context.color = None
    reply = HANDLERS[Intent.LED_COLOR](controller.context)

    assert controller.hardware.leds.is_on is False
    assert "cor" in reply.message.lower()


# --------------------------------------------------------------------------- #
# Tarefas em segundo plano
# --------------------------------------------------------------------------- #


def test_monitorar_distancia_nao_bloqueia(controller) -> None:
    """Regressao: o monitor rodava 15 s dentro do handler e travava o loop."""
    import time

    inicio = time.monotonic()
    reply = controller.handle_text("monitorar distancia")
    decorrido = time.monotonic() - inicio

    # Retorna quase imediatamente, com a tarefa rodando em segundo plano.
    assert decorrido < 1.0
    assert controller.task.running is True
    assert "parar" in reply.message.lower()

    controller.task.cancel()


def test_parar_cancela_a_tarefa(controller) -> None:
    controller.handle_text("monitorar distancia")
    assert controller.task.running is True

    reply = controller.handle_text("parar")
    assert controller.task.running is False
    assert "cancelado" in reply.message.lower()


def test_parar_sem_tarefa_nao_quebra(controller) -> None:
    reply = controller.handle_text("parar")
    assert "nada" in reply.message.lower()


def test_novo_comando_cancela_a_tarefa_anterior(controller) -> None:
    controller.handle_text("modo festa")
    assert controller.task.running is True

    controller.handle_text("monitorar distancia")
    assert controller.task.label == "monitor de distancia"
    controller.task.cancel()


def test_modo_festa_respeita_a_duracao_configurada(controller) -> None:
    """Regressao: a festa durava ~1 s porque so percorria quatro icones."""
    assert controller.config.behavior.party_duration_s >= 10.0

    reply = controller.handle_text("modo festa")
    assert controller.task.running is True
    assert "festa" in reply.message.lower()
    controller.task.cancel()


def test_close_cancela_tudo(controller) -> None:
    controller.handle_text("monitorar distancia")
    controller.close()
    assert controller.task.running is False


def test_sensor_mudo_nao_trava_o_comando(controller) -> None:
    """Regressao: 'mostrar distancia' congelava a central inteira."""
    import time

    sensor = controller.hardware.distance
    sensor.simulate_timeout = True
    sensor.faulty = True  # ja diagnosticado como mudo em leituras anteriores

    inicio = time.monotonic()
    reply = controller.handle_text("mostrar distancia")
    decorrido = time.monotonic() - inicio

    assert decorrido < 3.0
    texto = reply.message.lower()
    assert "fiacao" in texto or "respondeu" in texto or "sensor" in texto
    assert reply.icon == "erro"


def test_monitor_desiste_quando_o_sensor_esta_mudo(controller) -> None:
    controller.hardware.distance.simulate_timeout = True
    controller.handle_text("monitorar distancia")

    # A tarefa tem que morrer sozinha em vez de insistir por 20 s.
    for _ in range(60):
        if not controller.task.running:
            break
        time.sleep(0.1)

    assert controller.task.running is False


# --------------------------------------------------------------------------- #
# Buzzers
# --------------------------------------------------------------------------- #


def test_apitar_toca_no_buzzer(controller) -> None:
    reply = controller.handle_text("apitar")
    time.sleep(0.5)
    assert controller.hardware.buzzers.active.history
    assert "bipe" in reply.message.lower()


def test_melodia_vem_da_fala(controller) -> None:
    reply = controller.handle_text("tocar parabens")
    assert "parabens" in reply.message.lower()

    time.sleep(0.5)
    # O passivo e o unico que reproduz notas distintas.
    assert len(set(controller.hardware.buzzers.passive.history)) > 1
    controller.hardware.buzzers.stop()


def test_alarme_roda_em_segundo_plano_e_para(controller) -> None:
    reply = controller.handle_text("tocar alarme")
    assert controller.task.running is True
    assert "parar" in reply.message.lower()

    controller.handle_text("silenciar")
    assert controller.task.running is False


def test_sem_buzzer_avisa(controller) -> None:
    from centralvoz.hardware.buzzer import BuzzerPair

    controller.hardware.buzzers = BuzzerPair(None, None)
    reply = controller.handle_text("apitar")
    assert "buzzer" in reply.message.lower()
    assert reply.icon == "alerta"


def test_matriz_desativada_avisa_em_vez_de_mentir(controller) -> None:
    """Regressao: dizia 'Desenhando coracao' sem nada acontecer."""
    from centralvoz.hardware.base import NullPeripheral

    controller.hardware.matrix = NullPeripheral("matriz", "desativada")
    reply = controller.handle_text("desenhar coracao")

    assert "matriz" in reply.message.lower()
    assert "config" in reply.message.lower()
    assert reply.icon == "alerta"


def test_desenho_funciona_com_matriz_ativa(controller) -> None:
    controller.handle_text("desenhar coracao")
    linhas = controller.hardware.matrix.render()
    assert any("#" in linha for linha in linhas)
