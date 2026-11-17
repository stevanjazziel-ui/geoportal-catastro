"""Render product-to-product elevation differences, not accuracy against ground truth."""
from pathlib import Path
import gzip, json
from study_reference import ROOT
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    source=ROOT/'sources/municipal-terrain-audit'
    a=np.genfromtxt(source/'samples.csv',delimiter=',',names=True)
    report=json.loads((source/'report.json').read_text(encoding='utf-8'))
    xs=np.arange(785500,787501,5)
    fig,axes=plt.subplots(5,1,figsize=(10,12),layout='constrained',sharex=True)
    for ax,y in zip(axes,(9949000,9949500,9950000,9950500,9951000)):
        rows=a[(a['northing']==y)&(a['easting']>=xs[0])&(a['easting']<=xs[-1])]
        municipal=np.full(len(xs),np.nan);cop=municipal.copy()
        ix=np.searchsorted(xs,rows['easting']);municipal[ix]=rows['municipal_service_m'];cop[ix]=rows['copernicus30m_m']
        ax.plot(xs,municipal,label='Cota consultada al municipio',color='#21645d',lw=1.5)
        ax.plot(xs,cop,label='Copernicus reproyectado a 30 m',color='#b46638',lw=1.2)
        ax.set(title=f'Perfil transversal · norte UTM {y:,} m',ylabel='Cota reportada (m)')
        ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
    axes[0].legend(frameon=False,fontsize=9)
    axes[-1].set_xlabel('Este UTM zona 17 sur (m)')
    fig.suptitle('Comparación de terrenos en el corredor al sur de Sangolquí\nConsulta cada 5 m: no demuestra resolución nativa de 5 m',fontsize=13)
    fig.savefig(source/'terrain-profiles.png',dpi=130);plt.close(fig)
    raw=(source/'samples.csv').read_bytes()
    (source/'samples.csv.gz').write_bytes(gzip.compress(raw,mtime=0))
    print('Municipal elevation audit rendered; no DEM or model inputs changed.',flush=True)


if __name__=='__main__':main()
