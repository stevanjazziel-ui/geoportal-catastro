"""Publish only the approved aggregate KDE, never individual CMI records."""
import base64
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('D:/codex/entregas/KDE_COMBINADO_PROVISIONAL_20261017')
OUT=ROOT/'data/seguridad-riobamba/KDE_COMBINADO_200M_20261017'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((SOURCE/'RESULTADOS.json').read_text())
    grid=json.loads((ROOT/'riobamba-conflictividad-data.js').read_text(encoding='utf-8').split('=',1)[1].strip().rstrip(';'))['urbanGrid']
    with np.load(SOURCE/'NUMERICOS/KDE_TODOS_DISPONIBLES_200M.npz') as cached:
        density=cached['density'].ravel().astype('<f8')
    assert hashlib.sha256(density.tobytes()).hexdigest()==next(s['rasterSha256'] for s in metadata['surfaces'] if s['name']=='KDE_TODOS_DISPONIBLES_200M')
    stops=np.array(metadata['commonColorStops'])
    colors=np.array([[255,255,178],[254,217,118],[254,178,76],[240,59,32],[189,0,38],[189,0,38]])
    alphas=np.array([0,65,140,205,215,215])
    warp=np.array(grid['warpIndex'])
    values=density[np.maximum(warp,0)]
    rgba=np.zeros((len(warp),4),dtype=np.uint8)
    for channel in range(3):
        rgba[:,channel]=np.floor(np.interp(values,stops,colors[:,channel])+.5).astype(np.uint8)
    rgba[:,3]=np.floor(np.interp(values,stops,alphas)+.5).astype(np.uint8)
    rgba[(warp<0)|(values<=stops[0]),3]=0
    Image.fromarray(rgba.reshape(grid['height'],grid['width'],4)).save(OUT/'kde-combinado-200m.png')
    positive=density[density>0]
    stats=dict(zip(['p25','p30','p50','p75','p90','p95'],map(float,np.quantile(positive,[.25,.30,.50,.75,.90,.95]))))
    stats.update(minDensity=0,maxDensity=float(density.max()),positiveCells=len(positive))
    public=dict(release='kde-combinado-200m-20261017',records=10731,ecu911=9915,cmi=816,
        bandwidth=200,cellSize=20,crs='EPSG:32717',units='registros/km2',
        period='ECU911: enero-agosto 2026; CMI: enero-9 octubre 2026',
        warning='Provisional: posible doble conteo entre fuentes. No representa hechos unicos ni significancia Gi*.',
        statisticalScope='URBANO: union operativa de 18 Plataformas',
        unresolvedPairs=130,deduplicated=False,pointCoordinatesChanged=False,giChanged=False,
        colorStops=stops.tolist(),colors=['#ffffb2','#fed976','#feb24c','#f03b20','#bd0026','#bd0026'],
        alphas=alphas.tolist(),visual=stats,
        densitySha256=hashlib.sha256(density.tobytes()).hexdigest(),
        pngSha256=hashlib.sha256((OUT/'kde-combinado-200m.png').read_bytes()).hexdigest(),
        bounds=grid['bounds'])
    (OUT/'METODOLOGIA.json').write_text(json.dumps(public,indent=2),encoding='utf-8')
    encoded=base64.b64encode(density.tobytes()).decode('ascii')
    (ROOT/'riobamba-kde-combinado-data.js').write_text('window.RIOBAMBA_KDE_COMBINADO='+json.dumps(dict(**public,densityBase64=encoded),separators=(',',':'))+';\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in public.items() if k not in ['visual','bounds']},indent=2))


if __name__=='__main__':
    main()
