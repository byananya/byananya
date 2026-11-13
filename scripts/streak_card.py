#!/usr/bin/env python3
"""Render an all-time streak card SVG (light + dark).

Usage:
  GH_TOKEN=... python scripts/streak_card.py --user byananya --out assets
  python scripts/streak_card.py --fixture days.json --out assets   # [{date, contributionCount}]
"""
import argparse
import datetime as dt
import json
import math
import os
import urllib.request


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

YEAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""


def gql(query, variables, token):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "streak-card"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    return data["data"]


def fetch_all(user, token):
    created = gql('query($login:String!){user(login:$login){createdAt}}', {"login": user}, token)
    start = dt.datetime.fromisoformat(created["user"]["createdAt"].replace("Z", "+00:00")).date()
    today = dt.date.today()
    days = {}
    for year in range(start.year, today.year + 1):
        frm = max(start, dt.date(year, 1, 1))
        to = min(today, dt.date(year, 12, 31))
        data = gql(YEAR_QUERY, {"login": user, "from": f"{frm}T00:00:00Z", "to": f"{to}T23:59:59Z"}, token)
        cal = data["user"]["contributionsCollection"]["contributionCalendar"]
        for w in cal["weeks"]:
            for d in w["contributionDays"]:
                if frm.isoformat() <= d["date"] <= to.isoformat():
                    days[d["date"]] = d["contributionCount"]
    return [{"date": k, "contributionCount": v} for k, v in sorted(days.items())]


def streaks(days):
    counts = [(dt.date.fromisoformat(d["date"]), d["contributionCount"]) for d in days]
    best = (0, None, None)
    run, run_start = 0, None
    for date, c in counts:
        if c > 0:
            run_start = date if run == 0 else run_start
            run += 1
            if run > best[0]:
                best = (run, run_start, date)
        else:
            run = 0
    # current streak: today may still be empty without breaking it
    tail = counts[:-1] if counts and counts[-1][1] == 0 else counts
    cur, cur_end = 0, None
    for date, c in reversed(tail):
        if c == 0:
            break
        cur_end = cur_end or date
        cur += 1
    cur_start = cur_end - dt.timedelta(days=cur - 1) if cur else None
    last_active = next((date for date, c in reversed(counts) if c > 0), None)
    return {"longest": best, "current": (cur, cur_start, cur_end), "last_active": last_active}


def fmt(d, year=True):
    return d.strftime("%b %-d, %Y") if year else d.strftime("%b %-d")


def span(a, b):
    if not a:
        return "—"
    return f"{fmt(a, a.year != b.year)} — {fmt(b)}"


