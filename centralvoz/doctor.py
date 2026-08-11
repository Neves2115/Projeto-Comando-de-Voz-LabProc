"""`voz doctor`: diagnostico do ambiente.

Se esse comando existisse na versao anterior do projeto, o erro
"No module named lgpio / PWM is not supported" teria sido diagnosticado em
cinco segundos, com o comando de correcao na tela.
"""

from __future__ import annotations

import importlib.util
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .gpio_setup import FACTORY_MODULES, PREFERRED_ORDER, inspect_platform

OK = "  [ ok ]"
WARN = "  [aviso]"
FAIL = "  [FALHA]"


@dataclass
class Check:
    status: str
    title: str
    detail: str = ""
    hint: str = ""


def run_checks(config: AppConfig) -> list[Check]:
    checks: list[Check] = []
    checks.append(_check_python())
    checks.extend(_check_platform())
    checks.extend(_check_i2c(config))
    checks.extend(_check_audio(config))
    checks.extend(_check_speech(config))
    checks.append(_check_storage(config))
    return checks


def print_report(config: AppConfig) -> int:
    checks = run_checks(config)
    print("\n=== Diagnostico da Central de Voz ===\n")
    for check in checks:
        line = f"{check.status} {check.title}"
        if check.detail:
            line += f": {check.detail}"
        print(line)
        if check.hint:
            for hint_line in check.hint.strip().splitlines():
                print(f"         {hint_line}")
    failures = sum(1 for check in checks if check.status == FAIL)
    print(
        f"\n{len(checks)} verificacoes, {failures} falha(s).\n"
        "Lembre que tudo funciona com --mock mesmo sem hardware.\n"
    )
    return 1 if failures else 0


# --------------------------------------------------------------------------- #


def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _check_python() -> Check:
    version = platform.python_version()
    if sys.version_info >= (3, 11):
        return Check(OK, "Python", f"{version} em {platform.machine()}")
    return Check(FAIL, "Python", version, "Este projeto precisa de Python 3.11 ou maior.")


def _check_platform() -> list[Check]:
    info = inspect_platform()
    checks: list[Check] = []

    if info.is_raspberry_pi:
        checks.append(Check(OK, "Placa", info.model or "Raspberry Pi"))
    else:
        checks.append(
            Check(WARN, "Placa", info.model or "nao e um Raspberry Pi",
                  "Fora do Pi so o modo --mock funciona. Tudo bem para desenvolver.")
        )

    available = [name for name in PREFERRED_ORDER if name in info.available_factories]
    if available:
        checks.append(
            Check(OK, "Backend de GPIO", f"disponivel: {', '.join(available)}; "
                  f"sera usado: {available[0]}")
        )
    else:
        missing = ", ".join(f"{k} ({v})" for k, v in FACTORY_MODULES.items() if v)
        checks.append(
            Check(
                FAIL if info.is_raspberry_pi else WARN,
                "Backend de GPIO",
                "nenhum backend com PWM",
                "sudo apt install -y python3-lgpio\n"
                "Se usa venv: python3 -m venv --system-site-packages .venv\n"
                f"Procurados: {missing}",
            )
        )

    if _installed("gpiozero"):
        checks.append(Check(OK, "gpiozero", "instalado"))
    else:
        checks.append(
            Check(WARN, "gpiozero", "ausente", "pip install 'centralvoz[pi]'")
        )
    return checks


