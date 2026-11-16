"""Losslessly compress national city detail JSON for the Pages size budget."""
from pathlib import Path
import gzip,re

def main():
    root=Path(__file__).resolve().parent/'dist/data';original=packed=0;count=0
    for p in root.glob('*.json'):
        if not re.fullmatch(r'\d+\.json',p.name):continue
        raw=p.read_bytes();data=gzip.compress(raw,compresslevel=9,mtime=0)
        assert gzip.decompress(data)==raw
        p.with_suffix('.json.gz').write_bytes(data)
        original+=len(raw);packed+=len(data);count+=1
    print('City detail compression:',count,'files;',original,'->',packed,'bytes; exact roundtrip')

if __name__=='__main__':main()
