# SignalDesk – H1 Trading Dashboard

Next.js-App mit Candlestick-Charts für EURUSD, GBPUSD, USDJPY und AUDUSD. Regelbasierte Signale auf **abgeschlossenen** 1h-Kerzen: EMA20/50/200-Trend und EMA20-Crossover; SL 1,5 × ATR(14), Ziele 1R/2R/3R.

## Lokal starten

1. `npm install`
2. `.env.example` nach `.env.local` kopieren und API-Key von https://twelvedata.com eintragen.
3. `npm run dev` und http://localhost:3000 öffnen.

## GitHub und Vercel

1. Neues GitHub-Repository erstellen, Projektdateien hochladen oder mit `git init && git add . && git commit -m "Initial commit" && git branch -M main && git remote add origin <DEINE_GITHUB_REPO_URL> && git push -u origin main` pushen.
2. Auf https://vercel.com/new GitHub-Repository importieren.
3. Unter **Environment Variables** `TWELVEDATA_API_KEY` hinterlegen.
4. Deploy klicken. Änderungen an `main` werden automatisch deployed.

**Wichtig:** Twelve Data kann je nach Plan H1-Forex, Gold und BTC einschränken. API-Fehler werden sichtbar angezeigt. Das Dashboard handelt nicht automatisch und gibt keine Gewinngarantie. Ein Signal wird nur auf der neuesten abgeschlossenen Kerze gezeigt, nicht als dauerhaft offene Position. Für produktiven Einsatz Marktdatenlizenz, Rate Limits, Backtests und Risikomanagement prüfen.

## Multi-Indikator-Signale (H1)

Signale werden auf der letzten **abgeschlossenen** Stundenkerze berechnet. Die Strategie prüft EMA 20/50/200, RSI(14), MACD(12/26/9), ADX(14) mit Richtungsindikatoren sowie EMA20-Kerzenmomentum. LONG/SHORT erfordert mindestens 4 von 5 Bestätigungen, wobei EMA-Trend und ADX zwingend übereinstimmen müssen. Der Stop-Loss liegt 1,5 ATR(14) vom Schlusskurs entfernt; TP1, TP2, TP3 liegen bei 1R, 2R und 3R. Signale sind experimentell, nicht backgetestet und können bei jeder neuen H1-Kerze verschwinden. Es werden keine Trades platziert.

## Erweiterte Price-Action-Filter

Zusätzlich zu den 5 technischen Indikatoren prüft die App 4 regelbasierte Price-Action-Kriterien: Support/Resistance (48 abgeschlossene Kerzen), Order-Block-**Näherung** (Gegenkerze vor starkem Impuls), Fair Value Gap (Drei-Kerzen-Lücke mit Kursnähe) und Liquidity Sweep (Stich über/unter ein 20-Kerzen-Extrem und Schluss zurück in der Range). Ein Signal erfordert **mindestens 2 von 4** passende Price-Action-Filter zusätzlich zu den bisherigen 4/5 Indikatoren (EMA + ADX Pflicht). Alle Prüfungen nutzen ausschließlich abgeschlossene H1-Kerzen; die Erkennung von Order Blocks und Liquidität ist eine vereinfachte Preisaktions-Heuristik, keine Einsicht in echte Orderbücher. Die Signale sind **nicht backgetestet** und nicht als Handelsgarantie zu verstehen.


## Forex-only-Version
XAUUSD bleibt entfernt. BTCUSD und ETHUSD sind wieder auswählbar. Die Client-Abfrage erfolgt alle 15 Minuten; serverseitiges Caching ist auf 15 Minuten konfiguriert. API-Credits sind trotzdem abhängig von Twelve-Data-Abrechnung und Vercel-Cache-Verhalten.

## iPhone-App-Icon
`app/apple-icon.png` (180×180) und `app/icon.png` (512×512) sind enthalten.
`app/layout.tsx` registriert die Icons und den Web-App-Modus.
Nach GitHub-Commit und erfolgreichem Vercel-Deployment das alte SignalDesk-Symbol
vom Home-Bildschirm entfernen und die Website in Safari erneut über
Teilen → Zum Home-Bildschirm hinzufügen installieren.

## 1H-Daten und Chart-Level (Optimierung)
- Server validiert OHLC, UTC-Stundenraster, Duplikate und ausschließlich abgeschlossene Stundenkerzen.
- Der Chart verwendet nur sortierte, eindeutige, abgeschlossene 1H-Kerzen.
- Bei aktivem Signal sind ENTRY (blau), SL (rot) und TP1–TP3 (grün) als beschriftete Preislinien sichtbar.
- Kein Signal wird erfunden, wenn die Strategie keine Übereinstimmung findet.
- Server-Fetch und Browser-Polling nutzen weiter stündliche Cache-Intervalle; Vercel-Cache ist nicht garantiert persistent.
- Achtung: Forex-Marktdaten können Wochenend-Lücken enthalten; es werden keine künstlichen Kerzen eingefügt.


## Neue Kryptomärkte
BTCUSD (Bitcoin/USD) und ETHUSD (Ethereum/USD) sind zusätzlich auswählbar.
Der API-Endpunkt verwendet bei Twelve Data die Symbole `BTC/USD` und `ETH/USD`.
Die Verfügbarkeit hängt vom Twelve-Data-Tarif ab. Der API-Fehler wird angezeigt,
wenn ein Symbol nicht unterstützt wird. Jede weitere Symbolabfrage kann Credits verbrauchen.
`ETC` steht für Ethereum, nicht für Ether (`ETH`).
