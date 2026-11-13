#!/usr/bin/env python3
"""Render a contribution ledger SVG (light + dark) from the GitHub GraphQL API.

Usage:
  GH_TOKEN=... python scripts/contrib_graph.py --user byananya --out assets
  python scripts/contrib_graph.py --fixture data.json --out assets   # offline
"""
import argparse
import datetime as dt
import json
import os
import urllib.request
from collections import defaultdict

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount weekday } }
      }
    }
  }
}
"""

THEMES = {
    "light": {
        "bg": "#FBF4EF", "border": "#EAD7CF", "ink": "#4A2C3D", "muted": "#9A8178",
        "gold": "#B08A55", "accent": "#8E2B4A", "rule": "#EAD7CF",
        "levels": ["#F0E2DC", "#F2C4CF", "#E28AA3", "#D4537E", "#8E2B4A"],
        "bar": "#D4537E", "bar_peak": "#8E2B4A", "track": "#F0E2DC",
    },
    "dark": {
        "bg": "#1A1216", "border": "#3A2A31", "ink": "#F5E6E0", "muted": "#A8918A",
        "gold": "#C9A97A", "accent": "#F08FAE", "rule": "#33252B",
        "levels": ["#2A1F24", "#5A2A3C", "#8E3A5A", "#D4537E", "#F08FAE"],
        "bar": "#D4537E", "bar_peak": "#F08FAE", "track": "#2A1F24",
    },
}

SERIF = "Fraunces, 'EB Garamond', Georgia, 'Times New Roman', serif"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def fetch(user, token):
    body = json.dumps({"query": QUERY, "variables": {"login": user}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "contrib-ledger"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def level_fn(counts):
    nz = sorted(c for c in counts if c > 0)
    if not nz:
        return lambda c: 0
    q = [nz[int(len(nz) * p)] if int(len(nz) * p) < len(nz) else nz[-1] for p in (0.25, 0.5, 0.75)]

    def lvl(c):
        if c == 0:
            return 0
        if c <= q[0]:
            return 1
        if c <= q[1]:
            return 2
        if c <= q[2]:
            return 3
        return 4
    return lvl


def stats(days):
    counts = [d["contributionCount"] for d in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    current = 0
    tail = counts[:]
    if tail and tail[-1] == 0:  # today not yet active: streak continues from yesterday
        tail = tail[:-1]
    for c in reversed(tail):
        if c == 0:
            break
        current += 1
    peak = max(days, key=lambda d: d["contributionCount"])
    active = sum(1 for c in counts if c > 0)
    return {
        "total": sum(counts), "current": current, "longest": longest,
        "peak": peak, "active_pct": round(100 * active / max(1, len(counts))),
    }


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(cal, theme_name):
    t = THEMES[theme_name]
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    lvl = level_fn([d["contributionCount"] for d in days])
    s = stats(days)

    W = 920
    pad = 32
    cell, gap = 13, 3
    step = cell + gap
    grid_x = pad + 30
    grid_y = 190
    grid_w = len(weeks) * step - gap
    W = max(W, grid_x + grid_w + pad)
    out = []
    a = out.append

    start = dt.date.fromisoformat(days[0]["date"])
    end = dt.date.fromisoformat(days[-1]["date"])

    # --- header
    a(f'<text x="{pad}" y="52" font-family="{SERIF}" font-size="26" fill="{t["ink"]}" '
      f'font-weight="600" letter-spacing="0.2">Contribution Ledger</text>')
    rng = f'{start.strftime("%b %Y").upper()} — {end.strftime("%b %Y").upper()}'
    a(f'<text x="{W - pad}" y="52" text-anchor="end" font-family="{SANS}" font-size="11" '
      f'fill="{t["gold"]}" letter-spacing="2.4" font-weight="600">{rng}</text>')
    a(f'<line x1="{pad}" y1="70" x2="{W - pad}" y2="70" stroke="{t["rule"]}" stroke-width="1"/>')

    # --- stats row
    peak_date = dt.date.fromisoformat(s["peak"]["date"])
    items = [
        (f'{s["total"]:,}', "CONTRIBUTIONS"),
        (f'{s["current"]}d', "CURRENT STREAK"),
        (f'{s["longest"]}d', "LONGEST STREAK"),
        (f'{s["peak"]["contributionCount"]}', f'PEAK · {peak_date.strftime("%b %-d").upper()}'),
        (f'{s["active_pct"]}%', "DAYS ACTIVE"),
    ]
    col_w = (W - 2 * pad) / len(items)
    for i, (num, label) in enumerate(items):
        x = pad + i * col_w
        a(f'<g class="fade" style="animation-delay:{i * 80}ms">')
        a(f'<text x="{x:.1f}" y="118" font-family="{SERIF}" font-size="34" fill="{t["accent"]}" '
          f'font-weight="600">{esc(num)}</text>')
        a(f'<text x="{x:.1f}" y="140" font-family="{SANS}" font-size="10" fill="{t["muted"]}" '
          f'letter-spacing="1.8" font-weight="600">{esc(label)}</text>')
        a('</g>')
        if i:
            a(f'<line x1="{x - 14:.1f}" y1="92" x2="{x - 14:.1f}" y2="140" stroke="{t["rule"]}"/>')

    # --- month labels
    last_month = None
    for wi, w in enumerate(weeks):
        d0 = dt.date.fromisoformat(w["contributionDays"][0]["date"])
        if d0.month != last_month and (wi == 0 or d0.day <= 7):
            if wi < len(weeks) - 2:
                a(f'<text x="{grid_x + wi * step}" y="{grid_y - 10}" font-family="{SANS}" '
                  f'font-size="10" fill="{t["muted"]}">{MONTHS[d0.month - 1]}</text>')
            last_month = d0.month

    for wd in (1, 3, 5):
        a(f'<text x="{grid_x - 8}" y="{grid_y + wd * step + cell - 2}" text-anchor="end" '
          f'font-family="{SANS}" font-size="9.5" fill="{t["muted"]}">{WEEKDAYS[wd]}</text>')

    # --- heatmap
    for wi, w in enumerate(weeks):
        delay = wi * 14
        for d in w["contributionDays"]:
            x = grid_x + wi * step
            y = grid_y + d["weekday"] * step
            fill = t["levels"][lvl(d["contributionCount"])]
            extra = ""
            if d["date"] == s["peak"]["date"]:
                extra = f' stroke="{t["gold"]}" stroke-width="1.6"'
            a(f'<rect class="c" style="animation-delay:{delay}ms" x="{x}" y="{y}" width="{cell}" '
              f'height="{cell}" rx="3" fill="{fill}"{extra}/>')

    # legend
    ly = grid_y + 7 * step + 12
    lx = grid_x + grid_w - 5 * step - 34
    a(f'<text x="{lx - 8}" y="{ly + 10}" text-anchor="end" font-family="{SANS}" font-size="10" '
      f'fill="{t["muted"]}">Less</text>')
    for i, c in enumerate(t["levels"]):
        a(f'<rect x="{lx + i * step}" y="{ly}" width="{cell}" height="{cell}" rx="3" fill="{c}"/>')
    a(f'<text x="{lx + 5 * step + 4}" y="{ly + 10}" font-family="{SANS}" font-size="10" '
      f'fill="{t["muted"]}">More</text>')
    a(f'<text x="{grid_x}" y="{ly + 10}" font-family="{SANS}" font-size="10" fill="{t["muted"]}">'
      f'<tspan fill="{t["gold"]}">◆</tspan> gold outline marks the peak day</text>')

    # --- lower panels
    py = ly + 52
    a(f'<line x1="{pad}" y1="{py - 20}" x2="{W - pad}" y2="{py - 20}" stroke="{t["rule"]}"/>')

    # monthly totals (last 12 calendar months in range)
    monthly = defaultdict(int)
    for d in days:
        k = d["date"][:7]
        monthly[k] += d["contributionCount"]
    keys = sorted(monthly)[-12:]
    mx = max([monthly[k] for k in keys] + [1])
    panel_w = (W - 2 * pad) * 0.58
    a(f'<text x="{pad}" y="{py}" font-family="{SANS}" font-size="10" fill="{t["gold"]}" '
      f'letter-spacing="2" font-weight="600">BY MONTH</text>')
    bh = 90
    base = py + 18 + bh
    bw = panel_w / len(keys)
    peak_k = max(keys, key=lambda k: monthly[k])
    for i, k in enumerate(keys):
        v = monthly[k]
        h = max(2, bh * v / mx)
        x = pad + i * bw + 4
        col = t["bar_peak"] if k == peak_k else t["bar"]
        a(f'<rect x="{x:.1f}" y="{base - bh}" width="{bw - 8:.1f}" height="{bh}" rx="3" fill="{t["track"]}"/>')
        a(f'<rect class="b" style="animation-delay:{300 + i * 50}ms" x="{x:.1f}" y="{base - h:.1f}" '
          f'width="{bw - 8:.1f}" height="{h:.1f}" rx="3" fill="{col}"/>')
        a(f'<text x="{x + (bw - 8) / 2:.1f}" y="{base + 14}" text-anchor="middle" font-family="{SANS}" '
          f'font-size="9.5" fill="{t["muted"]}">{MONTHS[int(k[5:]) - 1]}</text>')
        if v:
            a(f'<text x="{x + (bw - 8) / 2:.1f}" y="{base - h - 5:.1f}" text-anchor="middle" '
              f'font-family="{SANS}" font-size="9" fill="{t["ink"]}" class="fade" '
              f'style="animation-delay:{600 + i * 50}ms">{v}</text>')

    # weekday rhythm
    wx = pad + panel_w + 40
    ww = W - pad - wx
    a(f'<text x="{wx}" y="{py}" font-family="{SANS}" font-size="10" fill="{t["gold"]}" '
      f'letter-spacing="2" font-weight="600">WEEKLY RHYTHM</text>')
    byday = [0] * 7
    for d in days:
        byday[d["weekday"]] += d["contributionCount"]
    tot = sum(byday) or 1
    order = [1, 2, 3, 4, 5, 6, 0]
    rh = 13.5
    best = max(range(7), key=lambda i: byday[i])
    for r, wd in enumerate(order):
        y = py + 16 + r * rh
        frac = byday[wd] / max(byday + [1])
        a(f'<text x="{wx}" y="{y + 9}" font-family="{SANS}" font-size="9.5" fill="{t["muted"]}">'
          f'{WEEKDAYS[wd]}</text>')
        bx = wx + 32
        bwid = ww - 32 - 36
        a(f'<rect x="{bx}" y="{y + 1}" width="{bwid:.1f}" height="9" rx="4.5" fill="{t["track"]}"/>')
        col = t["bar_peak"] if wd == best else t["bar"]
        a(f'<rect class="h" style="animation-delay:{400 + r * 60}ms" x="{bx}" y="{y + 1}" '
          f'width="{max(4, bwid * frac):.1f}" height="9" rx="4.5" fill="{col}"/>')
        a(f'<text x="{W - pad}" y="{y + 9}" text-anchor="end" font-family="{SANS}" font-size="9.5" '
          f'fill="{t["ink"]}">{round(100 * byday[wd] / tot)}%</text>')

    H = base + 40
    css = (
        "@keyframes in{from{opacity:0}to{opacity:1}}"
        "@keyframes up{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
        "@keyframes right{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
        ".c,.fade{opacity:0;animation:in .5s ease-out forwards}"
        ".b{transform-box:fill-box;transform-origin:bottom;transform:scaleY(0);"
        "animation:up .7s cubic-bezier(.2,.8,.2,1) forwards}"
        ".h{transform-box:fill-box;transform-origin:left;transform:scaleX(0);"
        "animation:right .7s cubic-bezier(.2,.8,.2,1) forwards}"
        "@media (prefers-reduced-motion:reduce){.c,.fade,.b,.h{animation:none;opacity:1;transform:none}}"
    )
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="Contribution ledger: {s["total"]} contributions in the last year">'
        f'<style>{css}</style>'
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="16" fill="{t["bg"]}" '
        f'stroke="{t["border"]}"/>'
    )
    return head + "".join(out) + "</svg>\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=os.environ.get("GH_USER", "byananya"))
    ap.add_argument("--fixture")
    ap.add_argument("--out", default="assets")
    args = ap.parse_args()

    if args.fixture:
        with open(args.fixture) as f:
            cal = json.load(f)
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("Set GH_TOKEN")
        cal = fetch(args.user, token)

    os.makedirs(args.out, exist_ok=True)
    for name in THEMES:
        path = os.path.join(args.out, f"contrib-ledger-{name}.svg")
        with open(path, "w") as f:
            f.write(render(cal, name))
        print("wrote", path)


if __name__ == "__main__":
    main()
