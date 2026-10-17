
#!/usr/bin/env python3
"""SignalDesk backend: market signals and web push, no broker orders."""

import os
import json
import time
import threading
import urllib.request
import urllib.parse
import sqlite3
import secrets

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SYMBOLS = {
    'EUR/USD': 'EUR/USD',
    'GBP/USD': 'GBP/USD',
    'USD/JPY': 'USD/JPY',
    'XAU/USD': 'XAU/USD',
    'BTC/USD': 'BTC/USD'
}

state = {
    'prices': {},
    'candles': {},
    'positions': [],
    'events': [],
    'last_poll': 0,
    'provider': 'not configured',
    'last_error': '',
    'balance': 10000.0,
    'next_id': 1,
    'last_signal': {}
}

lock = threading.RLock()

KEY = os.getenv('TWELVEDATA_API_KEY', '').strip()
PORT = int(os.getenv('PORT', '8765'))
AUTO = False

RISK = float(os.getenv('DEFAULT_RISK_EUR', '5'))
RISK = max(5, min(10, RISK))

# Five markets: at least 10 minutes per full polling round.
INTERVAL = max(600, int(os.getenv('POLL_SECONDS', '600')))

VAPID_PUBLIC = os.getenv('VAPID_PUBLIC_KEY', '').strip()
VAPID_PRIVATE = os.getenv('VAPID_PRIVATE_KEY', '').strip()
VAPID_SUBJECT = os.getenv('VAPID_SUBJECT', '').strip()

DB = Path(os.getenv(
    'DATABASE_PATH',
    str(ROOT / 'push.sqlite3')
))

POLL_ENABLED = os.getenv('POLL_ENABLED', '1') == '1'


def connect_db():
    DB.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB, timeout=10)

    connection.execute(
        'CREATE TABLE IF NOT EXISTS subscriptions '
        '(endpoint TEXT PRIMARY KEY, token TEXT NOT NULL, '
        'subscription TEXT NOT NULL, symbol TEXT NOT NULL)'
    )

    connection.execute(
        'CREATE TABLE IF NOT EXISTS sent '
        '(symbol TEXT NOT NULL, bar TEXT NOT NULL, '
        'PRIMARY KEY(symbol,bar))'
    )

    return connection


with connect_db() as _db:
    _db.commit()


def dispatch_push(symbol, s):
    if not (
        VAPID_PUBLIC
        and VAPID_PRIVATE
        and VAPID_SUBJECT
    ):
        return

    try:
        from pywebpush import webpush
    except ImportError:
        return

    with connect_db() as db:
        already_sent = db.execute(
            'SELECT 1 FROM sent WHERE symbol=? AND bar=?',
            (symbol, s['bar'])
        ).fetchone()

        if already_sent:
            return

        db.execute(
            'INSERT INTO sent(symbol,bar) VALUES(?,?)',
            (symbol, s['bar'])
        )
        db.commit()

        subscriptions = db.execute(
            'SELECT endpoint,subscription FROM subscriptions '
            'WHERE symbol=?',
            (symbol,)
        ).fetchall()

    sign = 1 if s['direction'] == 'BUY' else -1
    distance = s['distance']
    entry = s['entry']

    def rounded(value):
        return round(value, 6)

    payload = json.dumps({
        'title': f"{symbol} · {s['direction']}",
        'body': (
            f"Entry {rounded(entry)} | "
            f"SL {rounded(entry - sign * distance)} | "
            f"TP1 {rounded(entry + sign * 2 * distance)} | "
            f"TP2 {rounded(entry + sign * 3 * distance)} | "
            f"TP3 {rounded(entry + sign * 4 * distance)}"
        ),
        'symbol': symbol,
        'bar': s['bar'],
        'url': '/'
    })

    for endpoint, raw in subscriptions:
        try:
            webpush(
                subscription_info=json.loads(raw),
                data=payload,
                vapid_private_key=VAPID_PRIVATE,
                vapid_claims={'sub': VAPID_SUBJECT},
                ttl=3600,
                timeout=10
            )
        except Exception as exc:
            response = getattr(exc, 'response', None)
            status = getattr(response, 'status_code', None)

            if status in (404, 410):
                with connect_db() as db:
                    db.execute(
                        'DELETE FROM subscriptions WHERE endpoint=?',
                        (endpoint,)
                    )
                    db.commit()


def fetch_json(url, headers=None):
    request = urllib.request.Request(
        url,
        headers=headers or {
            'User-Agent': 'SignalDeskDemo/1.0'
        }
    )

    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode())


