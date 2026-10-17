# KDE combinado provisional aprobado para publicacion

10.731 registros urbanos: 9.915 ECU911 de enero-agosto 2026 + 816 robos CMI de enero-9 de octubre 2026.
No representa una serie homogenea enero-octubre de ambas fuentes ni 10.731 hechos unicos.
Persisten 130 pares candidatos entre fuentes sin confirmar; no se eliminaron por distancia.

Radio 200 m, celda 20 m, EPSG:32717. Mismo kernel normalizado truncado y mascara urbana del visor.
Peso 1 por registro, sin correccion de borde. Convivencia conserva su peso por numero de registros.
No equivale a peligrosidad, Gi*, una tasa poblacional o visibilidad de camaras.

Se publica solo el agregado numerico y su imagen; no los puntos CMI, fechas individuales o expedientes.
Los limites de color son los mismos del estudio comparativo local: P30/P50/P75/P90/P95/max de las
cuatro superficies comparadas. Los valores concretos, colores y alpha estan en METODOLOGIA.json.
Rojo desde P90, rojo oscuro desde P95; hasta P30 transparente solo en la representacion.

La superficie publicada es fija, sin filtros por categoria/fecha/plataforma. El KDE rural y Gi* conservan
sus datos, calculos, parametros y filtros. Las camaras y sus evaluaciones anteriores no se recalculan
por el mero hecho de incorporar este fondo KDE en la evaluacion de propuestas.

Resultado local de origen: KDE_TODOS_DISPONIBLES_200M. El hash de la densidad Float64 se conserva.
