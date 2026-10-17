#!/usr/bin/env python3
"""SignalDesk demo backend. Standard library only; never submits real orders."""
import os,json,time,math,threading,urllib.request,urllib.parse,datetime,random,sqlite3,secrets,concurrent.futures
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SYMBOLS={'EUR/USD':'EUR/USD','GBP/USD':'GBP/USD','USD/JPY':'USD/JPY','XAU/USD':'XAU/USD','BTC/USD':'BTC/USD'}
state={'prices':{},'candles':{},'positions':[],'events':[],'last_poll':0,'provider':'not configured','last_error':'','balance':10000.0,'next_id':1,'last_signal':{}}
lock=threading.RLock()
KEY=os.getenv('TWELVEDATA_API_KEY','').strip(); PORT=int(os.getenv('PORT','8765'))
AUTO=False # Keine Broker- oder Demo-Orderausführung
RISK=float(os.getenv('DEFAULT_RISK_EUR','5'))
RISK=max(5,min(10,RISK))
INTERVAL=max(30,int(os.getenv('POLL_SECONDS','65')))
VAPID_PUBLIC=os.getenv('VAPID_PUBLIC_KEY','').strip()
VAPID_PRIVATE=os.getenv('VAPID_PRIVATE_KEY','').strip()
VAPID_SUBJECT=os.getenv('VAPID_SUBJECT','').strip()
DB=Path(os.getenv('DATABASE_PATH',str(ROOT/'push.sqlite3')))
POLL_ENABLED=os.getenv('POLL_ENABLED','1')=='1'
def connect_db():
 DB.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(DB,timeout=10)
 c.execute('CREATE TABLE IF NOT EXISTS subscriptions (endpoint TEXT PRIMARY KEY, token TEXT NOT NULL, subscription TEXT NOT NULL, symbol TEXT NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS sent (symbol TEXT NOT NULL, bar TEXT NOT NULL, PRIMARY KEY(symbol,bar))')
 return c
with connect_db() as _db:_db.commit()
def dispatch_push(symbol,s):
 if not (VAPID_PUBLIC and VAPID_PRIVATE and VAPID_SUBJECT):return
 try:
  from pywebpush import webpush,WebPushException
 except ImportError:return
 with connect_db() as db:
  if db.execute('SELECT 1 FROM sent WHERE symbol=? AND bar=?',(symbol,s['bar'])).fetchone():return
  db.execute('INSERT INTO sent(symbol,bar) VALUES(?,?)',(symbol,s['bar']))
  db.commit()
  subscriptions=db.execute('SELECT endpoint,subscription FROM subscriptions WHERE symbol=?',(symbol,)).fetchall()
 sign=1 if s['direction']=='BUY' else -1
 d=s['distance'];e=s['entry'];f=lambda v:round(v,6)
 payload=json.dumps({'title':f"{symbol} · {s['direction']}",'body':f"Entry {f(e)} | SL {f(e-sign*d)} | TP1 {f(e+sign*2*d)} | TP2 {f(e+sign*3*d)} | TP3 {f(e+sign*4*d)}",'symbol':symbol,'bar':s['bar'],'url':'/'})
 for endpoint,raw in subscriptions:
  try:webpush(subscription_info=json.loads(raw),data=payload,vapid_private_key=VAPID_PRIVATE,vapid_claims={'sub':VAPID_SUBJECT},ttl=3600,timeout=10)
  except Exception as exc:
   if getattr(getattr(exc,'response',None),'status_code',None) in (404,410):
    with connect_db() as db:db.execute('DELETE FROM subscriptions WHERE endpoint=?',(endpoint,));db.commit()


def fetch_json(url,headers=None):
 req=urllib.request.Request(url,headers=headers or {'User-Agent':'SignalDeskDemo/1.0'})
 with urllib.request.urlopen(req,timeout=12) as r:return json.loads(r.read().decode())

def get_bars(symbol):
 params=urllib.parse.urlencode({'symbol':symbol,'interval':'5min','outputsize':'80','apikey':KEY,'format':'JSON'})
 j=fetch_json('https://api.twelvedata.com/time_series?'+params)
 if j.get('status')=='error' or 'values' not in j:raise ValueError(j.get('message','No candles returned'))
 rows=[]
 for x in reversed(j['values']):
  rows.append({'t':x['datetime'],'o':float(x['open']),'h':float(x['high']),'l':float(x['low']),'c':float(x['close'])})
 return rows

def ema(vals,n):
 e=vals[0]; k=2/(n+1)
 for v in vals[1:]:e=v*k+e*(1-k)
 return e