def get_bars(symbol):
    params = urllib.parse.urlencode({
        'symbol': symbol,
        'interval': '5min',
        'outputsize': '80',
        'apikey': KEY,
        'format': 'JSON'
    })

    data = fetch_json(
        'https://api.twelvedata.com/time_series?' + params
    )

    if data.get('status') == 'error' or 'values' not in data:
        raise ValueError(
            data.get('message', 'No candles returned')
        )

    rows = []

    for candle in reversed(data['values']):
        rows.append({
            't': candle['datetime'],
            'o': float(candle['open']),
            'h': float(candle['high']),
            'l': float(candle['low']),
            'c': float(candle['close'])
        })

    return rows


def ema(values, period):
    result = values[0]
    multiplier = 2 / (period + 1)

    for value in values[1:]:
        result = (
            value * multiplier
            + result * (1 - multiplier)
        )

    return result


def signal(bars):
    # Ignore the latest candle, which may still be forming.
    bars = bars[:-1]

    if len(bars) < 55:
        return None

    closes = [bar['c'] for bar in bars]

    fast_ema = ema(closes[-50:], 20)
    slow_ema = ema(closes[-50:], 50)

    previous_fast = ema(closes[-51:-1], 20)
    previous_slow = ema(closes[-51:-1], 50)

    changes = [
        abs(bars[i]['h'] - bars[i]['l'])
        for i in range(-15, -1)
    ]

    atr = sum(changes) / len(changes)

    if atr <= 0:
        return None

    last = bars[-1]
    previous = bars[-2]
    direction = None

    if (
        fast_ema > slow_ema
        and fast_ema > previous_fast
        and last['c'] > fast_ema
        and previous['c'] <= previous_fast
        and last['c'] > previous['c']
    ):
        direction = 'BUY'

    if (
        fast_ema < slow_ema
        and fast_ema < previous_fast
        and last['c'] < fast_ema
        and previous['c'] >= previous_fast
        and last['c'] < previous['c']
    ):
        direction = 'SELL'

    if not direction:
        return None

    return {
        'direction': direction,
        'entry': last['c'],
        'distance': max(
            atr * 1.5,
            last['c'] * 0.00015
        ),
        'bar': last['t'],
        'reason': (
            'EMA20/EMA50 Trend + Rückkehr über/unter EMA20; '
            '5-Minuten-Schlusskurs'
        )
    }


def poll():
    backoff = 0

    while True:
        rate_limited = False

        if KEY:
            for symbol in SYMBOLS:
                try:
                    bars = get_bars(symbol)
                    current_signal = signal(bars)
                    price = bars[-1]['c']

                    with lock:
                        state['candles'][symbol] = bars
                        state['prices'][symbol] = {
                            'price': price,
                            'time': bars[-1]['t']
                        }
                        state['provider'] = 'Twelve Data'
                        state['last_poll'] = time.time()
                        state['last_error'] = ''

                        if current_signal:
                            state['last_signal'][symbol] = (
                                current_signal
                            )

                    if current_signal:
                        threading.Thread(
                            target=dispatch_push,
                            args=(symbol, current_signal),
                            daemon=True
                        ).start()

                except Exception as exc:
                    error = str(exc)

                    with lock:
                        state['last_error'] = (
                            f'{symbol}: {error}'
                        )

                    print(
                        f'Market data error for {symbol}: {error}',
                        flush=True
                    )

                    error_lower = error.lower()

                    if (
                        '429' in error_lower
                        or 'rate limit' in error_lower
                        or 'credits' in error_lower
                        or 'too many requests' in error_lower
                    ):
                        rate_limited = True
                        break

        if rate_limited:
            backoff = min(
                3600,
                max(900, backoff * 2)
            )

            print(
                f'API limit reached. Waiting {backoff} seconds.',
                flush=True
            )
        else:
            backoff = 0

        time.sleep(max(INTERVAL, backoff))


