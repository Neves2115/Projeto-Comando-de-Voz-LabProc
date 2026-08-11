import pytest

from centralvoz.config import AppConfig
from centralvoz.gpio_setup import GpioUnavailable, configure_pin_factory, inspect_platform
from centralvoz.hardware.factory import build_hardware
from centralvoz.hardware.lcd import MockLcd
from centralvoz.hardware.matrix import MockMatrix, pattern_to_rows
from centralvoz.utils import fit, paginate, to_ascii


# --------------------------------------------------------------------------- #
# Utilitarios
# --------------------------------------------------------------------------- #


def test_fit_corta_e_completa() -> None:
    assert fit("abc", 5) == "abc  "
    assert fit("abcdefgh", 5) == "abcde"
    assert fit("", 3) == "   "


def test_to_ascii_preserva_caixa_e_pontuacao() -> None:
    assert to_ascii("Distância: 12,5 cm") == "Distancia: 12,5 cm"
    assert to_ascii("AÇÃO") == "ACAO"


def test_paginate_quebra_em_paginas_do_tamanho_do_display() -> None:
    texto = "comprar pao leite cafe e tambem passar na farmacia depois do almoco"
    paginas = paginate(texto, cols=16, rows=2)

    assert len(paginas) > 1
    assert all(len(p) == 2 for p in paginas)
    assert all(len(linha) <= 16 for pagina in paginas for linha in pagina)


def test_paginate_texto_vazio() -> None:
    assert paginate("", 16, 2) == [["", ""]]


# --------------------------------------------------------------------------- #
# LCD
# --------------------------------------------------------------------------- #


def test_lcd_mostra_duas_linhas() -> None:
    lcd = MockLcd(cols=16, rows=2)
    lcd.show_lines("Central", "pronto")

    linhas = lcd.render()
    assert linhas[0].strip() == "Central"
    assert linhas[1].strip() == "pronto"
    assert all(len(linha) == 16 for linha in linhas)


def test_lcd_corta_texto_maior_que_o_display() -> None:
    lcd = MockLcd(cols=16, rows=2)
    lcd.show_lines("uma linha absurdamente longa demais", "")
    assert len(lcd.render()[0]) == 16


def test_lcd_pagina_texto_longo() -> None:
    lcd = MockLcd(cols=16, rows=2, page_delay_s=0.05)
    lcd.show_text("um texto bem maior do que cabe em dezesseis por duas colunas")
    try:
        assert "".join(lcd.render()).strip() != ""
    finally:
        lcd.close()


def test_lcd_clear_esvazia_o_buffer() -> None:
    lcd = MockLcd(cols=16, rows=2)
    lcd.show_lines("algo", "aqui")
    lcd.clear()
    assert "".join(lcd.render()).strip() == ""


# --------------------------------------------------------------------------- #
# Matriz
# --------------------------------------------------------------------------- #


def test_pattern_to_rows_converte_para_bytes() -> None:
    linhas = pattern_to_rows(["#" * 8] + ["." * 8] * 7)
    assert linhas[0] == 0xFF
    assert linhas[1] == 0x00
    assert len(linhas) == 8


def test_pattern_to_rows_rejeita_tamanho_errado() -> None:
    with pytest.raises(ValueError):
        pattern_to_rows(["........"] * 3)


def test_matriz_render_faz_ida_e_volta() -> None:
    matriz = MockMatrix()
    matriz.show_icon("alerta")
    assert len(matriz.render()) == 8
    matriz.clear()
    assert set("".join(matriz.render())) == {"."}


# --------------------------------------------------------------------------- #
# Plataforma
# --------------------------------------------------------------------------- #


def test_inspect_platform_nao_explode() -> None:
    info = inspect_platform()
    assert isinstance(info.available_factories, tuple)
    assert "native" in info.available_factories


def test_configure_pin_factory_falha_com_mensagem_util_fora_do_pi() -> None:
    if inspect_platform().is_raspberry_pi:
        pytest.skip("rodando em um Raspberry Pi de verdade")

    with pytest.raises(GpioUnavailable) as exc:
        configure_pin_factory()
    assert "mock" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# Configuracao
