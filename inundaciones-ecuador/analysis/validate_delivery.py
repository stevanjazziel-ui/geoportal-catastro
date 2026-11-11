import gzip,json,pathlib
from html.parser import HTMLParser
import numpy as np
ROOT=pathlib.Path(__file__).parent;DATA=ROOT/'dist/data'
class CheckAssets(HTMLParser):
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ('script','link'):
            ref=attrs.get('src') or attrs.get('href')
            if ref and not ref.startswith('http'):
                assert (ROOT/'dist'/ref.split('?',1)[0]).is_file(),ref
for page in ('index.html','datos-hidraulicos.html'):
    CheckAssets().feed((ROOT/'dist'/page).read_text(encoding='utf-8'))
cat=json.loads((DATA/'cities.json').read_text(encoding='utf-8'));assert len(cat['cities'])==38
ids=[c['id'] for c in cat['cities']];assert len(set(ids))==38
checks=[]
for c in cat['cities']:
    d=json.loads((DATA/f"{c['id']}.json").read_text());n=d['n'];z=np.array(d['dem']);classes=np.array(d['class']);assert z.shape==(128,128) and np.isfinite(z).all();assert classes.shape==z.shape
    assert np.isin(classes,[0,1,2,3,4]).all();assert (DATA/f"{c['id']}.png").is_file()
    assert c['bbox'][0]<c['lon']<c['bbox'][2] and c['bbox'][1]<c['lat']<c['bbox'][3]
    for scenario in ['rain50','rain100']:
        p=DATA/'simulations'/f"{c['id']}-{scenario}.json";s=json.loads(p.read_text() if p.exists() else gzip.decompress(p.with_suffix('.json.gz').read_bytes()));assert s['calibrated'] is False and s['forcing_is_hypothetical'] is True
        a=np.array(s['frames']);assert a.shape==(17,64,64);assert np.isfinite(a).all() and a.min()>=0
        assert s['times_minutes']==list(range(0,241,15));assert s['summary']['numerical_checks_passed'];assert s['summary']['mass_relative_error']<1e-8
        total=s['summary']['rain_m3'];terms=s['summary']['infiltration_m3']+s['summary']['outflow_m3']+s['summary']['final_storage_m3']
        assert abs(total-terms)/max(total,1)<1e-8
        checks.append({'city':c['name'],'scenario':scenario,'mass_relative_error':s['summary']['mass_relative_error'],'max_depth_m':s['summary']['max_depth_m'],'froude_limited_fraction':s['summary']['froude_limited_fraction']})
report={'cities':38,'simulations':len(checks),'all_checks_passed':True,'worst_mass_relative_error':max(c['mass_relative_error'] for c in checks),'runs_with_max_depth_over_10m':[c for c in checks if c['max_depth_m']>10],
        'note':'Numerical integrity only, not local field validation. Deep isolated accumulations require terrain and drainage inspection.','checks':checks}
(ROOT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=1),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ['checks','runs_with_max_depth_over_10m']},indent=2))
print('Runs requiring review of deep accumulations:',len(report['runs_with_max_depth_over_10m']))
