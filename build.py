#!/usr/bin/env python3
"""
WC2026 Prediction Market — daily rebuild pipeline.
Downloads fresh results, replays ELO, prices markets with a Poisson goal model,
and regenerates docs/index.html. Runs daily via GitHub Actions.

All markets are priced from REAL data only:
  1X2, Double Chance, Draw No Bet, Over/Under goals, BTTS,
  Win to Nil, Half-Time Leader, Anytime Goalscorer.
Corners / fouls / cards / player shots are NOT priced — that data
only exists in paid Opta-level feeds and we refuse to fabricate it.
"""
import json, math, urllib.request
from datetime import date, datetime, timezone
import pandas as pd
import numpy as np

BASE = "https://raw.githubusercontent.com/martj42/international_results/master/"
HOSTS = {"Mexico", "United States", "Canada"}
HOME_ADV = 60
TODAY = date.today().isoformat()

# ---------------------------------------------------------------- data
def download():
    for f in ("results.csv", "goalscorers.csv"):
        urllib.request.urlretrieve(BASE + f, f)

def load():
    res = pd.read_csv("results.csv"); res["date"] = pd.to_datetime(res["date"])
    gs = pd.read_csv("goalscorers.csv"); gs["date"] = pd.to_datetime(gs["date"])
    return res, gs

def clean(res):
    res = res.drop_duplicates(subset=["date", "home_team", "away_team"])
    cut = res[res["date"] >= "1996-06-11"]
    comp = cut[cut.tournament.str.contains(
        "FIFA|Copa Am|UEFA|African Cup|AFC|CONCACAF|Gold Cup|OFC", case=False, na=False)]
    fifa = set(comp.home_team) | set(comp.away_team)
    cut = cut[cut.home_team.isin(fifa) & cut.away_team.isin(fifa)]
    train = cut[cut.home_score.notna()].sort_values("date")
    fixtures = cut[(cut.home_score.isna()) & (cut.tournament == "FIFA World Cup")
                   & (cut["date"] >= TODAY)].sort_values("date")
    return train, fixtures

# ---------------------------------------------------------------- elo
def kfactor(t):
    t = str(t)
    if t == "FIFA World Cup": return 60
    if "qualification" in t.lower() or t in ("Copa América", "UEFA Euro",
        "African Cup of Nations", "AFC Asian Cup", "CONCACAF Championship", "Gold Cup"):
        return 40
    if "Nations League" in t: return 30
    return 20

def run_elo(train):
    elo = {}
    g = lambda t: elo.setdefault(t, 1500.0)
    for r in train.itertuples():
        ra, rb = g(r.home_team), g(r.away_team)
        ha = 0 if r.neutral else 80
        ea = 1 / (1 + 10 ** (-(ra + ha - rb) / 400))
        sa = 1.0 if r.home_score > r.away_score else (0.0 if r.home_score < r.away_score else 0.5)
        gd = abs(r.home_score - r.away_score)
        mult = 1 if gd <= 1 else (1.5 if gd == 2 else 1.75 + (gd - 3) * 0.125)
        d = kfactor(r.tournament) * mult * (sa - ea)
        elo[r.home_team] = ra + d; elo[r.away_team] = rb - d
    return elo

# ---------------------------------------------------------------- form & players
def last20(train, gs, teams):
    form, players = {}, {}
    for t in teams:
        tm = train[(train.home_team == t) | (train.away_team == t)].tail(20)
        w = d = l = gf = ga = 0; fs = []
        for r in tm.itertuples():
            f, a = (r.home_score, r.away_score) if r.home_team == t else (r.away_score, r.home_score)
            gf += f; ga += a
            if f > a: w += 1; fs.append("W")
            elif f == a: d += 1; fs.append("D")
            else: l += 1; fs.append("L")
        form[t] = [w, d, l, int(gf), int(ga), "".join(fs[-10:])]
        tg = gs[(gs.team == t) & (gs.date.isin(set(tm.date))) & (gs.own_goal == False)]
        pl = []
        for name, grp in tg.groupby("scorer"):
            if pd.isna(name): continue
            pl.append([name, len(grp), int(grp.penalty.sum()), round(len(grp) / 20, 2)])
        players[t] = sorted(pl, key=lambda x: -x[1])[:6]
    return form, players