def render(days, theme_name):
    t = THEMES[theme_name]
    st = streaks(days)
    total = sum(d["contributionCount"] for d in days)
    active = sum(1 for d in days if d["contributionCount"] > 0)
    first = dt.date.fromisoformat(days[0]["date"])

    yearly = {}
    for d in days:
        y = int(d["date"][:4])
        yearly[y] = yearly.get(y, 0) + d["contributionCount"]

    W, pad = 920, 32
    col = (W - 2 * pad) / 3
    cx = [pad + col * i + col / 2 for i in range(3)]
    out = []
    a = out.append

    def label(x, y, text, color, anchor="middle", size=10, spacing=2):
        a(f'<text x="{x:.1f}" y="{y}" text-anchor="{anchor}" font-family="{SANS}" font-size="{size}" '
          f'fill="{color}" letter-spacing="{spacing}" font-weight="600">{text}</text>')

    def sub(x, y, text):
        a(f'<text x="{x:.1f}" y="{y}" text-anchor="middle" font-family="{SANS}" font-size="12" '
          f'fill="{t["muted"]}">{text}</text>')

    def big(x, y, text, color, size=46, cls="fade", delay=0):
        a(f'<text class="{cls}" style="animation-delay:{delay}ms" x="{x:.1f}" y="{y}" text-anchor="middle" '
          f'font-family="{SERIF}" font-size="{size}" font-weight="600" fill="{color}">{text}</text>')

    # dividers
    for i in (1, 2):
        x = pad + col * i
        a(f'<line x1="{x:.1f}" y1="40" x2="{x:.1f}" y2="196" stroke="{t["rule"]}"/>')

    # left: all-time total
    label(cx[0], 58, "ALL-TIME", t["gold"])
    big(cx[0], 122, f"{total:,}", t["ink"])
    sub(cx[0], 150, f"{fmt(first)} — Present")
    sub(cx[0], 172, f"{active:,} active days")

    # center: current streak ring
    cur, cs, ce = st["current"]
    longest = st["longest"][0] or 1
    frac = min(1.0, cur / longest)
    r, ry = 52, 112
    circ = 2 * math.pi * r
    is_record = cur > 0 and cur >= st["longest"][0]
    ring_col = t["gold"] if is_record else t["accent"]
    a(f'<circle cx="{cx[1]:.1f}" cy="{ry}" r="{r}" fill="none" stroke="{t["track"]}" stroke-width="8"/>')
    if frac > 0:
        a(f'<circle class="ring" cx="{cx[1]:.1f}" cy="{ry}" r="{r}" fill="none" stroke="{ring_col}" '
          f'stroke-width="8" stroke-linecap="round" stroke-dasharray="{circ * frac:.1f} {circ:.1f}" '
          f'style="--len:{circ * frac:.1f}" transform="rotate(-90 {cx[1]:.1f} {ry})"/>')
    # alpona diamond at the crown of the ring
    dx, dy = cx[1], ry - r
    a(f'<path d="M{dx:.1f} {dy - 9} L{dx + 7:.1f} {dy} L{dx:.1f} {dy + 9} L{dx - 7:.1f} {dy} Z" '
      f'fill="{t["gold"]}" stroke="{t["bg"]}" stroke-width="3"/>')
    big(cx[1], ry + 15, str(cur), t["ink"], size=42, delay=200)
    label(cx[1], ry + r + 26, "CURRENT STREAK", t["accent"])
    if cur:
        note = span(cs, ce) + (" · record" if is_record else f" · {round(frac * 100)}% of record")
    else:
        note = f"Last active {fmt(st['last_active'], False)}" if st["last_active"] else "No activity yet"
    sub(cx[1], ry + r + 46, note)

    # right: longest streak
    ln, ls, le = st["longest"]
    label(cx[2], 58, "LONGEST STREAK", t["gold"])
    big(cx[2], 122, f"{ln}<tspan font-size='22' fill='{t['muted']}'> days</tspan>", t["ink"], delay=100)
    sub(cx[2], 150, span(ls, le))
    best_year = max(yearly, key=yearly.get)
    sub(cx[2], 172, f"Best year {best_year} · {yearly[best_year]:,}")

    # bottom: yearly strip
    sy = 222
    a(f'<line x1="{pad}" y1="{sy}" x2="{W - pad}" y2="{sy}" stroke="{t["rule"]}"/>')
    label(pad, sy + 26, "BY YEAR", t["gold"], anchor="start")
    years = sorted(yearly)
    mx = max(yearly.values()) or 1
    sx = pad + 90
    slot = (W - pad - sx) / len(years)
    bh = 34
    base = sy + 58
    for i, y in enumerate(years):
        v = yearly[y]
        h = max(2, bh * v / mx)
        x = sx + i * slot
        bw = min(56, slot - 18)
        c = t["bar_peak"] if y == best_year else t["bar"]
        a(f'<rect x="{x:.1f}" y="{base - bh}" width="{bw:.1f}" height="{bh}" rx="3" fill="{t["track"]}"/>')
        a(f'<rect class="b" style="animation-delay:{400 + i * 70}ms" x="{x:.1f}" y="{base - h:.1f}" '
          f'width="{bw:.1f}" height="{h:.1f}" rx="3" fill="{c}"/>')
        a(f'<text x="{x + bw + 8:.1f}" y="{base - 16}" font-family="{SANS}" font-size="11" '
          f'font-weight="600" fill="{t["ink"]}">{v:,}</text>')
        a(f'<text x="{x + bw + 8:.1f}" y="{base - 2}" font-family="{SANS}" font-size="10" '
          f'fill="{t["muted"]}">{y}</text>')

    H = base + 26
    css = (
        "@keyframes in{from{opacity:0}to{opacity:1}}"
        "@keyframes up{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
        "@keyframes draw{from{stroke-dashoffset:var(--len)}to{stroke-dashoffset:0}}"
        ".fade{opacity:0;animation:in .6s ease-out forwards}"
        ".ring{stroke-dashoffset:var(--len);animation:draw 1.2s cubic-bezier(.2,.8,.2,1) .2s forwards}"
        ".b{transform-box:fill-box;transform-origin:bottom;transform:scaleY(0);"
        "animation:up .7s cubic-bezier(.2,.8,.2,1) forwards}"
        "@media (prefers-reduced-motion:reduce){.fade,.ring,.b{animation:none;opacity:1;"
        "transform:none;stroke-dashoffset:0}}"
    )
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="{total} all-time contributions; current streak {cur} days; '
        f'longest streak {ln} days"><style>{css}</style>'
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
            days = json.load(f)
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("Set GH_TOKEN")
        days = fetch_all(args.user, token)
    os.makedirs(args.out, exist_ok=True)
    for name in THEMES:
        path = os.path.join(args.out, f"streak-card-{name}.svg")
        with open(path, "w") as f:
            f.write(render(days, name))
        print("wrote", path)


if __name__ == "__main__":
    main()
