"""Human-readable report and scientific plots from a finished native analysis."""
from pathlib import Path
import json, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.deps'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from study_reference import WORK


def render(output):
    a=json.loads((WORK/'report.json').read_text(encoding='utf-8'))
    assert a['completed_time_s']==9000 and a['native_frames_checked']==601
    h=np.genfromtxt(WORK/'section-hydrograph.csv',delimiter=',',names=True)
    t=h['time_s'];q=h['north_m3_s'];net=h['net_north_m3_s']
    cumulative=np.r_[0,np.cumsum((q[1:]+q[:-1])*.5*np.diff(t))]
    net_cumulative=np.r_[0,np.cumsum((net[1:]+net[:-1])*.5*np.diff(t))]
    peak=a['scenario']['sum_rounded_peaks_m3_s']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    fig,axes=plt.subplots(3,1,figsize=(10,10),layout='constrained')
    axes[0].plot([0,2.5,15],[0,peak,0],color='#21645d',lw=2)
    axes[0].fill_between([0,2.5,15],[0,peak,0],alpha=.12,color='#21645d')
    axes[0].set(title='Agua liberada en las nueve fuentes del Cotopaxi',xlabel='Minutos desde el inicio de los aportes',ylabel='Caudal total de agua (m³/s)',xlim=(0,15),ylim=(0,None))
    axes[1].plot(t/60,q,color='#924c31',lw=1.6)
    axes[1].set(title='Flujo hacia el norte en la sección al sur del área de comparación',xlabel='Minutos desde el inicio de los aportes',ylabel='Caudal de mezcla estimado (m³/s)',xlim=(0,150),ylim=(0,None))
    axes[2].plot(t/60,cumulative/1e6,label='Transporte hacia el norte',color='#924c31')
    axes[2].plot(t/60,net_cumulative/1e6,label='Transporte neto',color='#21645d',ls='--')
    axes[2].set(title='Integral del paso por la sección; no es volumen depositado en la ciudad',xlabel='Minutos desde el inicio de los aportes',ylabel='Volumen estimado (millones de m³)',xlim=(0,150))
    axes[2].legend(frameon=False)
    for ax in axes:ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Adaptación exploratoria de Kestrel · no validada para predicción local',fontsize=14)
    fig.savefig(output/'study-hydrographs.png',dpi=150);plt.close(fig)
    bracket=a['first_urban_wetting_bracket_s']
    arrival='No alcanzó el rectángulo de comparación en esta corrida.' if bracket is None else f"Entre {bracket[0]/60:.2f} y {bracket[1]/60:.2f} minutos desde los aportes en el Cotopaxi."
    volume=a['section']['integrated_m3'];alt=a['section']['subsampled_30s_integrated_m3']
    shift=abs(volume['north_m3']-alt['north_m3'])
    balance='menor del 0,001 %' if a['volume_balance_relative_error']*100<.001 else f"{a['volume_balance_relative_error']*100:.5f} %"
    section_rows=[]
    for section in a['published_section_context']['sections']:
        bracket=section['first_wetting_bracket_s']
        arrival_text='Sin llegada ≥5cm en esta corrida' if bracket is None else f'{bracket[0]/60:.2f}–{bracket[1]/60:.2f} min'
        section_rows.append(f"<tr><td>{section['name']}</td><td>{arrival_text}</td><td>{section['sampled_max_speed_m_s']:.2f} m/s</td><td>{section['published_scenario3_max_speed_m_s']} m/s</td></tr>")
    section_rows=''.join(section_rows)
    point=a['urban_depth_max_location']
    depth_context='No se registraron celdas con al menos5cm en este rectángulo.' if point is None else f"El máximo de espesor muestreado está en la celda centrada en {point['lat']:.5f}, {point['lon']:.5f}, a los {point['time_s']/60:.2f} minutos. Su componente vertical es {point['vertical_depth_m']:.2f}m. Es una celda de30m dentro del rectángulo, que incluye cañones; no describe una altura uniforme sobre la ciudad ni necesariamente una calle."
    html=f'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Resultado del escenario de lahares · Sangolquí</title><style>body{{font:16px/1.6 Arial,sans-serif;background:#f8f7f2;color:#233c38;max-width:1000px;margin:30px auto;padding:0 22px}}h1{{line-height:1.2}}a{{color:#21645d}}.notice{{background:#fcf1da;border-left:4px solid #c28a40;padding:16px}}table{{border-collapse:collapse;width:100%;margin:25px 0}}td,th{{border-bottom:1px solid #dce0d4;padding:12px;text-align:left}}img{{max-width:100%;height:auto}}small{{color:#52685e}}</style>
    <a href="../../lahars.html">← Volver al simulador 3D</a><h1>Qué calculó este escenario</h1>
    <p class="notice"><b>Adaptación exploratoria, sin validación predictiva local.</b> Usa los nueve aportes de agua de un estudio publicado, con ubicaciones digitalizadas de su mapa y un terreno global de 30 m diferente del original. No es un pronóstico de erupción ni indica cuánto tiempo hay para evacuar.</p>
    <table><tr><th>Dato</th><th>Resultado de esta corrida</th></tr>
    <tr><td>Agua liberada en el flanco norte</td><td>{a['scenario']['water_input_m3']/1e6:.3f} millones de m³, durante 15 minutos</td></tr>
    <tr><td>Primera presencia de al menos 5 cm en el rectángulo Sangolquí–San Rafael</td><td>{arrival}</td></tr>
    <tr><td>Mayor espesor muestreado dentro de ese rectángulo</td><td>{a['urban_max_depth_m']:.2f} m, normal a la pendiente</td></tr>
    <tr><td>Mayor velocidad muestreada con espesor de al menos5cm</td><td>{a['urban_max_speed_m_s']*3.6:.2f} km/h ({a['urban_max_speed_m_s']:.2f} m/s)</td></tr>
    <tr><td>Transporte estimado hacia el norte por la sección de comparación</td><td>{volume['north_m3']/1e6:.3f} millones de m³</td></tr>
    <tr><td>Transporte neto por esa sección</td><td>{volume['net_north_m3']/1e6:.3f} millones de m³</td></tr></table>
    <p>La sección está al sur del rectángulo y abarca los corredores de Pita y Santa Clara. La integral del paso por una sección <b>no equivale a todo el material que entra en la ciudad ni al que queda en sus calles</b>. El transporte positivo puede contar material que cruza más de una vez. Los límites del rectángulo no son los límites administrativos.</p>
    <p>{depth_context}</p><p>Los máximos de esta tabla corresponden a los601 estados revisados cada15 segundos; puede haber picos entre esas muestras. Que un resultado sea cero o no alcance el área en esta corrida <b>no demuestra que el lugar sea seguro</b>.</p>
    <img src="study-hydrographs.png" alt="Tres gráficos: aporte inicial de agua, caudal estimado por la sección y volumen acumulado de paso durante 150 minutos.">
    <h2>Qué se comprobó</h2><p>La corrida terminó los 150 minutos y se revisaron sus 601 estados, guardados cada 15 segundos. La diferencia máxima en el balance de volumen del flujo y del lecho fue {balance} del aporte. La integral por sección cambió {shift/1e6:.6f} millones de m³ al usar datos cada 30 segundos. Esta comparación examina el muestreo temporal; no mide el error del terreno ni valida la predicción.</p>
    <h2>Por qué no reproduce exactamente el estudio</h2><p>El escenario de agua y los parámetros físicos proceden de <a href="https://doi.org/10.3389/feart.2025.1611579">Vasconez y colaboradores (2025)</a>. La geometría de referencia del glaciar se basó en imágenes de 2020–2022, no en un levantamiento de 2026. Nuestro terreno Copernicus de 30 m puede incluir vegetación y edificios y no resuelve todos los cañones. Las fuentes se digitalizaron de una figura; faltan sus archivos GIS originales. El acondicionamiento de depresiones se limitó a elevaciones de hasta 2 m. Estas diferencias pueden cambiar alcance, velocidad y llegada.</p>
    <p>Los tiempos de 52 minutos a Sangolquí y 60–84 minutos a San Rafael de <a href="https://doi.org/10.1002/esp.5056">Frimberger y colaboradores</a> corresponden a otros escenarios y a RAMMS. Su figura 6 incluye velocidades históricas reconstruidas para calibrar 1877: 18 m/s en Jatabamba y 20 m/s en Proaño y Hacienda San Rafael. No se impusieron esos tiempos ni velocidades a esta animación. La corrección y validación local siguen pendientes de terreno fino y comparación en puntos equivalentes.</p>
    <h2>Contraste en secciones publicadas</h2><p>Se muestrearon las líneas transversales con coordenadas de <a href="https://bibdigital.epn.edu.ec/handle/15000/17595">Torres y Vásquez, EPN2017, tablas3.5,3.7 y4.2</a>. Las llegadas de nuestra corrida cuentan desde las nueve fuentes del glaciar. El otro estudio utiliza diferentes entradas, terreno y propiedades del flujo. Sus velocidades máximas de FLOW-3D no son necesariamente la misma magnitud que la velocidad promediada en profundidad de Kestrel; esta tabla aporta contexto y <b>no constituye una calibración</b>.</p><table><tr><th>Sección</th><th>Primera presencia ≥5cm en esta corrida</th><th>Máxima velocidad muestreada de esta corrida</th><th>Referencia EPN2017, escenario3</th></tr>{section_rows}</table>
    <h2>También revisamos el terreno municipal</h2><p>Se obtuvieron 9.127 cotas numéricas válidas del MDT municipal. Sus diferencias frente al Copernicus varían según el lugar; el RMSE entre productos es de 10,30 m. No es una medida de precisión contra levantamientos de campo. Los perfiles muestran cauces que el terreno global suaviza. No se fusionaron cotas sin confirmar la referencia vertical y la resolución original del servicio. Consultar cada 5 m no convierte ese servicio en un MDT de resolución nativa de 5 m.</p>
    <img src="municipal-terrain-profiles.png" alt="Cinco perfiles del terreno municipal y Copernicus comparados en el corredor al sur de Sangolquí.">
    <p><a href="municipal-terrain-comparison.json">Comprobación del terreno municipal</a> · <a href="municipal-terrain-samples.csv.gz">Muestras de cota (CSV comprimido)</a></p>
    <h2>Contraste con evidencia histórica</h2><p>También se revisaron 14 polígonos de depósitos y 170 puntos de trabajo de campo publicados por <a href="https://zenodo.org/records/5866730">Andrade y colaboradores (2022), CC BY 4.0</a>. Cubren el tramo cercano al volcán. Los depósitos de 1877 no son la misma magnitud que el espesor máximo de un flujo hipotético con otra geometría del glaciar. Esta comparación espacial no es una puntuación de exactitud ni valida llegadas o velocidades en la ciudad.</p><img src="historical-deposits-comparison.png" alt="Recorrido calculado cerca del volcán comparado con límites de depósitos históricos y puntos de campo de 1877."><p><a href="historical-deposits-comparison.json">Datos del contraste histórico</a></p>
    <p><a href="section-hydrograph.csv">Descargar caudal por tiempo (CSV)</a> · <a href="study-report.json">Datos y comprobaciones (JSON)</a> · <a href="source-terrain-audit.json">Entradas y terreno</a> · <a href="../../analysis/lahars-sangolqui/METODOLOGIA.md">Metodología completa</a></p><small>Las construcciones son referencias visuales; no actúan como obstáculos ni se calculan daños estructurales.</small></html>'''
    (output/'study-summary.html').write_text(html,encoding='utf-8')
    print('Human-readable results and scientific charts rendered.',flush=True)


if __name__=='__main__':render(WORK)