# --------------------------------------------------------------------------- #


def test_config_le_toml(tmp_path) -> None:
    arquivo = tmp_path / "config.toml"
    arquivo.write_text(
        """
mock = true

[pins]
rgb_red = 5
rgb_green = 6
servo = 12

[lcd]
address = "0x3f"

[behavior]
servo_open_angle = 120.0
"""
    )
    config = AppConfig.load(arquivo)

    assert config.mock is True
    assert config.pins.rgb_red == 5
    assert config.pins.rgb_green == 6
    assert config.pins.servo == 12
    assert config.lcd.address == 0x3F
    assert config.behavior.servo_open_angle == 120.0


def test_config_rejeita_chave_desconhecida(tmp_path) -> None:
    arquivo = tmp_path / "config.toml"
    arquivo.write_text("chave_que_nao_existe = 1\n")
    with pytest.raises(ValueError):
        AppConfig.load(arquivo)


def test_overrides_tem_prioridade(tmp_path) -> None:
    arquivo = tmp_path / "config.toml"
    arquivo.write_text("mock = false\n")
    assert AppConfig.load(arquivo, overrides={"mock": True}).mock is True


# --------------------------------------------------------------------------- #
# Modo minimo (usado pelo `voz hello`)
# --------------------------------------------------------------------------- #


def test_modo_minimo_liga_so_lcd_e_gatilho(tmp_path) -> None:
    """`voz hello` nao pode depender de GPIO: o LCD I2C fala por smbus2."""
    config = AppConfig(mock=False, trigger="keyboard", log_dir=tmp_path)
    config.lcd.enabled = False  # sem I2C neste ambiente de teste

    hardware = build_hardware(config, minimal=True)
    try:
        # LED, servo, sensor e matriz viram no-ops silenciosos.
        hardware.leds.on()
        hardware.servo.move_to(90)
        hardware.matrix.show_icon("ok")

        assert hardware.lcd is not None
        hardware.lcd.show_lines("OLA MUNDO", "Central de Voz")
        assert hardware.lcd.render()[0].strip() == "OLA MUNDO"
    finally:
        hardware.close()


def test_trigger_keyboard_nao_toca_no_gpio(tmp_path) -> None:
    from centralvoz.hardware.trigger import KeyboardTrigger

    config = AppConfig(mock=False, trigger="keyboard", log_dir=tmp_path)
    config.lcd.enabled = False

    hardware = build_hardware(config, minimal=True)
    try:
        assert isinstance(hardware.trigger, KeyboardTrigger)
    finally:
        hardware.close()


def test_config_aceita_trigger(tmp_path) -> None:
    arquivo = tmp_path / "config.toml"
    arquivo.write_text('trigger = "keyboard"\n')
    assert AppConfig.load(arquivo).trigger == "keyboard"


# --------------------------------------------------------------------------- #
# Modelo Vosk
# --------------------------------------------------------------------------- #


def test_resolve_model_dir_encontra_pasta_aninhada(tmp_path) -> None:
    """O zip do Vosk as vezes extrai criando um nivel a mais."""
    from centralvoz.speech.vosk_engine import resolve_model_dir

    raiz = tmp_path / "vosk-model-small-pt-0.3"
    interno = raiz / "vosk-model-small-pt-0.3"
    for sub in ("am", "conf", "graph"):
        (interno / sub).mkdir(parents=True)

    assert resolve_model_dir(raiz) == interno


def test_resolve_model_dir_aceita_pasta_direta(tmp_path) -> None:
    from centralvoz.speech.vosk_engine import resolve_model_dir

    modelo = tmp_path / "modelo"
    for sub in ("am", "conf", "graph"):
        (modelo / sub).mkdir(parents=True)

    assert resolve_model_dir(modelo) == modelo


def test_resolve_model_dir_rejeita_pasta_irrelevante(tmp_path) -> None:
    from centralvoz.speech.vosk_engine import resolve_model_dir

    (tmp_path / "lixo").mkdir()
    assert resolve_model_dir(tmp_path / "lixo") is None
    assert resolve_model_dir(tmp_path / "nao-existe") is None


