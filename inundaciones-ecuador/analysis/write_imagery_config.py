"""Build a browser-public config from a dedicated assets:read / asset 2 token.
Never log the token. The deployed browser can read this token by design.
"""
import argparse
import json
import os
from pathlib import Path


def write(output):
    token=os.environ.get('CESIUM_ION_PUBLIC_TOKEN','').strip()
    cfg={'provider':'bing-ion','assetId':2,'accessToken':token}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text('window.ECUADOR_IMAGERY_CONFIG='+json.dumps(cfg,separators=(',',':'))+';\n',encoding='utf-8')
    print('Imagery config generated. Dedicated Bing token configured:',bool(token))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');a=p.parse_args();write(a.output)
