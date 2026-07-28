# Central de comandos por voz para o kit Freenove

## Estrutura de código
- `src/hardware/led.py`
- `src/hardware/servo.py`
- `src/hardware/lcd.py`
- `src/hardware/distance.py`
- `src/hardware/matrix.py`
- `src/recognition/commands.py`
- `src/recognition/vosk_engine.py`
- `src/audio/recorder.py`
- `src/app/controller.py`
- `src/main.py`

## Como testar em modo simulado
```bash
python -m  src.main
```

## Ordem recomendada de integração
1. LED
2. Servo
3. LCD
4. Sensor de distância
5. Reconhecimento de fala com Vosk
