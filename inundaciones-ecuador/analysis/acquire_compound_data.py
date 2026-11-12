"""Cache public primary-source inputs with provenance. No terrain datum inferred."""
import concurrent.futures
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

ROOT=Path(__file__).parent
RAW=ROOT/'raw'/'compound-acquisition'
CATALOG='https://www.datosabiertos.gob.ec/api/3/action/package_show?id=altura-horaria-predicha-de-mareas'
METADATA='https://geoglows-v2.s3.us-west-2.amazonaws.com/tables/package-metadata-table.parquet'

def download(url,path):
    path=Path(path)
    if not path.exists():
        temporary=path.with_suffix(path.suffix+'.partial')
        with urllib.request.urlopen(url,timeout=90) as response,temporary.open('wb') as out:
            while block:=response.read(1024*1024):out.write(block)
        temporary.replace(path)
    return {'url':url,'file':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':hashlib.file_digest(path.open('rb'),'sha256').hexdigest()}

def main():
    RAW.mkdir(parents=True,exist_ok=True)
    catalog=download(CATALOG,RAW/'inocar-catalog.json')
    data=json.loads((RAW/'inocar-catalog.json').read_text(encoding='utf-8'))['result']
    resources=[x for x in data['resources'] if '2026' in x['name'] and x['format'].upper()=='CSV']
    if len(resources)!=1:raise ValueError('INOCAR resource requires manual review')
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        jobs=[pool.submit(download,resources[0]['url'],RAW/'inocar-predictions-resource2026.csv'),pool.submit(download,METADATA,RAW/'geoglows-metadata.parquet')]
        files=[catalog]+[x.result() for x in jobs]
    dictionary=next(x for x in data['resources'] if x['name'].startswith('INOCAR_Altura_Horaria_Predicha_DD'))
    extras=[(dictionary['url'],RAW/'inocar-dictionary.ods'),
            ('https://raw.githubusercontent.com/USEPA/swmm-nrtestsuite/dev/public/examples/Example2.inp',RAW/'EPA-Example2.inp'),
            ('https://raw.githubusercontent.com/USEPA/swmm-nrtestsuite/dev/public/examples/Example2.dat',RAW/'Example2.dat')]
    # Explicit candidates from the inspected metadata table; not verified hydraulic inlets.
    extras.extend((f'https://geoglows.ecmwf.int/api/v2/forecast/{ident}?format=json',RAW/f'forecast-{ident}.json') for ident in (670075133,670065947,670068009))
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        files.extend(pool.map(lambda args:download(*args),extras))
    manifest={'retrieved_utc':datetime.now(timezone.utc).isoformat(),'files':files,'inocar_license':data.get('license_id'),'inocar_resource':resources[0],
              'limitations':['Resource year/name must be checked against dates inside the file.','Tides are predictions in MLWS; no conversion to terrain datum asserted.','GEOGLOWS discharge is modeled, not gauge observation.','Nearest river outlets are candidates, not verified inlet locations.']}
    (RAW/'acquisition-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(files,indent=2))

if __name__=='__main__':main()