# ---------------------------------------------------------------- markets (Poisson)
def pois_grid(xa, xb, n=10):
    pa = [math.exp(-xa) * xa ** i / math.factorial(i) for i in range(n)]
    pb = [math.exp(-xb) * xb ** i / math.factorial(i) for i in range(n)]
    return [[pa[i] * pb[j] for j in range(n)] for i in range(n)]

def price_match(h, a, elo, form, players):
    ha = HOME_ADV if h in HOSTS else (-HOME_ADV if a in HOSTS else 0)
    p_raw = 1 / (1 + 10 ** (-(elo[h] + ha - elo[a]) / 400))
    att_h = form.get(h, [0,0,0,27,0,""])[3] / 20
    att_a = form.get(a, [0,0,0,27,0,""])[3] / 20
    total = min(max(0.6 * (att_h + att_a) + 0.4 * 2.72, 1.8), 4.2)
    share = 0.5 + (p_raw - 0.5) * 0.85
    xh, xa_ = total * share, total * (1 - share)
    G = pois_grid(xh, xa_)
    pH = sum(G[i][j] for i in range(10) for j in range(10) if i > j)
    pD = sum(G[i][i] for i in range(10))
    pA = 1 - pH - pD
    o15 = 1 - sum(G[i][j] for i in range(10) for j in range(10) if i + j <= 1)
    o25 = 1 - sum(G[i][j] for i in range(10) for j in range(10) if i + j <= 2)
    btts = 1 - sum(G[0][j] for j in range(10)) - sum(G[i][0] for i in range(10)) + G[0][0]
    wtn_h = sum(G[i][0] for i in range(1, 10))
    Ght = pois_grid(xh * 0.45, xa_ * 0.45)
    ht_h = sum(Ght[i][j] for i in range(10) for j in range(10) if i > j)
    # anytime scorers (top 3 per team) from real last-20 rates, scaled by xG context
    scorers = []
    for team, xg in ((h, xh), (a, xa_)):
        base = max(form.get(team, [0,0,0,27])[3] / 20, 0.5)
        for p in players.get(team, [])[:3]:
            rate = p[3] * (xg / base)
            scorers.append([p[0], team, round(min(1 - math.exp(-rate), 0.8) * 100)])
    scorers.sort(key=lambda x: -x[2])
    r = lambda x: round(x * 100)
    return {"pH": r(pH), "pD": r(pD), "pA": r(pA),
            "dc1X": r(pH + pD), "dcX2": r(pD + pA), "dc12": r(pH + pA),
            "dnbH": r(pH / (pH + pA)), "dnbA": r(pA / (pH + pA)),
            "o15": r(o15), "o25": r(o25), "u25": r(1 - o25),
            "btts": r(btts), "wtnH": r(wtn_h), "htH": r(ht_h),
            "xg": f"{xh:.1f}-{xa_:.1f}", "scorers": scorers[:4]}

# ---------------------------------------------------------------- build
def main():
    download()
    res, gs = load()
    train, fixtures = clean(res)
    elo = run_elo(train)
    teams = sorted(set(fixtures.home_team) | set(fixtures.away_team))
    form, players = last20(train, gs, teams)
    matches = []
    for r in fixtures.itertuples():
        m = price_match(r.home_team, r.away_team, elo, form, players)
        m.update({"d": str(r.date.date())[5:], "g": "", "h": r.home_team, "a": r.away_team,
                  "city": r.city, "eH": round(elo[r.home_team]), "eA": round(elo[r.away_team])})
        matches.append(m)
    payload = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "n_train": len(train), "M": matches, "F": form, "P": players}
    with open("docs/data.json", "w") as f:
        json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)
    tpl = open("template.html").read()
    open("docs/index.html", "w").write(
        tpl.replace("__DATA__", json.dumps(payload, separators=(",", ":"), ensure_ascii=False)))
    print(f"Built {len(matches)} markets from {len(train):,} training matches.")

if __name__ == "__main__":
    main()