def _criar_modelo_compilado(raiz):
    """Layout do vosk-model-small-pt-0.3: tudo na raiz, sem am/conf/graph."""
    (raiz / "ivector").mkdir(parents=True)
    for nome in (
        "final.mdl", "Gr.fst", "HCLr.fst", "mfcc.conf",
        "phones.txt", "README", "disambig_tid.int", "word_boundary.int",
    ):
        (raiz / nome).write_text("x")
    return raiz


def test_aceita_modelo_com_layout_compilado(tmp_path) -> None:
    """Regressao: o modelo small de portugues nao tem am/conf/graph."""
    from centralvoz.speech.vosk_engine import looks_like_model, resolve_model_dir

    modelo = _criar_modelo_compilado(tmp_path / "vosk-model-small-pt-0.3")
    assert looks_like_model(modelo) is True
    assert resolve_model_dir(modelo) == modelo


def test_aceita_modelo_compilado_em_subpasta(tmp_path) -> None:
    from centralvoz.speech.vosk_engine import resolve_model_dir

    raiz = tmp_path / "vosk-model-small-pt-0.3"
    interno = _criar_modelo_compilado(raiz / "vosk-model-small-pt-0.3")
    assert resolve_model_dir(raiz) == interno


def test_pasta_com_arquivos_soltos_nao_e_modelo(tmp_path) -> None:
    from centralvoz.speech.vosk_engine import looks_like_model

    solta = tmp_path / "qualquer"
    solta.mkdir()
    (solta / "README").write_text("x")
    (solta / "notas.txt").write_text("x")
    assert looks_like_model(solta) is False


# --------------------------------------------------------------------------- #
# Audio
# --------------------------------------------------------------------------- #


def test_mono_faz_media_dos_canais() -> None:
    """Regressao: pegar so o canal 0 gravava silencio em adaptadores USB
    que ligam o microfone em apenas um dos canais."""
    import array

    from centralvoz.audio.microphone import _to_mono

    # canal 0 mudo, canal 1 com sinal
    estereo = array.array("h", [0, 8000, 0, -8000]).tobytes()
    mono = array.array("h")
    mono.frombytes(_to_mono(estereo, 2))

    assert mono.tolist() == [4000, -4000]
    assert any(v != 0 for v in mono)


def test_mono_nao_altera_audio_de_um_canal() -> None:
    import array

    from centralvoz.audio.microphone import _to_mono

    dados = array.array("h", [1, -2, 3]).tobytes()
    assert _to_mono(dados, 1) == dados


def test_analyze_levels_detecta_canal_mudo() -> None:
    import array

    from centralvoz.audio.microphone import analyze_levels

    estereo = array.array("h", [0, 16000] * 50).tobytes()
    niveis = analyze_levels(estereo, 2)

    assert niveis[0]["rms_dbfs"] < -100      # canal mudo
    assert niveis[1]["rms_dbfs"] > -20       # canal com sinal


def test_taxas_preferem_multiplos_exatos_de_16k() -> None:
    """44100 -> 16000 nao e razao inteira e degrada mais que 48000 -> 16000."""
    from centralvoz.audio.microphone import CANDIDATE_RATES

    assert CANDIDATE_RATES[0] == 16000
    assert CANDIDATE_RATES.index(48000) < CANDIDATE_RATES.index(44100)
    assert CANDIDATE_RATES.index(32000) < CANDIDATE_RATES.index(44100)


# --------------------------------------------------------------------------- #
# Sensor de distancia: timeout
# --------------------------------------------------------------------------- #


def test_leitura_com_sensor_mudo_devolve_none_rapido() -> None:
    """Regressao: o gpiozero bloqueia para sempre quando o ECHO nao sobe.

    Isso prendia a thread principal, congelava o LCD em 'Processando...' e
    tornava o Ctrl+C inutil.
    """
    import time

    from centralvoz.hardware.distance import MockDistanceSensor

    sensor = MockDistanceSensor(23, 24)
    sensor.simulate_timeout = True

    inicio = time.monotonic()
    valor = sensor.read_cm(samples=1)
    decorrido = time.monotonic() - inicio

    assert valor is None
    assert decorrido < 3.0
    assert sensor.faulty is True


