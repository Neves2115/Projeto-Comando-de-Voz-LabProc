from central_voz_freenove.hardware.servo import ServoController

servo = ServoController(pin=18, mock=True)
servo.open(90)
servo.close(0)
