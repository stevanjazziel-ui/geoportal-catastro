"""Map the native flow envelope and first saved wetting of both rivers."""

import json
from html import escape

from compare_lahar_branches import OUT as AUDIT, ROOT, RUN
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from netCDF4 import Dataset
import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.plot import plotting_extent


OUT = ROOT.parent / 'dist/data/sangolqui-lahars'
COLORS = {'Pita': '#147e9a', 'Santa Clara': '#7e43a1'}
STUDY_2017 = 'https://bibdigital.epn.edu.ec/bitstream/15000/17595/1/CD-8076.pdf#page=141'
STUDY_2021 = 'https://onlinelibrary.wiley.com/doi/10.1002/esp.5056'
STUDY_2025 = 'https://doi.org/10.3389/feart.2025.1611579'
OFFICIAL = 'https://www.igepn.edu.ec/cotopaxi-mapa-de-amenza-volcanica/25031-mapa-amenaza-volcanica-cotopaxi-norte-2016/file'


def draw(report):
    west, south, east, north = 780500, 9947400, 790400, 9969300
    fig, (area, time) = plt.subplots(1, 2, figsize=(12.3, 9), gridspec_kw={'width_ratios': [1.1, 1]})
    fig.subplots_adjust(top=.865, left=.085, right=.965, bottom=.155, wspace=.14)
    to_utm = Transformer.from_crs(4326, 32717, always_xy=True)
    with rasterio.open(RUN / 'prepared/municipal_hybrid_30m.tif') as dem:
        window = rasterio.windows.from_bounds(west, south, east, north, dem.transform)
        z = dem.read(1, window=window)
        extent = plotting_extent(z, dem.window_transform(window))
        dy, dx = np.gradient(z, 30)
        shade = (1 + .55 * dx + .45 * dy) / np.sqrt(1 + dx*dx + dy*dy)
        area.imshow(shade, extent=extent, cmap='Greys_r', vmin=-.45, vmax=1.03, alpha=.29)
    with Dataset(RUN / 'prepared/display-maximums.nc') as ds:
        x, y = np.asarray(ds['x'][:]), np.asarray(ds['y'][:])
        rr = np.flatnonzero((y > south - 30) & (y < north + 30))
        cc = np.flatnonzero((x > west - 30) & (x < east + 30))
        h = ds['max_depth'][rr[0]:rr[-1]+1, cc[0]:cc[-1]+1].filled(0)
        categories = np.where(h < .5, 1, np.where(h < 2, 2, 3))
        area.imshow(np.ma.masked_where(h < .05, categories), interpolation='nearest', origin='lower',
                    cmap=ListedColormap(['#f8bf5a', '#e97b34', '#a6442b']), vmin=1, vmax=3,
                    extent=[x[cc[0]]-15, x[cc[-1]]+15, y[rr[0]]-15, y[rr[-1]]+15])
    for segment in report['segments']:
        _, lon, lat, seconds = np.array(segment['samples']).T
        x, y = to_utm.transform(lon, lat)
        color = COLORS[segment['river']]
        area.plot(x, y, ls=(0, (1, 2.4)), color=color, lw=1.6)
        # A gap is preserved as a blank on the time plot.
        minutes = np.where(seconds >= 0, seconds / 60, np.nan)
        time.plot(minutes, y, color=color, lw=2.4)
        if segment['id'] != 'santaclara4':
            continue
        gap = max(segment['dry_runs_of_100m_or_more'], key=lambda run: run['length_km'])
        lo = to_utm.transform(*gap['start'])[1]
        hi = to_utm.transform(*gap['end'])[1]
        time.axhspan(lo, hi, color=color, alpha=.09)
        time.text(7, (lo + hi) / 2, 'Santa Clara\nTramo de 4,5 km sin flujo ≥5 cm', va='center', color='#592d73', fontsize=10)
    for text, lon, lat, delta in [('La Caldera',-78.42255,-.45633,(8,-13)),('Sangolquí',-78.4425,-.3315,(-6,7)),('San Rafael',-78.447,-.306,(-6,8))]:
        x, y = to_utm.transform(lon, lat)
        area.scatter(x, y, color='#293a3a', s=12, zorder=5)
        area.annotate(text, (x,y), xytext=delta, textcoords='offset points', fontsize=10, weight='bold',
                      ha='left' if delta[0]>0 else 'right', bbox={'fc':'white','ec':'none','pad':2,'alpha':.85})
    for ax in (area, time):
        ax.set_ylim(south, north)
        ax.ticklabel_format(axis='y', style='plain', useOffset=False)
        ax.spines[['right','top']].set_visible(False)
        ax.grid(alpha=.19)
    area.set(xlim=(west,east), xlabel='Este UTM 17S (m)', ylabel='Norte UTM 17S (m)', title='Dónde pasa el flujo calculado')
    area.ticklabel_format(axis='x', style='plain', useOffset=False)
    time.set(xlim=(0,150), xlabel='Minutos desde el inicio de los aportes', title='Cuándo aparece flujo cerca de cada cauce')
    time.tick_params(labelleft=False)
    fig.text(.085,.943,'Pita y Santa Clara · escenario municipal',weight='bold',fontsize=22,color='#183633')
    fig.text(.085,.907,'Primer estado con ≥5 cm en el corredor del río. 601 estados guardados cada 15 s.',fontsize=11,color='#425854')
    handles = [Patch(facecolor='#e97b34', label='Espesor máximo calculado ≥5 cm'),
               *[Line2D([0],[0],color=color,lw=2,label=river) for river,color in COLORS.items()]]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5,.065), ncols=3, frameon=False)
    fig.text(.085, .045, 'Cauces © OpenStreetMap contributors · Relieve GAD Rumiñahui y Copernicus GLO-30 · Cálculo Kestrel', fontsize=8.5)
    fig.text(.085, .024, 'La humedad cerca de una confluencia puede venir de otra rama. Escenario exploratorio sin validación predictiva local.', fontsize=8.5)
    fig.savefig(OUT/'comparacion-pita-santa-clara.png',dpi=150,facecolor='white')
    plt.close(fig)


