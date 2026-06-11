# WC2026 Prediction Market — auto-updating

A self-rebuilding FIFA World Cup 2026 prediction site. Every morning it downloads
the latest real match results, retrains a scratch-built ELO model (validated at
76.4% accuracy on 18,618 decisive matches), prices every remaining fixture with a
Poisson goal model, and republishes the site — automatically, for free.

**Markets priced (all from real data):** 1X2 · Double Chance · Draw No Bet ·
Over/Under 1.5 & 2.5 · BTTS · Win to Nil · Half-Time Leader · Anytime Goalscorer
(from each player's real scoring rate over their team's last 20 internationals).

Corners, fouls, cards and player shots are **deliberately not priced** — that data
only exists in paid Opta-level feeds, and this project does not fabricate numbers.

## Setup (one time, ~10 minutes)

1. Create a free account at github.com
2. Click **New repository** → name it anything (e.g. `wc2026-market`) → set it to **Public** → Create
3. Click **uploading an existing file** and drag in ALL the files from this folder
   (including the hidden `.github` folder — if drag-drop misses it, use
   **Add file → Create new file**, type `.github/workflows/daily.yml` as the name,
   and paste the contents of that file)
4. Go to **Settings → Pages** → under "Branch" choose `main` and folder `/docs` → Save
5. Go to the **Actions** tab → enable workflows if prompted → open **Daily rebuild** →
   click **Run workflow** once to do the first build

Your site will be live at: `https://YOUR-USERNAME.github.io/wc2026-market/`
within a couple of minutes, and will rebuild itself every day at 05:00 UTC.

## How the daily update works

- Group-stage results are recorded in the upstream dataset as matches finish
- Knockout fixtures appear automatically once they're scheduled — the model
  picks them up and prices them with zero changes needed
- Each rebuild replays all ~27,000 matches so every result shifts the ratings

## Files

| File | Purpose |
|---|---|
| `build.py` | The whole pipeline: download → clean → ELO → Poisson pricing → site |
| `template.html` | Site template (data is injected at build time) |
| `.github/workflows/daily.yml` | The daily automation |
| `docs/index.html` | The generated site (rebuilt daily) |
| `docs/data.json` | The generated model output, if you want raw numbers |

Model probabilities are fair odds with no bookmaker margin. For analysis and
entertainment — real bookmaker prices will differ.