def test_leitura_normal_continua_funcionando() -> None:
    from centralvoz.hardware.distance import MockDistanceSensor

    sensor = MockDistanceSensor(23, 24, value_cm=30.0)
    valor = sensor.read_cm()

    assert valor is not None
    assert 25.0 < valor < 35.0
    assert sensor.faulty is False


def test_is_close_com_sensor_mudo_e_falso() -> None:
    from centralvoz.hardware.distance import MockDistanceSensor

    sensor = MockDistanceSensor(23, 24)
    sensor.simulate_timeout = True
    assert sensor.is_close(20.0) is False


# --------------------------------------------------------------------------- #
# Buzzers
# --------------------------------------------------------------------------- #


def test_melodia_toca_frequencias_distintas() -> None:
    from centralvoz.hardware.buzzer import MockBuzzer

    buzzer = MockBuzzer()
    buzzer.play("ok")
    assert len(set(buzzer.history)) >= 2
    assert all(f > 0 for f in buzzer.history)


def test_pausa_nao_gera_tom() -> None:
    from centralvoz.hardware.buzzer import MockBuzzer

    buzzer = MockBuzzer()
    buzzer.play((("do", 0.02), ("pausa", 0.02), ("mi", 0.02)))
    assert 0.0 not in buzzer.history


def test_stop_interrompe_melodia_longa() -> None:
    import time

    from centralvoz.hardware.buzzer import MockBuzzer

    buzzer = MockBuzzer()
    buzzer.play_async("parabens")
    time.sleep(0.1)

    inicio = time.monotonic()
    buzzer.stop()
    assert time.monotonic() - inicio < 2.0


def test_par_prefere_o_passivo_para_melodias() -> None:
    import time

    from centralvoz.hardware.buzzer import BuzzerPair, MockBuzzer

    ativo, passivo = MockBuzzer(), MockBuzzer()
    par = BuzzerPair(ativo, passivo)

    par.play("escala")
    time.sleep(0.4)
    par.stop()

    assert passivo.history and not ativo.history


def test_par_vazio_nao_quebra() -> None:
    from centralvoz.hardware.buzzer import BuzzerPair

    par = BuzzerPair(None, None)
    assert par.available is False
    par.beep()
    par.play("ok")
    par.stop()
    par.close()


def test_todas_as_melodias_usam_notas_validas() -> None:
    from centralvoz.hardware.buzzer import MELODIES, NOTES

    for nome, melodia in MELODIES.items():
        for nota, duracao in melodia:
            assert nota in NOTES, f"{nome}: nota desconhecida {nota!r}"
            assert duracao > 0, f"{nome}: duracao invalida"


def test_todos_os_icones_sao_validos() -> None:
    from centralvoz.hardware.matrix import ICONS, pattern_to_rows

    assert len(ICONS) >= 10
    for nome, padrao in ICONS.items():
        linhas = pattern_to_rows(padrao)
        assert len(linhas) == 8, nome
        assert any(v for v in linhas), f"{nome} esta todo apagado"


def test_resolve_icon_aceita_apelidos() -> None:
    from centralvoz.hardware.matrix import resolve_icon

    assert resolve_icon("carinha feliz") == "sorriso"
    assert resolve_icon("rosto triste") == "triste"
    assert resolve_icon("desenhar coracao") == "coracao"
    assert resolve_icon("mostrar nota") == "musica"
    assert resolve_icon("nada disso aqui") is None


def test_feedback_de_proximidade_escala() -> None:
    """Perto = vermelho e bipe rapido; longe = verde e bipe espacado."""
    from centralvoz.commands.handlers import _proximity_feedback

    perto_cor, perto_int = _proximity_feedback(10.0, 20.0)
    medio_cor, medio_int = _proximity_feedback(35.0, 20.0)
    longe_cor, longe_int = _proximity_feedback(120.0, 20.0)

    assert (perto_cor, medio_cor, longe_cor) == ("vermelho", "amarelo", "verde")
    assert perto_int < medio_int < longe_int