class Handler(BaseHTTPRequestHandler):

    def send(self, code, data):
        raw = json.dumps(
            data,
            ensure_ascii=False,
            allow_nan=False
        ).encode()

        self.send_response(code)
        self.send_header(
            'Content-Type',
            'application/json; charset=utf-8'
        )
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path

        if path == '/health':
            return self.send(200, {'ok': True})

        if path == '/api/push/config':
            return self.send(200, {
                'enabled': bool(
                    VAPID_PUBLIC
                    and VAPID_PRIVATE
                    and VAPID_SUBJECT
                ),
                'publicKey': VAPID_PUBLIC
            })

        if path == '/sw.js':
            raw = (ROOT / 'sw.js').read_bytes()

            self.send_response(200)
            self.send_header(
                'Content-Type',
                'text/javascript'
            )
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()

            return self.wfile.write(raw)

        if path == '/api/state':
            with lock:
                data = {
                    key: value
                    for key, value in state.items()
                    if key not in (
                        'candles',
                        'positions',
                        'events',
                        'balance',
                        'next_id'
                    )
                }

                data.update({
                    'configured': bool(KEY),
                    'auto_demo': False,
                    'risk_eur': RISK,
                    'interval_seconds': INTERVAL,
                    'broker': 'none',
                    'note': (
                        'Nur Signale, keine Orders. '
                        'Daten können verzögert sein.'
                    )
                })

            return self.send(200, data)

        if path == '/api/candles':
            symbol = urllib.parse.parse_qs(
                parsed.query
            ).get('symbol', [''])[0]

            with lock:
                bars = state['candles'].get(symbol, [])

            return self.send(200, {
                'symbol': symbol,
                'candles': bars
            })

        if path in ('/', '/index.html'):
            raw = (ROOT / 'index.html').read_bytes()

            self.send_response(200)
            self.send_header(
                'Content-Type',
                'text/html; charset=utf-8'
            )
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()

            return self.wfile.write(raw)

        if path == '/manifest.json':
            raw = (ROOT / 'manifest.json').read_bytes()

            self.send_response(200)
            self.send_header(
                'Content-Type',
                'application/manifest+json'
            )
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()

            return self.wfile.write(raw)

        return self.send(404, {
            'error': 'Not found'
        })

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path

        if path in (
            '/api/push/subscribe',
            '/api/push/unsubscribe'
        ):
            try:
                length = int(
                    self.headers.get('Content-Length', '0')
                )

                if not 0 < length <= 8192:
                    raise ValueError('Invalid payload size')

                data = json.loads(
                    self.rfile.read(length)
                )

                if path == '/api/push/unsubscribe':
                    endpoint = data['endpoint']
                    token = data['token']

                    with connect_db() as db:
                        db.execute(
                            'DELETE FROM subscriptions '
                            'WHERE endpoint=? AND token=?',
                            (endpoint, token)
                        )
                        db.commit()

                    return self.send(200, {'ok': True})

                if not (
                    VAPID_PUBLIC
                    and VAPID_PRIVATE
                    and VAPID_SUBJECT
                ):
                    return self.send(503, {
                        'error': 'Push server not configured'
                    })

                subscription = data['subscription']
                endpoint = subscription['endpoint']
                symbol = data['symbol']

                keys = subscription.get('keys', {})

                if (
                    symbol not in SYMBOLS
                    or not endpoint.startswith('https://')
                    or len(endpoint) > 2048
                    or not keys.get('p256dh')
                    or not keys.get('auth')
                ):
                    raise ValueError(
                        'Invalid subscription or market'
                    )

                token = (
                    data.get('token')
                    or secrets.token_urlsafe(32)
                )

                with connect_db() as db:
                    old = db.execute(
                        'SELECT token FROM subscriptions '
                        'WHERE endpoint=?',
                        (endpoint,)
                    ).fetchone()

                    if old and old[0] != token:
                        return self.send(403, {
                            'error': (
                                'Subscription owned '
                                'by another client'
                            )
                        })

                    db.execute(
                        'INSERT OR REPLACE INTO subscriptions '
                        'VALUES(?,?,?,?)',
                        (
                            endpoint,
                            token,
                            json.dumps(subscription),
                            symbol
                        )
                    )
                    db.commit()

                return self.send(200, {
                    'ok': True,
                    'token': token,
                    'symbol': symbol
                })

            except Exception as exc:
                return self.send(400, {
                    'error': str(exc)
                })

        return self.send(404, {
            'error': 'Keine Orderfunktion vorhanden'
        })

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    if POLL_ENABLED:
        threading.Thread(
            target=poll,
            daemon=True
        ).start()

    print(
        f'SignalDesk: http://127.0.0.1:{PORT} '
        f'| Live API configured: {bool(KEY)} '
        f'| auto demo: {AUTO}',
        flush=True
    )

    ThreadingHTTPServer(
        ('0.0.0.0', PORT),
        Handler
    ).serve_forever()
