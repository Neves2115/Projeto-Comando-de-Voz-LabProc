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
