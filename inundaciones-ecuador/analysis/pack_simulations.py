"""Losslessly compress numerical runs for a GitHub Pages site near its size limit."""
import gzip,json,pathlib,shutil
ROOT=pathlib.Path(__file__).parent;FOLDER=ROOT/'dist/data/simulations';BACKUP=ROOT/'simulation-json-archive';BACKUP.mkdir(exist_ok=True)
count=0
for p in FOLDER.glob('*-rain*.json'):
    raw=p.read_bytes();packed=gzip.compress(raw,compresslevel=9,mtime=0)
    assert gzip.decompress(packed)==raw
    p.with_suffix('.json.gz').write_bytes(packed)
    target=BACKUP/p.name
    assert target.resolve().is_relative_to(ROOT.resolve())
    shutil.move(str(p),str(target));count+=1
print('Losslessly compressed simulations:',count)
