"""Package a local, unapplied road-junction review without changing the public viewer."""
import json
import shutil
from pathlib import Path
from review_police_verified_main_roads import OUT, ROOT


def main():
    report=json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
    assert report['applied'] is False and report['published'] is False
    shutil.copy2(ROOT/'tools/police_verified_roads_review.html',OUT/'index.html')
    shutil.copy2(ROOT/'tools/police_verified_roads_review.js',OUT/'review.js')
    text='''# Revision policial de ejes principales

Estado: PARA REVISION. NO APLICADA. NO PUBLICADA. No ejecutar una sustitucion automatica.

El caso de la captura corresponde a POL-08: la ubicacion publicada esta a 0.40 m de una calle local (El Oro), pero a 40.81 m del eje principal Proano. La clasificacion municipal la acepto como arterial; OSM la representa como residential. La validacion de la corrida anterior no contrasto esa discrepancia. Ademas, los rotulos anteriores utilizaron NOMBRE (parroquia) en lugar de TXT (calle).

La alternativa POL-08 se ubica en Proano x El Oro, a 43.94 m de su ubicacion publicada. Es un vertice compartido de calles nombradas; no es una proyeccion arbitraria al eje ni un punto inventado en una manzana.

Se preparan 30 posiciones usando KDE urbano D+V como criterio principal. Se conserva el kernel, radio 200 m, celda 20 m y peso 1; solo cambia el universo candidato vial. Se revisaron 939 cruces de vertices compartidos OSM, con dos calles nombradas, al menos tres brazos y un tramo trunk/primary/secondary/tertiary. Se descartan puentes, tuneles y cruces geometricos sin vertice compartido. La jerarquia OSM no se presenta como equivalente a una certificacion municipal.

Se mantienen fijas las 103 existentes del inventario nuevo y las 50 municipales. Gi* se usa como referencia sin cambiar celdas ni estadisticos. El analisis KDE del visor y las fuentes originales no se modifican. La integral KDE se reproduce solo para evaluar la alternativa privada con la misma metodologia anterior.

La seleccion greedy se ordena por KDE D+V marginal, grado y un ID estable para desempates. Cada radio intersecta cobertura base o seleccionada previamente. No se exige una distancia minima ni un solape maximo arbitrarios. Una vez seleccionadas posiciones, la asignacion de IDs minimiza desplazamiento total mediante scipy.optimize.linear_sum_assignment. No se afirma un optimo global del conjunto.

ADVERTENCIA: el conjunto completo genera desplazamientos extensos, no solo correcciones de metros. Media 999.02 m; maximo 5401.81 m. La cobertura de eventos D/V urbanos baja de 2631 a 2585 (-46); KDE D baja de 75.95% a 75.09%, KDE V de 69.32% a 67.88%. Los aumentos incidentales en corredores no compensan automaticamente esas perdidas ni constituyen el objetivo policial. Revisar antes de aplicar.

El mapa local compara lo publicado y lo propuesto, muestra KDE, las 103 existentes, las 50 municipales, radios de 200 m y ejes principales. Abre inicialmente POL-08. MOVIMIENTOS_POLICIA_30.csv y REVISION_POLICIA_30.gpkg conservan ID, XY antes/despues, desplazamiento, nombres de calles, jerarquia, IDs OSM, grado y evidencia de referencia Gi*.

Limitaciones: referencia OSM local, no levantamiento de postes, certificacion institucional ni modelo de linea de vista. No hay informacion de altura, orientacion u obstaculos. Las distancias se calculan en EPSG:32717, no en grados. Los derivados visuales estan en EPSG:4326.
'''
    trace_path=OUT/'TRAZABILIDAD.json'
    if trace_path.exists():
        trace=json.loads(trace_path.read_text(encoding='utf-8'))
        text+='\n## Historial y continuidad\n\n'
        text+=f"Se conservan {trace['historyRows']} registros de historial: {trace['historyVersions']} versiones por ID. Incluyen las revisiones puntuales POL-20/POL-12/POL-24, el escenario municipal B, KDE y la version actualmente publicada. No se inventan fechas de aprobacion: las fechas son las de cada version archivada. Cada coordenada tiene archivo y SHA-256 de origen.\n\n"
        text+=f"La alternativa tiene {trace['potentialLinks']} enlaces potenciales por calles entre policiales; {trace['linksNeedingOtherCameraCoverage']} requieren apoyo de otros radios. {len(trace['isolatedFromOtherPoliceInThisControl'])} policiales no tienen enlace comprobado a otra policial en este control. No implica aislamiento respecto a las 103 existentes o 50 municipales, cuyos anclajes en red no se inventan.\n\n"
        text+='Los enlaces siguen vertices compartidos y segmentos originales, totalmente cubiertos por la union de los radios de 183 equipos. No son rectas arbitrarias entre centros. No se crean nodos donde dos ejes cruzan sin conexion. Se calcula un arbol minimo entre policiales alcanzables para representar cadenas sin dibujar todos los pares. El modelo no dirigido es geometrico, no de trafico o tiempos de acceso.\n\n'
        text+='La continuidad de buffers y rutas no certifica seguimiento visual. Giros, alturas, orientaciones, obstaculos, operatividad e instalacion requieren verificacion de campo. Ver HISTORIAL_30_CAMARAS.csv, ENLACES_POTENCIALES_POR_CALLES.csv y TRAZABILIDAD.json.\n'
    (OUT/'INFORME.md').write_text(text,encoding='ascii')
    print(str(OUT/'index.html'))


if __name__=='__main__':
    main()
