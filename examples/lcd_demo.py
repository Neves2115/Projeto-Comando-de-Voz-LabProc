from central_voz_freenove.hardware.lcd import LcdDisplay

lcd = LcdDisplay(mock=True)
lcd.show_message("Central de Voz", "Pronto")
print(lcd.render())
