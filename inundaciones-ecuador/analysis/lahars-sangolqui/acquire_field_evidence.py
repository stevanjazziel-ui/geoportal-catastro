"""Acquire pinned, openly licensed historical geological vectors (no bulk imagery)."""
import hashlib, json, urllib.request
from pathlib import Path
from study_reference import ROOT


def main():
    folder=ROOT/'sources/1877-field-evidence';folder.mkdir(exist_ok=True)
    with urllib.request.urlopen('https://zenodo.org/api/records/5866730',timeout=60) as r:record=json.load(r)
    assert record['metadata']['license']['id']=='cc-by-4.0'
    (folder/'record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    audit=[]
    for f in record['files']:
        if not f['key'].endswith(('.shp','.shx','.dbf','.prj','.qpj','.cpg')):continue
        assert Path(f['key']).name==f['key']
        target=folder/f['key'];kind,expected=f['checksum'].split(':')
        assert kind=='md5'
        if not target.exists():
            with urllib.request.urlopen(f['links']['self'],timeout=60) as r:raw=r.read()
            assert len(raw)==f['size'] and hashlib.md5(raw).hexdigest()==expected
            target.write_bytes(raw)
        assert target.stat().st_size==f['size']
        assert hashlib.md5(target.read_bytes()).hexdigest()==expected
        audit.append({'name':f['key'],'bytes':f['size'],'md5':expected,
                      'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    (folder/'acquisition.json').write_text(json.dumps({'doi':'10.5281/zenodo.5866730','license':'CC-BY-4.0',
         'attribution':'Andrade, Saltos, Nogales, Cruz, Lee and Barclay (2022)',
         'purpose':'Historical proximal deposit and fieldwork evidence; not a future maximum-flow footprint or DEM',
         'files':audit},indent=2),encoding='utf-8')
    import geopandas as gpd
    for name in ('1877-Deposit-Polygones','1877-fieldwork points','1877-Deposit-Contacts'):
        data=gpd.read_file(folder/(name+'.shp'))
        print(name,'n=',len(data),'crs=',data.crs,'invalid=',int((~data.is_valid).sum()),'bounds=',data.to_crs(4326).total_bounds,flush=True)


if __name__=='__main__':main()
