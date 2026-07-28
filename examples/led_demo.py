from central_voz_freenove.hardware.led import LedController

leds = LedController((17,), mock=True)
leds.on()
leds.blink(n=2)
leds.off()
