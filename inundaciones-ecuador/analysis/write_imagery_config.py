"""Build browser-public imagery config using explicitly restricted credentials.
Never log the token. The deployed browser can read this token by design.
"""
import argparse
import json
import os
from pathlib import Path


def write(output):
    token=os.environ.get('CESIUM_ION_PUBLIC_TOKEN','').strip()
    provider=os.environ.get('ECUADOR_IMAGERY_PROVIDER','google-ion').strip()
    if provider not in ('google-ion','google-maps','bing-ion'):
        raise ValueError('Unsupported imagery provider')
    asset=int(os.environ.get('CESIUM_IMAGERY_ASSET_ID','2' if provider=='bing-ion' else '3830182'))
    key=os.environ.get('GOOGLE_MAPS_PUBLIC_KEY','').strip()
    cfg={'provider':provider,'assetId':asset,'accessToken':token if provider!='google-maps' else '',
         'apiKey':key if provider=='google-maps' else ''}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text('window.ECUADOR_IMAGERY_CONFIG='+json.dumps(cfg,separators=(',',':'))+';\n',encoding='utf-8')
    print('Imagery config generated. Provider:',provider,'credential configured:',bool(key if provider=='google-maps' else token))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');a=p.parse_args();write(a.output)
