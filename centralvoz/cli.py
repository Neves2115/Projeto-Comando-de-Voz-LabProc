"""Interface de linha de comando.

    voz doctor            diagnostico do ambiente (comece por aqui)
    voz devices           lista as entradas de audio
    voz selftest          testa os perifericos na ordem de integracao
    voz text              digita comandos, sem microfone
    voz say "ligar led"   executa um comando unico
    voz run               loop de voz completo (push-to-talk)

Qualquer subcomando aceita --mock para rodar sem hardware nenhum.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from .app.controller import VoiceCommandController
from .commands.intents import AppMode
from .app.runner import VoiceLoop
from .audio.microphone import AudioUnavailable, Microphone, list_input_devices
from .config import AppConfig
from .utils import ensure_dir
from .hardware.factory import build_hardware
from .logging_setup import setup_logging
from .speech.vosk_engine import SpeechUnavailable, VoskEngine
from .storage.db import Storage

logger = logging.getLogger(__name__)


def _add_global_options(parser: argparse.ArgumentParser) -> None:
    """Opcoes aceitas antes OU depois do subcomando.

    `argparse.SUPPRESS` e essencial aqui: sem ele, o subparser sobrescreveria
    com o proprio default o valor que o parser principal ja tinha lido.
    """
    parser.add_argument(
        "--config", type=Path, default=argparse.SUPPRESS, help="caminho do config.toml"
    )
    parser.add_argument(
        "--mock", action="store_true", default=argparse.SUPPRESS,
        help="simula todo o hardware",
    )
    parser.add_argument(
        "--real", action="store_true", default=argparse.SUPPRESS,
        help="forca hardware real",
    )
    parser.add_argument(
        "--pin-factory", choices=["lgpio", "pigpio", "rpigpio", "native"],
        default=argparse.SUPPRESS, help="backend de GPIO do gpiozero",
    )
    parser.add_argument(
        "--model", type=Path, default=argparse.SUPPRESS, help="pasta do modelo Vosk"
    )
    parser.add_argument(
        "--trigger", choices=["button", "keyboard"], default=argparse.SUPPRESS,
        help="como iniciar a escuta: botao no GPIO ou ENTER no teclado",
    )
    parser.add_argument(
        "--rate", type=int, default=argparse.SUPPRESS,
        help="forca a taxa de amostragem do microfone (ex.: 48000)",
    )
    parser.add_argument(
        "--device", default=argparse.SUPPRESS,
        help="indice do microfone (veja: voz devices)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=argparse.SUPPRESS,
        help="log em nivel DEBUG",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voz",
        description="Central de comandos por voz para Raspberry Pi + kit Freenove.",
    )
    _add_global_options(parser)

    comum = argparse.ArgumentParser(add_help=False)
    _add_global_options(comum)

    sub = parser.add_subparsers(dest="command", required=True, parser_class=lambda **kw: argparse.ArgumentParser(parents=[comum], **kw))
    sub.add_parser("doctor", help="verifica GPIO, I2C, microfone e modelo de fala")
    sub.add_parser(
        "hello",
        help="teste minimo: fale no microfone e veja o texto no LCD (so I2C, sem GPIO)",
    )
    sub.add_parser("devices", help="lista dispositivos de entrada de audio")
    mic = sub.add_parser(
        "mic", help="mede o nivel do microfone e diz se o ganho esta bom"
    )
    mic.add_argument("--seconds", type=float, default=5.0, help="duracao do teste")
    mic.add_argument("--save", action="store_true", help="salva o .wav gravado")
    sub.add_parser("selftest", help="aciona cada periferico em sequencia")
    sub.add_parser("text", help="loop de comandos digitados (sem microfone)")
    sub.add_parser("run", help="loop de voz com push-to-talk")

    say = sub.add_parser("say", help="executa um unico comando de texto")
    say.add_argument("text", nargs="+", help="o comando, ex.: voz say ligar led")

    return parser


def _config_from_args(args: argparse.Namespace) -> AppConfig:
    get = lambda nome, padrao=None: getattr(args, nome, padrao)

    overrides: dict = {}
    if get("mock"):
        overrides["mock"] = True
    if get("real"):
        overrides["mock"] = False
    if get("pin_factory"):
        overrides["pin_factory"] = get("pin_factory")
    if get("model"):
        overrides["speech"] = {"model_path": get("model")}
    if get("trigger"):
        overrides["trigger"] = get("trigger")
    if get("verbose"):
        overrides["log_level"] = "DEBUG"

    audio: dict = {}
    if get("rate"):
        audio["sample_rate"] = int(get("rate"))
    if get("device") is not None:
        valor = get("device")
        audio["input_device"] = int(valor) if str(valor).isdigit() else valor
    if audio:
        overrides["audio"] = audio

    return AppConfig.load(get("config"), overrides=overrides)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = _config_from_args(args)
    setup_logging(config.log_dir, config.log_level)

    if args.command == "doctor":
        from .doctor import print_report

        return print_report(config)

    if args.command == "devices":
        return _cmd_devices()

    if args.command == "mic":
        return _cmd_mic(config, args.seconds, args.save)

    if args.command == "hello":
        return _cmd_hello(config)
    if args.command == "selftest":
        return _cmd_selftest(config)
    if args.command == "text":
        return _cmd_text(config)
    if args.command == "say":
        return _cmd_say(config, " ".join(args.text))
    if args.command == "run":
        return _cmd_run(config)

    return 2


# --------------------------------------------------------------------------- #


def _cmd_devices() -> int:
    try:
        devices = list_input_devices()
    except AudioUnavailable as exc:
        print(exc)
        return 1
    if not devices:
        print("Nenhuma entrada de audio encontrada. Confira com: arecord -l")
        return 1
    print("\nEntradas de audio disponiveis:\n")
    for device in devices:
        taxas = device.get("rates") or []
        aceitas = ", ".join(f"{t}" for t in taxas) if taxas else "nenhuma testada com sucesso"
        print(f"  [{device['index']:>2}] {device['name']}")
        print(
            f"       {device['channels']} canal(is), padrao "
            f"{device['default_samplerate']:.0f} Hz"
        )
        print(f"       taxas aceitas: {aceitas}")
    print(
        "\nO projeto negocia a taxa sozinho. Para fixar, use config.toml:\n\n"
        "    [audio]\n    input_device = 2\n    sample_rate = 48000\n"
    )
    return 0


def _cmd_hello(config: AppConfig) -> int:
    """Teste minimo de ponta a ponta: microfone -> Vosk -> LCD.

    Deliberadamente nao usa LED, servo, sensor nem matriz. O LCD I2C fala por
    smbus2, entao este caminho funciona mesmo que o backend de GPIO esteja
    quebrado -- e assim da para isolar audio + I2C de qualquer problema de PWM.
    """
    # Sem botao fisico por padrao aqui: ENTER e suficiente para o primeiro teste.
    if config.trigger == "button":
        print("\nDica: se o botao ainda nao estiver ligado, use --trigger keyboard.\n")

    # --- etapa 1: o LCD sozinho -------------------------------------- #
    print("Etapa 1/3 - escrevendo no LCD...")
    hardware = build_hardware(config, minimal=True)
    lcd = hardware.lcd
    lcd.show_lines("OLA MUNDO", "Central de Voz")

    if lcd.simulated:
        print(
            "\n  [!] O LCD real nao respondeu; o que voce viu foi a simulacao acima.\n"
            "      Rode `voz doctor` e confira a secao 'LCD I2C'.\n"
        )
    else:
        print("      Confira: o display deve mostrar OLA MUNDO / Central de Voz.")
        print("      Se a luz acende mas nao aparece nada, gire o potenciometro")
        print("      de contraste no verso do modulo.\n")

    # --- etapa 2: microfone e modelo ---------------------------------- #
    print("Etapa 2/3 - abrindo o microfone e carregando o modelo de fala...")
    microphone = Microphone(config.audio)
    try:
        # check() primeiro: e ele que descobre a taxa que o microfone aceita,
        # e o Vosk precisa ser criado com essa mesma taxa.
        microphone.check()
        engine = VoskEngine(config.speech.model_path, microphone.sample_rate)
        engine.load()
    except (AudioUnavailable, SpeechUnavailable) as exc:
        lcd.show_lines("Sem microfone", "veja o terminal")
        hardware.close()
        print(f"\n[NAO DA PARA OUVIR AINDA]\n{exc}\n")
        return 1

    # --- etapa 3: falar e ver no LCD ---------------------------------- #
    print("Etapa 3/3 - fale alguma coisa. Tudo que voce disser vai para o LCD.")
    print("            Ctrl+C encerra.\n")

    # Ditado puro: reconhecimento livre, sem gramatica e sem sair sozinho.
    config.behavior.dictation_timeout_s = 86400

    with Storage(config.db_path) as storage:
        controller = VoiceCommandController(config, hardware, storage)
        controller.mode = AppMode.DICTATION
        loop = VoiceLoop(config, controller, engine, microphone)
        try:
            loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            hardware.close()

    print("\nTeste encerrado.")
    return 0


def _cmd_mic(config: AppConfig, seconds: float, save: bool) -> int:
    """Mede o nivel de captura. Reconhecimento ruim quase sempre e ganho baixo."""
    microphone = Microphone(config.audio)
    try:
        microphone.check()
    except AudioUnavailable as exc:
        print(f"\n{exc}\n")
        return 1

    print(
        f"\nGravando {seconds:.0f} s a {microphone.sample_rate} Hz "
        f"({microphone.device_channels} canal(is)).\n"
        "FALE NORMALMENTE, na distancia que voce usaria de verdade.\n"
    )
    resultado = microphone.measure(seconds)
    niveis = resultado["levels"]

    print(f"Capturados {resultado['seconds']:.1f} s.\n")
    for indice, nivel in enumerate(niveis):
        print(
            f"  canal {indice}: RMS {nivel['rms_dbfs']:6.1f} dBFS   "
            f"pico {nivel['peak_dbfs']:6.1f} dBFS   "
            f"saturacao {nivel['clip_pct']:.2f}%"
        )

    melhor = max(niveis, key=lambda n: n["rms_dbfs"])
    print()

    # Faixa alvo para voz: RMS entre -30 e -12 dBFS, picos abaixo de -3.
    if melhor["rms_dbfs"] < -45:
        print("  [PROBLEMA] Sinal muito fraco. O Vosk vai errar muito.")
        print("             Aumente o ganho de captura:")
        print("                 alsamixer  ->  F4 (Capture)  ->  setas para cima")
        print("                 procure tambem 'Mic Boost' e ligue")
        print("             Depois salve com: sudo alsactl store")
    elif melhor["rms_dbfs"] < -30:
        print("  [ATENCAO] Sinal fraco. Funciona, mas da para melhorar.")
        print("            Aproxime o microfone ou suba o ganho no alsamixer.")
    elif melhor["clip_pct"] > 1.0 or melhor["peak_dbfs"] > -1.0:
        print("  [PROBLEMA] Sinal saturado (distorcido). Isso atrapalha tanto")
        print("             quanto o sinal fraco. Reduza o ganho no alsamixer.")
    else:
        print("  [ ok ] Nivel bom para reconhecimento.")

    if len(niveis) > 1:
        vivos = [i for i, n in enumerate(niveis) if n["rms_dbfs"] > -60]
        if len(vivos) == 1:
            print(
                f"\n  Nota: so o canal {vivos[0]} tem sinal. E normal em "
                "adaptadores USB baratos;\n        o projeto mistura os canais, "
                "entao isso nao e problema."
            )
        elif not vivos:
            print(
                "\n  [PROBLEMA] Nenhum canal captou nada. Verifique se o microfone"
                "\n             esta no conector certo (rosa = entrada) e se nao"
                "\n             esta mudo no alsamixer (tecla M)."
            )

    if save:
        from .audio.microphone import _to_mono

        mono = _to_mono(resultado["raw"], microphone.device_channels)
        caminho = microphone.save_wav([mono], ensure_dir(config.recordings_dir))
        print(f"\n  Audio salvo em {caminho}")
        print("  Ouca com:  aplay " + str(caminho))

    print()
    return 0


def _cmd_selftest(config: AppConfig) -> int:
    """Segue a ordem de integracao do relatorio: LED, servo, LCD, sensor."""
    with build_hardware(config) as hardware:
        print(f"\nHardware: {hardware.summary()}\n")

        print("1/5 LED RGB ...")
        for cor in ("vermelho", "verde", "azul", "amarelo", "ciano", "magenta"):
            print(f"     {cor}")
            hardware.leds.set_named(cor)
            time.sleep(0.5)
        hardware.leds.off()

        print("2/5 Servo ...")
        hardware.servo.move_to(0)
        time.sleep(0.5)
        hardware.servo.move_to(90)
        time.sleep(0.5)
        hardware.servo.release()

        print("3/5 LCD ...")
        hardware.lcd.show_lines("Central de Voz", "autoteste ok")
        time.sleep(1.5)
        hardware.lcd.show_text(
            "Este texto e maior que o display para testar a paginacao automatica."
        )
        time.sleep(5)

        print("4/5 Sensor de distancia ...")
        for _ in range(3):
            print(f"     {hardware.distance.read_cm():.1f} cm")
            time.sleep(0.4)

        print("5/5 Matriz ...")
        for icon in ("ok", "alerta", "casa"):
            hardware.matrix.show_icon(icon)
            time.sleep(0.7)
        hardware.matrix.clear()
        hardware.lcd.clear()

    print("\nAutoteste concluido.\n")
    return 0


def _cmd_say(config: AppConfig, text: str) -> int:
    with build_hardware(config) as hardware, Storage(config.db_path) as storage:
        controller = VoiceCommandController(config, hardware, storage)
        reply = controller.handle_text(text)
        print(reply.message)
        time.sleep(0.4)  # deixa o LCD/matriz mostrarem antes de fechar
    return 0


def _cmd_text(config: AppConfig) -> int:
    with build_hardware(config) as hardware, Storage(config.db_path) as storage:
        controller = VoiceCommandController(config, hardware, storage)
        controller.greet()
        print(f"\nHardware: {hardware.summary()}")
        print("Digite um comando (ex.: ligar led). 'ajuda' lista tudo, 'sair' encerra.\n")
        while True:
            try:
                text = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if text.lower() in {"sair", "exit", "quit"}:
                break
            if not text:
                continue
            reply = controller.handle_text(text)
            print(f"  {reply.message}\n")
            if reply.stop:
                break
    return 0


def _cmd_run(config: AppConfig) -> int:
    microphone = Microphone(config.audio)
    try:
        microphone.check()
        engine = VoskEngine(config.speech.model_path, microphone.sample_rate)
        engine.load()
    except (AudioUnavailable, SpeechUnavailable) as exc:
        print(f"\n[NAO DA PARA OUVIR AINDA]\n{exc}\n")
        print("Enquanto isso, teste a logica toda com:  voz text --mock\n")
        return 1

    with build_hardware(config) as hardware, Storage(config.db_path) as storage:
        controller = VoiceCommandController(config, hardware, storage)
        loop = VoiceLoop(config, controller, engine, microphone)

        def _handle_signal(*_args: object) -> None:
            print("\nEncerrando...")
            loop.stop()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        print(f"\nHardware: {hardware.summary()}")
        storage.log_event("startup", result=hardware.summary())
        try:
            loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            controller.close()
            storage.log_event("shutdown")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
