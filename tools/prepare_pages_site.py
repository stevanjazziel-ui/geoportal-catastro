"""Publish the active SIG release; retain historical packages in Git history."""
import argparse,json,pathlib,re,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
PREFIX='data/seguridad-riobamba/SIG_BRIDGE_RELEASES/'
SECURITY_PREFIX='data/seguridad-riobamba/'
RIO_PREFIX='inundaciones-ecuador/data/riobamba-local/'
LAHAR_PREFIX='inundaciones-ecuador/data/sangolqui-lahars/'
SHOBOL_PREFIX='shobol-llinllin/data/shobol/'


def shobol_raw_asset(name):
 if not name.startswith(SHOBOL_PREFIX):return False
 asset=name.removeprefix(SHOBOL_PREFIX)
 return asset.startswith('photos/') or asset in {
  'drenaje_d8.geojson','nube-sfm.json','tileset.json','superficie-fotogrametrica-parcial.glb',
 }

def lahar_page_payloads():
 path=ROOT/LAHAR_PREFIX/'manifest.json'
 if not path.exists():return None
 m=json.loads(path.read_text(encoding='utf-8'))
 assets=[m[k] for k in ('geometry','terrain','regional','buildings') if k in m]
 assets += [a for c in m['cases'] for a in (c,c['max_asset'])]
 for a in assets:
  assert pathlib.PurePosixPath(a['file']).name==a['file'],'Ruta de payload fuera del directorio'
 return {LAHAR_PREFIX+a['file'] for a in assets if a.get('payload_delivery')!='github_raw'} | {LAHAR_PREFIX+'municipal-terrain-samples.csv.gz'}

def archived_rain_assets():
 manifest_path=ROOT/RIO_PREFIX/'manifest.json'
 if not manifest_path.exists():return set()
 manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
 previous=manifest.get('previous_scenarios')
 if not previous:return set()
 assert pathlib.PurePosixPath(previous).name==previous,'Archivo historico fuera del directorio local'
 old=json.loads((ROOT/RIO_PREFIX/previous).read_text(encoding='utf-8'))
 def assets(cases):
  return {RIO_PREFIX+value for case in cases for key in ('file','report','network_input_file','network_report_file')
          if isinstance(value:=case.get(key),str) and pathlib.PurePosixPath(value).name==value}
 return assets(old['cases'])-assets(manifest['cases'])

def plan():
 rio=json.loads((ROOT/RIO_PREFIX/'manifest.json').read_text(encoding='utf-8'))
 page_payloads={RIO_PREFIX+c['file'] for c in rio['cases'] if c.get('payload_delivery')=='pages'}
 active=json.loads((ROOT/'sig-bridge-active.json').read_text(encoding='utf-8'))['releaseId'];keep={active}
 tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0');tracked=[p for p in tracked if p]
 runtime=[]
 for name in tracked:
  if pathlib.Path(name).suffix.lower() not in ['.html','.js'] or name.startswith(('data/','tools/','sig-bridge/')):continue
  text=(ROOT/name).read_text(encoding='utf-8',errors='replace');runtime.append(text)
  keep.update(re.findall(r'SIG_BRIDGE_RELEASES/([A-Za-z0-9_-]+)/',text))
 runtime='\n'.join(runtime)
 scene_names={name[len(SECURITY_PREFIX):].split('/')[0] for name in tracked if name.startswith(SECURITY_PREFIX) and '/' in name[len(SECURITY_PREFIX):]}
 archived_scenes={name for name in scene_names if name!='SIG_BRIDGE_RELEASES' and name not in runtime}
 archived_rain=archived_rain_assets()
 lahar_payloads=lahar_page_payloads()
 included=[];excluded=[]
 for name in tracked:
  if name.startswith(PREFIX) and name[len(PREFIX):].split('/')[0] not in keep:excluded.append(name)
  elif name.startswith(SECURITY_PREFIX) and name[len(SECURITY_PREFIX):].split('/')[0] in archived_scenes:excluded.append(name)
  elif name.startswith(('.github/','sig-bridge/workspace/','inundaciones-ecuador/model-archives/')):excluded.append(name)
  elif name in archived_rain:excluded.append(name)
  elif name==LAHAR_PREFIX+'referencia-lidar/terreno-lidar-1m.tif':excluded.append(name)
  elif name.startswith(LAHAR_PREFIX) and name.endswith('.gz') and lahar_payloads is not None and name not in lahar_payloads:excluded.append(name)
  elif name.startswith(RIO_PREFIX) and name.endswith('.u16.gz') and name not in page_payloads:excluded.append(name)
  elif shobol_raw_asset(name):excluded.append(name)
  elif re.fullmatch(r'inundaciones-ecuador/data/\d+\.json',name) and name+'.gz' in tracked:excluded.append(name)
  else:included.append(name)
 for name in ['visor-seguridad-riobamba-v2.html','sig-bridge-active.json',PREFIX+active+'/ESCENARIO_FINAL_183.gpkg',PREFIX+active+'/ENTREGA_POLICIA_KDE.zip']:
  assert name in included,'Falta dependencia publicada: '+name
 for name in included:
  p=ROOT/name
  assert p.is_file() and not p.is_symlink(),'Fuente no regular: '+name
 assert sum((ROOT/name).stat().st_size for name in included)<1_000_000_000,'El sitio supera el limite de 1 GB sin comprimir de GitHub Pages'
 return included,excluded,keep
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--plan',action='store_true');parser.add_argument('--output',default='_gh_pages');args=parser.parse_args()
 included,excluded,keep=plan();report={'retainedSigReleases':sorted(keep),'includedFiles':len(included),'excludedFiles':len(excluded),'includedBytes':sum((ROOT/n).stat().st_size for n in included),'excludedHistoricalBytes':sum((ROOT/n).stat().st_size for n in excluded),'historyDeleted':False}
 if not args.plan:
  dest=(ROOT/args.output).resolve();assert dest.is_relative_to(ROOT) and dest!=ROOT and not dest.exists(),'Usar una carpeta nueva dentro del workspace'
  dest.mkdir()
  for name in included:
   p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
  (dest/'PUBLICATION_MANIFEST.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
