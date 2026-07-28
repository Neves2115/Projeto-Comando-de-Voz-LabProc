from central_voz_freenove.hardware.matrix import LedMatrixController

matrix = LedMatrixController(mock=True)
matrix.show_icon("ok")
print(matrix.render())
