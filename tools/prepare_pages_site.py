"""Publish the active SIG release; retain historical packages in Git history."""
import argparse,json,pathlib,re,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
PREFIX='data/seguridad-riobamba/SIG_BRIDGE_RELEASES/'
SECURITY_PREFIX='data/seguridad-riobamba/'
def plan():
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
 included=[];excluded=[]
 for name in tracked:
  if name.startswith(PREFIX) and name[len(PREFIX):].split('/')[0] not in keep:excluded.append(name)
  elif name.startswith(SECURITY_PREFIX) and name[len(SECURITY_PREFIX):].split('/')[0] in archived_scenes:excluded.append(name)
  elif name.startswith(('.github/','sig-bridge/workspace/')):excluded.append(name)
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
