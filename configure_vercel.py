#!/usr/bin/env python3
"""Creates web/vercel.json with a same-origin proxy to the HTTPS signal server."""
import json,sys
from pathlib import Path
from urllib.parse import urlparse
if len(sys.argv)!=2:
 print('Aufruf: python scripts/configure_vercel.py https://signaldesk-signalserver.onrender.com')
 sys.exit(1)
url=sys.argv[1].rstrip('/')
p=urlparse(url)
if p.scheme!='https' or not p.netloc or p.path or p.query or p.fragment:
 sys.exit('Bitte die reine HTTPS-Serveradresse ohne Pfad angeben.')
config={'version':2,'rewrites':[{'source':'/api/:path*','destination':url+'/api/:path*'}]}
path=Path(__file__).resolve().parents[1]/'web'/'vercel.json'
path.write_text(json.dumps(config,indent=2)+'\n')
print('Erstellt:',path)
