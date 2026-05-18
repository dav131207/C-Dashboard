# Instagram Analytics Dashboard

Ein selbst-gehostetes, vollständig kostenloses Analytics-Dashboard für Instagram Business Accounts. Daten kommen direkt von der offiziellen Instagram Graph API, werden täglich via GitHub Action aktualisiert und auf Streamlit Community Cloud visualisiert.

**Tech-Stack:** Python · Streamlit · Instagram Graph API · GitHub Actions
**Kosten:** 0,00 € / Monat

---

## Features

- Reichweite, Views, Likes, Kommentare, Saves, Shares pro Post
- KPI-Übersicht mit Datumsfilter (default 2025)
- Top-/Flop-Posts Ranking mit Direktlink zu Instagram
- Format-Vergleich (Reels / Karussell / Bild / Video)
- Posting-Zeit-Heatmap (Wochentag × Stunde)
- Follower-Wachstum über Zeit (tägliche Snapshots)
- Tägliche automatische Aktualisierung

---

## Setup-Anleitung

### Schritt 1 — Voraussetzungen

- [ ] Instagram **Business** oder **Creator** Account (kein Privatkonto)
- [ ] Mit einer Facebook Page verknüpft (Pflicht für die Graph API)
- [ ] Facebook-Account (für Meta Developer)
- [ ] GitHub-Account (kostenlos)

### Schritt 2 — Meta Developer App erstellen