def signal(bars):
 # Only closed candles: provider latest bar may still be forming.
 bars=bars[:-1]
 if len(bars)<55:return None
 closes=[x['c'] for x in bars]; a=ema(closes[-50:],20); b=ema(closes[-50:],50)
 prev_a=ema(closes[-51:-1],20); prev_b=ema(closes[-51:-1],50)
 changes=[abs(bars[i]['h']-bars[i]['l']) for i in range(-15,-1)]
 atr=sum(changes)/len(changes)
 if atr<=0:return None
 # Trend continuation with confirmation of most recent closed bar.
 last=bars[-1]; prev=bars[-2]; direction=None
 if a>b and a>prev_a and last['c']>a and prev['c']<=prev_a and last['c']>prev['c']:direction='BUY'
 if a<b and a<prev_a and last['c']<a and prev['c']>=prev_a and last['c']<prev['c']:direction='SELL'
 if not direction:return None
 return {'direction':direction,'entry':last['c'],'distance':max(atr*1.5,last['c']*0.00015),'bar':last['t'],'reason':'EMA20/EMA50 Trend + Rückkehr über/unter EMA20; 5-Minuten-Schlusskurs'}

def poll():
 while True:
  if KEY:
   for symbol in SYMBOLS:
    try:
     bars=get_bars(symbol);s=signal(bars);price=bars[-1]['c']
     with lock:
      state['candles'][symbol]=bars;state['prices'][symbol]={'price':price,'time':bars[-1]['t']};state['provider']='Twelve Data';state['last_poll']=time.time()
      if s:
       state['last_signal'][symbol]=s
       # Send only once for each confirmed candle; never notify on repeated polls.
       threading.Thread(target=dispatch_push,args=(symbol,s),daemon=True).start()
      state['last_error']=''
    except Exception as e:
     with lock:state['last_error']=f'{symbol}: {e}'
  time.sleep(INTERVAL)

class Handler(BaseHTTPRequestHandler):
 def send(self,code,data):
  raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  if self.path=='/health':return self.send(200,{'ok':True})
  if self.path=='/api/push/config':return self.send(200,{'enabled':bool(VAPID_PUBLIC and VAPID_PRIVATE and VAPID_SUBJECT),'publicKey':VAPID_PUBLIC})
  if self.path=='/sw.js':
   raw=(ROOT/'sw.js').read_bytes();self.send_response(200);self.send_header('Content-Type','text/javascript');self.send_header('Cache-Control','no-cache');self.send_header('Content-Length',str(len(raw)));self.end_headers();return self.wfile.write(raw)
  if self.path=='/api/state':
   with lock:
    d={k:v for k,v in state.items() if k not in ('candles','positions','events','balance','next_id')};d.update({'configured':bool(KEY),'auto_demo':False,'risk_eur':RISK,'interval_seconds':INTERVAL,'broker':'none','note':'Nur Signale, keine Orders. Daten können verzögert sein.'})
   return self.send(200,d)
  if self.path.startswith('/api/candles?'):
   symbol=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('symbol',[''])[0]
   with lock:bars=state['candles'].get(symbol,[])
   return self.send(200,{'symbol':symbol,'candles':bars})
  if self.path in ('/','/index.html'):
   raw=(ROOT/'index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();return self.wfile.write(raw)
  if self.path=='/manifest.json':
   raw=(ROOT/'manifest.json').read_bytes();self.send_response(200);self.send_header('Content-Type','application/manifest+json');self.end_headers();return self.wfile.write(raw)
  self.send(404,{'error':'Not found'})
 def do_POST(self):
  if self.path in ('/api/push/subscribe','/api/push/unsubscribe'):
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 0<n<=8192:raise ValueError('Invalid payload size')
    d=json.loads(self.rfile.read(n))
    if self.path.endswith('unsubscribe'):
     endpoint=d['endpoint'];token=d['token']
     with connect_db() as db:db.execute('DELETE FROM subscriptions WHERE endpoint=? AND token=?',(endpoint,token));db.commit()
     return self.send(200,{'ok':True})
    if not (VAPID_PUBLIC and VAPID_PRIVATE and VAPID_SUBJECT):return self.send(503,{'error':'Push server not configured'})
    sub=d['subscription'];endpoint=sub['endpoint'];symbol=d['symbol']
    if symbol not in SYMBOLS or not endpoint.startswith('https://') or len(endpoint)>2048 or not sub.get('keys',{}).get('p256dh') or not sub['keys'].get('auth'):raise ValueError('Invalid subscription or market')
    token=d.get('token') or secrets.token_urlsafe(32)
    with connect_db() as db:
     old=db.execute('SELECT token FROM subscriptions WHERE endpoint=?',(endpoint,)).fetchone()
     if old and old[0]!=token:return self.send(403,{'error':'Subscription owned by another client'})
     db.execute('INSERT OR REPLACE INTO subscriptions VALUES(?,?,?,?)',(endpoint,token,json.dumps(sub),symbol));db.commit()
    return self.send(200,{'ok':True,'token':token,'symbol':symbol})
   except Exception as exc:return self.send(400,{'error':str(exc)})
  return self.send(404,{'error':'Keine Orderfunktion vorhanden'})
 def log_message(self,*args):pass

if __name__=='__main__':
 if POLL_ENABLED:threading.Thread(target=poll,daemon=True).start()
 print(f'SignalDesk: http://127.0.0.1:{PORT} | Live API configured: {bool(KEY)} | auto demo: {AUTO}')
 ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