def main():
    report = json.loads(AUDIT.read_text(encoding='utf-8'))
    draw(report)
    (OUT/'branch-audit.json').write_bytes(AUDIT.read_bytes())
    sections = {item['id']:item for item in report['segments']}
    pita = sections['pita3']['samples'][-1][-1] / 60
    santa = sections['santaclara3']['samples'][-1][-1] / 60
    gap = max(sections['santaclara4']['dry_runs_of_100m_or_more'], key=lambda item:item['length_km'])
    checks = ''.join(f'<tr><td>{escape(row["name"])}</td><td>{time}</td><td>{speed}</td></tr>'
                     for row in report['sections']
                     for time, speed in [(f'{row["first_wetting_bracket_s"][1]/60:.2f} min', f'{row["sampled_max_speed_m_s"]:.1f} m/s')
                                         if row['first_wetting_bracket_s'] else ('Sin ≥5 cm en 150 min','—')])
    page = f'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pita y Santa Clara · comparación</title><style>
body{{font:16px/1.6 system-ui,sans-serif;max-width:1050px;margin:40px auto;padding:0 22px;color:#193a33}} a{{color:#185b5b}}img{{width:100%;height:auto}} table{{border-collapse:collapse}} td,th{{padding:9px;text-align:left;border-bottom:1px solid #ccd7d2}}
</style><a href="../../lahars.html">Volver al visor 3D</a>
<h1>¿Por qué avanzan distinto el Pita y el Santa Clara?</h1>
<p>En esta corrida, el Pita es el cauce principal. Parte del flujo desborda hacia Santa Clara cerca de La Caldera. Las velocidades máximas en las dos secciones de La Caldera fueron 14,2 m/s en Pita y 7,5 m/s en Santa Clara. Son máximos locales y pueden ocurrir a distintos minutos.</p>
<p>Al comparar los dos cursos cerca de la latitud 0,362° S, el Pita mostró flujo al minuto <b>{pita:.0f}</b> y Santa Clara al <b>{santa:.0f}</b>. La distancia recorrida por cada cauce es distinta. Más adelante, hay un tramo cartográfico de <b>{gap['length_km']:.1f} km</b> en Santa Clara sin flujo de al menos 5 cm durante los 150 minutos. Cerca de la unión con San Pedro aparece flujo calculado que podría provenir de otra rama.</p>
<img src="comparacion-pita-santa-clara.png" alt="Mapa del flujo de ambos ríos y gráfico de primeras llegadas. El modelo presenta una brecha de unos 4,5 km en Santa Clara.">
<h2>Qué muestran otros escenarios</h2>
<ul><li><b>Torres y Vásquez (EPN, 2017).</b> En el escenario 3, al final del tramo 3 Santa Clara llega antes que Pita (45,1 frente a 53,2 min). Las llegadas tabuladas a las uniones con San Pedro son 66,8 min por Santa Clara y 79,8 min por Pita. Los límites, el reloj y las entradas pertenecen a ese estudio. <a href="{STUDY_2017}">Tabla 4.4 y mapas del estudio</a>.</li>
<li><b>Frimberger y colaboradores (2021).</b> En RAMMS, el escenario 4 alcanza Sangolquí por Santa Clara a los 52 min y San Rafael por Pita a los 60 min. El desborde de Santa Clara es menor en el escenario 3. <a href="{STUDY_2021}">Tabla 2 y mapas de escenarios</a>.</li>
<li><b>Vásconez y colaboradores (2025).</b> La figura 5 compara las mismas entradas con distintos relieves. En sus mallas de 15 y 20 m, Santa Clara se detiene antes de zonas residenciales durante los 150 min. Las de 10 y 30 m muestran mayor desborde, con trayectorias diferentes. <a href="{STUDY_2025}">Figuras 5 y 8, y verificación de campo en La Caldera</a>.</li></ul>
<p>El <a href="{OFFICIAL}">mapa oficial de amenaza del IG-EPN para la zona norte</a> cubre ambos corredores. En el visor también puedes activar «Comparar con el mapa municipal» para consultar la referencia del GAD Rumiñahui.</p>
<h2>Puntos de control del cálculo</h2>
<table><tr><th>Sección</th><th>Primer estado con ≥5 cm</th><th>Velocidad máxima muestreada con ≥5 cm</th></tr>{checks}</table>
<p>Los tiempos se cuentan desde las nueve entradas del modelo. Se muestrearon los 601 estados nativos con paso de salida de 15 s. El corredor cartográfico se examina en ventanas de 5 × 5 celdas de 30 m. La simulación usa el MDT municipal remuestreado a 30 m y el terreno regional fuera de su cobertura. El tramo sin flujo calculado es una limitación de este escenario exploratorio. La amenaza oficial y los tiempos publicados se mantienen como referencias independientes.</p>
<p><a href="branch-audit.json">Descargar muestras de ambos cauces</a> · <a href="study-summary.html">Ver informe de la corrida</a></p></html>'''
    # Present decimal commas in the public Spanish report.
    page = page.replace('4.5 km','4,5 km')
    (OUT/'comparacion-pita-santa-clara.html').write_text(page,encoding='utf-8')


if __name__ == '__main__':
    main()