1. Gehe auf [developers.facebook.com](https://developers.facebook.com/) und logge dich ein.
2. Klicke auf **"Meine Apps"** → **"App erstellen"**.
3. Wähle als App-Typ: **"Business"**.
4. Gib einen Namen ein (z. B. "IG Dashboard"), eine Kontakt-E-Mail, und erstelle die App.
5. Im Dashboard der neuen App: **"Produkte hinzufügen"** → **"Instagram Graph API"** → **"Einrichten"**.

### Schritt 3 — IG Business Account ID + Token holen

1. Öffne den **[Graph API Explorer](https://developers.facebook.com/tools/explorer/)**.
2. Wähle oben rechts deine App.
3. Klicke **"Generate Access Token"** und gib folgende Berechtigungen frei:
   - `instagram_basic`
   - `instagram_manage_insights`
   - `pages_show_list`
   - `pages_read_engagement`
   - `business_management`
4. Wähle deine FB-Seite aus, die mit dem IG-Account verknüpft ist.
5. **Page Access Token holen:**
   - Im Explorer: `GET` → `me/accounts`
   - Du bekommst eine Liste deiner Pages mit `access_token` und `id`.
   - Notiere die `id` der relevanten Page.
6. **IG Business Account ID holen:**
   - `GET` → `{page-id}?fields=instagram_business_account`
   - Antwort enthält `instagram_business_account.id` — **das ist deine `INSTAGRAM_USER_ID`**.

### Schritt 4 — Long-Lived Token generieren (60 Tage)

Der Token aus dem Explorer hält nur 1–2 Stunden. Tausche ihn so gegen einen Long-Lived-Token:

```bash
curl -i -X GET "https://graph.facebook.com/v21.0/oauth/access_token?\
grant_type=fb_exchange_token&\
client_id={APP_ID}&\
client_secret={APP_SECRET}&\
fb_exchange_token={SHORT_LIVED_TOKEN}"
```

- `APP_ID` + `APP_SECRET` findest du in den App-Einstellungen → **Einstellungen → Allgemein**.
- `SHORT_LIVED_TOKEN` ist der Page-Access-Token aus Schritt 3.

Die Antwort enthält den **Long-Lived-Token (60 Tage gültig)** — **das ist dein `INSTAGRAM_ACCESS_TOKEN`**.

> ⚠️ Token alle ~50 Tage erneuern (selber Curl-Call, aktueller Token als `fb_exchange_token`). Das Skript warnt dich beim Fetch, wenn nur noch <10 Tage bleiben.

### Schritt 5 — Lokal testen (optional aber empfohlen)

```bash
git clone <dein-repo>
cd instagram_dashboard
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# .env editieren und Werte eintragen

# Daten holen
export $(cat .env | xargs)  # Windows: PowerShell-Variante nutzen
python fetch_data.py

# Dashboard starten
streamlit run app.py
```

Öffnet sich unter `http://localhost:8501`. Wenn das funktioniert → weiter zu Schritt 6.

### Schritt 6 — GitHub Repo aufsetzen

1. Neues **privates** Repo erstellen (Daten sind sensibel, auch wenn keine Tokens drin sind).
2. Projekt-Dateien hochladen:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<dein-user>/<dein-repo>.git
   git push -u origin main
   ```
3. Im Repo: **Settings → Secrets and variables → Actions → New repository secret**. Zwei Secrets anlegen:
   - `INSTAGRAM_ACCESS_TOKEN` = dein Long-Lived-Token
   - `INSTAGRAM_USER_ID` = deine IG Business Account ID
4. **Actions** Tab → "Refresh Instagram Data" Workflow → **"Run workflow"** zum ersten Mal manuell starten. Nach ~1 Min sollte `data/instagram_data.json` im Repo erscheinen.

### Schritt 7 — Streamlit Cloud Deployment

1. [share.streamlit.io](https://share.streamlit.io/) → mit GitHub anmelden.
2. **"New app"** → wähle dein Repo, Branch `main`, Hauptdatei `app.py`.
3. **Deploy** klicken. Nach ~2 Min ist deine App online.
4. (Optional) In den App-Settings unter **"Sharing"** → "Private" stellen, damit nur eingeloggte Personen Zugriff haben.

✅ Fertig. Ab jetzt läuft alles vollautomatisch:
- GitHub Action holt täglich um 03:00 UTC die aktuellen Daten
- Commit im Repo triggert Streamlit-Cloud-Redeploy
- Dashboard zeigt immer die aktuellen Zahlen

---

## Token-Renewal-Reminder

Long-Lived-Tokens halten 60 Tage. Beim Refresh läuft im Fetch-Skript eine Prüfung — die Action loggt Warnungen, wenn der Token bald abläuft. Trage dir vorsorglich alle 50 Tage einen Kalender-Reminder ein.

So erneuerst du ihn:
```bash
curl -i -X GET "https://graph.facebook.com/v21.0/oauth/access_token?\
grant_type=fb_exchange_token&\
client_id={APP_ID}&\
client_secret={APP_SECRET}&\
fb_exchange_token={CURRENT_TOKEN}"
```
Neuen Token in GitHub Secrets aktualisieren — fertig.

---

## Projekt-Struktur

```
.
├── app.py                          # Streamlit-Dashboard
├── fetch_data.py                   # IG-API-Fetcher
├── requirements.txt                # Python-Deps
├── .env.example                    # Template für lokale Env-Vars
├── .gitignore
├── .github/
│   └── workflows/
│       └── refresh.yml             # GitHub Action für tägliches Refresh
└── data/                           # Generierte Daten (vom Skript befüllt)
    ├── instagram_data.json
    └── follower_history.json
```

---

## Troubleshooting

**"Invalid OAuth access token"** → Token abgelaufen, neu generieren.

**"Tried accessing nonexisting field instagram_business_account"** → IG-Konto ist nicht mit der FB-Page verknüpft, oder kein Business-Account.

**"(#100) Tried accessing nonexisting field..."** → API-Version-Mismatch. Setze `API_VERSION` in `fetch_data.py` ggf. auf eine ältere/neuere Version.

**Action committet nichts** → Wenn sich keine Datei geändert hat, ist das normal. Prüfe die Action-Logs.

**Streamlit zeigt alte Daten** → Cache leeren: oben rechts auf das Menü → "Clear cache" → "Rerun".

---

Viel Erfolg mit dem Dashboard! 🚀
