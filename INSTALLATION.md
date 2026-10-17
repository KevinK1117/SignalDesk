# SignalDesk – Vercel + Render (iPhone)

## Architektur

- **Vercel**: statische iPhone-PWA unter HTTPS (`web/`).
- **Render**: ständig laufender Python-Signalserver (`server/`), pollt Twelve Data alle 65 Sekunden und verschickt Web Push über VAPID.
- **Vercel Rewrite**: Browser ruft `/api/...` auf; Vercel leitet diese Anfragen an Render weiter. Damit bleiben Push-Abos unter der iPhone-PWA-Domain.
- **Persistenz**: SQLite auf einem persistenten Render-Datenträger speichert Push-Abos und bereits verschickte Signalkerzen. Kein Broker, keine Orderausführung.

## Vorbereitungen

1. GitHub-Konto: https://github.com
2. Vercel-Konto: https://vercel.com
3. Render-Konto: https://render.com
4. Twelve Data API-Key: https://twelvedata.com (prüfe Abdeckung, Echtzeitstatus, Kreditbudget und API-Limits für EUR/USD, GBP/USD, USD/JPY, XAU/USD, BTC/USD; Tarife können sich ändern).
5. Für VAPID-Schlüssel lokal Python mit `cryptography` (oder eine vertrauenswürdige lokale Python-Umgebung). **Niemals private Schlüssel in GitHub einchecken.**

## 1. VAPID-Schlüssel erzeugen

Auf einem PC/Mac im Projektordner:

```bash
python -m pip install cryptography
python scripts/generate_vapid.py
```

Du erhältst `VAPID_PUBLIC_KEY` (eine einzelne Base64URL-Zeile) und `VAPID_PRIVATE_KEY` (vollständiger PEM-Block inklusive BEGIN/END-Zeilen). Beide kopieren und sicher aufbewahren. Die private PEM-Zeichenfolge darf nicht öffentlich sein. Bei Render kann der mehrzeilige PEM-Schlüssel als Environment-Variable eingefügt werden.

## 2. GitHub-Repository

Erstelle ein **privates** Repository und lade den gesamten Ordner hoch. Weder `.env` noch echte API-Keys oder VAPID-Schlüssel hochladen. `web/vercel.json` enthält anfangs eine Platzhalteradresse, die vor dem Vercel-Deploy ersetzt werden muss.

## 3. Render-Signalserver

1. Im Render-Dashboard `New` → `Blueprint` wählen und GitHub-Repository verbinden.
2. Die Datei `render.yaml` wird erkannt. Sie definiert einen Python-Web-Service mit **Starter-Instanz** und persistentem 1-GB-Datenträger. Dies ist normalerweise kostenpflichtig; aktuelle Preise direkt bei Render prüfen. Ein kostenloser schlafender Service ist für zuverlässige Überwachung ungeeignet.
3. Setze die Secret-Variablen:

   - `TWELVEDATA_API_KEY`: dein Twelve Data Schlüssel
   - `VAPID_PUBLIC_KEY`: die öffentliche Base64URL-Zeile
   - `VAPID_PRIVATE_KEY`: kompletter privater PEM-Block
   - `VAPID_SUBJECT`: `mailto:deine-adresse@beispiel.de` (eigene erreichbare Adresse)

4. Deploy starten. Notiere die Render-URL, beispielsweise `https://signaldesk-signalserver.onrender.com` (nur ein Beispiel).
5. Öffne `<RENDER-URL>/health` → erwartet `{"ok":true}`.
6. Öffne `<RENDER-URL>/api/state` → `configured: true`; warte bis `provider: "Twelve Data"` und `prices` Kurse enthält. Wenn `last_error` gesetzt ist, API-Tarif, Symbole und Quoten prüfen.
7. Öffne `<RENDER-URL>/api/push/config` → `enabled: true`.

**Achtung API-Budget:** Bei fünf Symbolen und 65 Sekunden Pollintervall werden grob 6.650 API-Anfragen pro Tag ausgelöst. Der kostenlose Datenplan kann dafür unzureichend sein. Bei Tarifproblemen `POLL_SECONDS` erhöhen (dann verzögern sich Signale) oder einen geeigneten Plan verwenden. Die Marktdaten sind nicht zwingend tick-echtzeitfähig.