def _check_i2c(config: AppConfig) -> list[Check]:
    checks: list[Check] = []
    if not config.lcd.enabled:
        return [Check(WARN, "LCD I2C", "desativado em config.toml")]

    if not _installed("smbus2"):
        return [
            Check(WARN, "LCD I2C", "smbus2 ausente",
                  "sudo apt install -y python3-smbus2 i2c-tools")
        ]

    bus_device = Path(f"/dev/i2c-{config.lcd.i2c_bus}")
    if not bus_device.exists():
        return [
            Check(FAIL, "LCD I2C", f"{bus_device} nao existe",
                  "sudo raspi-config -> Interface Options -> I2C -> Yes, depois reinicie.")
        ]

    try:
        from smbus2 import SMBus

        found = []
        with SMBus(config.lcd.i2c_bus) as bus:
            for address in range(0x03, 0x78):
                try:
                    bus.write_quick(address)
                    found.append(f"0x{address:02X}")
                except OSError:
                    continue
        if found:
            checks.append(Check(OK, "LCD I2C", f"dispositivos: {', '.join(found)}"))
        else:
            checks.append(
                Check(FAIL, "LCD I2C", "nenhum dispositivo no barramento",
                      "Confira VCC, GND, SDA (GPIO2) e SCL (GPIO3). "
                      "Depois rode: i2cdetect -y 1")
            )
    except (OSError, PermissionError) as exc:
        checks.append(
            Check(FAIL, "LCD I2C", str(exc),
                  "Adicione seu usuario ao grupo: sudo usermod -aG i2c $USER (e relogue)")
        )
    return checks


def _check_audio(config: AppConfig) -> list[Check]:
    if not _installed("sounddevice"):
        return [
            Check(WARN, "Audio", "sounddevice ausente",
                  "sudo apt install -y libportaudio2 && pip install sounddevice")
        ]
    try:
        from .audio.microphone import list_input_devices

        devices = list_input_devices()
    except Exception as exc:
        return [Check(FAIL, "Audio", str(exc), "sudo apt install -y libportaudio2")]

    if not devices:
        return [
            Check(FAIL, "Microfone", "nenhuma entrada encontrada",
                  "Conecte o microfone USB e confira com: arecord -l")
        ]
    linhas = []
    problema = False
    for d in devices[:4]:
        taxas = d.get("rates") or []
        if taxas:
            linhas.append(f"[{d['index']}] {d['name']} -> {', '.join(map(str, taxas))} Hz")
        else:
            linhas.append(f"[{d['index']}] {d['name']} -> nenhuma taxa aceita")
            problema = True

    detalhe = f"{len(devices)} entrada(s)"
    dica = "\n".join(linhas)
    if problema:
        dica += (
            "\nSe nenhuma taxa foi aceita, o microfone pode estar ocupado "
            "por outro programa."
        )
    return [Check(WARN if problema else OK, "Microfone", detalhe, dica)]


def _check_speech(config: AppConfig) -> list[Check]:
    checks: list[Check] = []
    if not _installed("vosk"):
        checks.append(Check(WARN, "Vosk", "ausente", "pip install vosk"))
    else:
        checks.append(Check(OK, "Vosk", "instalado"))

    from .speech.vosk_engine import resolve_model_dir

    model = config.speech.model_path
    resolvido = resolve_model_dir(model)
    if resolvido is not None:
        detalhe = str(resolvido)
        if resolvido != model:
            detalhe += "  (subpasta -- o projeto encontra sozinho)"
        checks.append(Check(OK, "Modelo de fala", detalhe))
    elif model.is_dir():
        conteudo = ", ".join(sorted(p.name for p in model.iterdir())[:8]) or "vazia"
        checks.append(
            Check(FAIL, "Modelo de fala", f"{model} nao parece um modelo Vosk",
                  f"Contem: {conteudo}\n"
                  f"Esperado um destes layouts:\n"
                  f"  classico:  am/ conf/ graph/ ivector/\n"
                  f"  compilado: final.mdl HCLr.fst Gr.fst ivector/\n"
                  f"Reextraia: rm -rf {model} && bash scripts/download_model.sh")
        )
    else:
        checks.append(
            Check(FAIL, "Modelo de fala", f"{model} nao encontrado",
                  "bash scripts/download_model.sh")
        )
    return checks


def _check_storage(config: AppConfig) -> Check:
    try:
        config.log_dir.mkdir(parents=True, exist_ok=True)
        probe = config.log_dir / ".escrita"
        probe.write_text("ok")
        probe.unlink()
        return Check(OK, "Pasta de logs", str(config.log_dir.resolve()))
    except OSError as exc:
        return Check(FAIL, "Pasta de logs", str(exc), "Confira permissoes e espaco no cartao.")
