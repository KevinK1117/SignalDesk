# SignalDesk – Vercel + Render

iPhone-optimierte Signal-PWA für Forex, Gold und Bitcoin. Candlestick-Chart, EMA20/EMA50-Signale, Entry, SL, TP1 1:2, TP2 1:3, TP3 1:4, theoretisches Risiko 5–10 €, Push nur für ausgewählten Markt. **Keine Brokeranbindung, keine Orders.**

## Verzeichnisstruktur

- `web/` – Vercel-Website mit PWA, SVG-Chart, Service Worker und Rewrite
- `server/` – Python-Server für Twelve Data, Signalberechnung, Push-Abos und VAPID
- `render.yaml` – Render-Blueprint mit persistentem Datenträger
- `scripts/generate_vapid.py` – VAPID-Schlüssel erzeugen
- `scripts/configure_vercel.py` – Render-Adresse in Vercel-Rewrite eintragen
- `INSTALLATION.md` – ausführliche deutschsprachige Anleitung

## Lokal testen

```bash
cd server
pip install -r requirements.txt
TWELVEDATA_API_KEY=DEIN_KEY python server.py
```

Der lokale Server stellt die API bereit; zum lokalen Test der `web/`-Dateien einen statischen Webserver nutzen und den Rewrite über Vercel testen. Web Push auf dem iPhone benötigt eine öffentlich erreichbare HTTPS-Domain.

**Deployment:** Zuerst Render, danach `web/vercel.json` mit der Render-URL aktualisieren und anschließend Vercel mit Root Directory `web` deployen.