## 4. Vercel vorbereiten

Ersetze im GitHub-Repository die Platzhalteradresse in `web/vercel.json` durch die echte Render-URL, z. B.:

```json
{
  "version": 2,
  "rewrites": [
    {"source": "/api/:path*", "destination": "https://DEIN-SERVER.onrender.com/api/:path*"}
  ]
}
```

Alternativ lokal ausführen und `web/vercel.json` danach committen:

```bash
python scripts/configure_vercel.py https://DEIN-SERVER.onrender.com
```

Bei Vercel `Add New → Project` → Repository importieren. **Root Directory: `web`**. Framework Preset: **Other**, Build Command: leer, Output Directory: leer (statische Dateien im Root). Deploy starten. Vercel vergibt eine HTTPS-Adresse wie `https://dein-projekt.vercel.app`.

Teste dort `/api/state`. Kommt JSON vom Render-Server zurück, funktioniert der Proxy. Die Web-App soll im Browser Marktpreise und Chart anzeigen, sobald der Signalserver Daten hat.

## 5. Auf iPhone installieren und Push aktivieren

1. iPhone mit iOS 16.4 oder neuer.
2. Vercel-HTTPS-Adresse in **Safari** öffnen.
3. Teilen → **Zum Home-Bildschirm** → Hinzufügen.
4. Die neue SignalDesk-App **vom Home-Bildschirm aus** öffnen (nicht nur Safari-Tab).
5. Gewünschten Markt auswählen, z. B. `XAU/USD`.
6. `Push aktivieren` drücken und die iOS-Berechtigung erteilen.
7. Prüfen, dass `Push aktiv: nur XAU/USD` angezeigt wird. Marktwechsel aktualisiert das serverseitige Abonnement. Beim nächsten bestätigten neuen Signal auf diesem Markt versucht der Server, eine Benachrichtigung zuzustellen – auch bei geschlossener App.

**Kein neues Signal = keine Push-Nachricht.** Die Implementierung sendet nicht bei jeder Kursaktualisierung. Zustellung hängt außerdem von iOS, Internet, Push-Dienst und dem laufenden Server ab.

## 6. Funktionsprüfung

- `https://DEIN-RENDER/health` → ok
- `https://DEIN-VERCEL/api/state` → JSON mit `configured: true`
- `https://DEIN-VERCEL/api/push/config` → `enabled: true`
- In der App Marktauswahl → Candlesticks / aktuelle Kurse
- `Push aktivieren` → Bestätigung für genau den ausgewählten Markt
- Markt wechseln → `Push aktiv: nur NEUER_MARKT`
- Auf echtes neues Signal warten; ohne solches Signal ist die Ende-zu-Ende-Push-Zustellung noch nicht bewiesen.

## Grenzen / Sicherheit

- **Kein Echtgeld, keine Demoorders, keine Brokeranbindung.** Es werden nur Signalvorschläge berechnet.
- Nur **5-Minuten-Kerzen**; EMA-Trendstrategie ist nicht backgetestet und garantiert keine Gewinne.
- **Entry** basiert auf dem Schlusskurs der bestätigten Kerze und kann bei Empfang bereits veraltet sein.
- SL-Abstand basiert auf Kerzen-Spannen, **nicht** auf 5–10 € Preisabstand. 5–10 € ist ein theoretisches monetäres Risiko bei einer berechneten Positionsgröße; Spread, Kontraktgröße, Pip-Wert, Gebühren, Slippage, Margin und Broker-Lots werden nicht berücksichtigt. Keine Ordergröße direkt übernehmen.
- Die App zeigt die **letzte erkannte** Signalkerze; diese kann älter sein. Kurszeiten und Feed-Status prüfen.
- Das Projekt ist ein **privater Prototyp**: API-Endpunkte und Push-Registrierung haben keine Benutzeranmeldung und kein Rate-Limiting. Vor öffentlicher Nutzung Authentifizierung, Abuse-Schutz, Monitoring und robuste Datenspeicherung ergänzen.
- Render-Persistenz ist wichtig: Ohne Datenträger gehen SQLite-Abos beim Neustart verloren.
- Vercel/Render und Twelve Data können Kosten verursachen. Die Bereitstellung ist noch nicht erfolgt; ein echter iPhone-Push-Test ist nach Deployment erforderlich.
