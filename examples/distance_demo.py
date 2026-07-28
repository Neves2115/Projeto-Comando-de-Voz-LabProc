from central_voz_freenove.hardware.distance import DistanceSensorReader

sensor = DistanceSensorReader(echo_pin=23, trigger_pin=24, mock=True)
print(sensor.read_cm())
