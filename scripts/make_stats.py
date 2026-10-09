"""Generate the GitHub stats cards (assets/stats-dark.svg, assets/stats-light.svg).

Counts every repository the token can see, private ones included, but only totals are written
to the card: no repository names. Languages are measured in bytes of code with Jupyter
notebooks left out (their stored outputs would otherwise swamp everything else).

    STATS_TOKEN=... python scripts/make_stats.py      # in CI (fine-grained, read-only token)
    python scripts/make_stats.py                      # locally, falls back to `gh auth token`
"""
import collections
import datetime as dt
import json
import os
import subprocess
import urllib.request
from pathlib import Path

LOGIN = "sazio"
W, H = 1200, 285
THEMES = {
    "dark": dict(paper="#0d0e12", off="#9d86ff", on="#4cc38a", ink="#ecebe6", ink2="#b4b5bb", ink3="#7c7f88", line="#282a31"),
    "light": dict(paper="#f3f2ee", off="#5b3fd1", on="#1d8a59", ink="#16171b", ink2="#4a4d55", ink3="#7f828a", line="#dedcd5"),
}
SERIF = "Georgia, 'Times New Roman', serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


def token():
    t = os.environ.get("STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def graphql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if out.get("errors"):
        raise SystemExit(f"GraphQL error: {out['errors']}")
    return out["data"]


def fetch():
    repos, cursor = [], None
    while True:
        d = graphql("""query($login: String!, $cursor: String) { user(login: $login) {
            repositories(ownerAffiliations: OWNER, isFork: false, first: 100, after: $cursor) {
              pageInfo { hasNextPage endCursor }
              nodes { isPrivate stargazerCount languages(first: 20) { edges { size node { name } } } } } } }""",
                    login=LOGIN, cursor=cursor)["user"]["repositories"]
        repos += d["nodes"]
        if not d["pageInfo"]["hasNextPage"]:
            break
        cursor = d["pageInfo"]["endCursor"]

    u = graphql("""query($login: String!) { user(login: $login) {
        pullRequests { totalCount } issues { totalCount }
        repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) { totalCount }
        contributionsCollection { contributionYears contributionCalendar { totalContributions
          weeks { contributionDays { contributionCount } } } } } }""", login=LOGIN)["user"]

    per_year = {}
    for y in u["contributionsCollection"]["contributionYears"]:
        c = graphql("""query($login: String!, $from: DateTime!, $to: DateTime!) { user(login: $login) {
            contributionsCollection(from: $from, to: $to) { contributionCalendar { totalContributions } } } }""",
                    login=LOGIN, **{"from": f"{y}-01-01T00:00:00Z", "to": f"{y}-12-31T23:59:59Z"})
        per_year[y] = c["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]

    weeks = [sum(d["contributionCount"] for d in w["contributionDays"])
             for w in u["contributionsCollection"]["contributionCalendar"]["weeks"]]
    langs, notebooks = collections.Counter(), 0
    for r in repos:
        for e in r["languages"]["edges"]:
            if e["node"]["name"] == "Jupyter Notebook":
                notebooks += 1
            else:
                langs[e["node"]["name"]] += e["size"]
    this_year = dt.date.today().year
    return dict(
        repos=len(repos), private=sum(r["isPrivate"] for r in repos), stars=sum(r["stargazerCount"] for r in repos),
        prs=u["pullRequests"]["totalCount"], issues=u["issues"]["totalCount"],
        contributed=u["repositoriesContributedTo"]["totalCount"],
        total=sum(per_year.values()), this_year=per_year.get(this_year, 0), year=this_year,
        since=min(per_year) if per_year else this_year,
        last12=u["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        weeks=weeks, langs=langs, notebooks=notebooks,
    )


def fmt(n):
    return f"{n / 1000:.1f}k" if n >= 10000 else f"{n:,}"


def render(theme, s):
    T = THEMES[theme]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
         f'aria-label="GitHub activity: {s["total"]} contributions since {s["since"]}, {s["repos"]} repositories.">',
         f'<rect width="{W}" height="{H}" rx="14" fill="{T["paper"]}"/>']

    def label(x, y, text):
        o.append(f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="11" letter-spacing="1.6" fill="{T["ink3"]}">{text}</text>')

    # left: headline number and a grid of totals
    label(48, 52, "GITHUB · ALL REPOSITORIES, PRIVATE INCLUDED")
    o.append(f'<text x="46" y="108" font-family="{SERIF}" font-size="50" letter-spacing="-1" fill="{T["ink"]}">{fmt(s["total"])}</text>')
    o.append(f'<text x="48" y="132" font-family="{SERIF}" font-style="italic" font-size="17" fill="{T["ink2"]}">'
             f'contributions since {s["since"]}</text>')
    grid = [(fmt(s["this_year"]), f"in {s['year']}"), (fmt(s["repos"]), "repositories"), (fmt(s["stars"]), "stars"),
            (fmt(s["prs"]), "pull requests"), (fmt(s["issues"]), "issues"), (fmt(s["contributed"]), "contributed to")]
    for i, (val, name) in enumerate(grid):
        x, y = 300 + (i % 3) * 112, 78 + (i // 3) * 52
        o.append(f'<text x="{x}" y="{y}" font-family="{SERIF}" font-size="24" fill="{T["ink"]}">{val}</text>')
        o.append(f'<text x="{x}" y="{y + 17}" font-family="{MONO}" font-size="10.5" fill="{T["ink3"]}">{name}</text>')

    # right: language bar and legend
    lx, lw = 700, 452
    label(lx, 52, "LANGUAGES · BYTES OF CODE")
    total = sum(s["langs"].values()) or 1
    top = s["langs"].most_common(6)
    shares = [(n, v / total) for n, v in top]
    rest = 1 - sum(p for _, p in shares)
    if rest > 0.001:
        shares.append(("Other", rest))
    colours = [(T["off"], 1), (T["on"], 1), (T["off"], 0.55), (T["on"], 0.55), (T["ink2"], 0.8), (T["ink3"], 0.7), (T["ink3"], 0.35)]
    x = lx
    for (name, p), (c, a) in zip(shares, colours):
        w = max(p * lw, 2)
        o.append(f'<rect x="{x:.1f}" y="70" width="{w:.1f}" height="10" fill="{c}" fill-opacity="{a}"/>')
        x += w
    for i, ((name, p), (c, a)) in enumerate(zip(shares, colours)):
        cx, cy = lx + (i % 2) * 230, 108 + (i // 2) * 22
        o.append(f'<circle cx="{cx + 5}" cy="{cy - 4}" r="4.5" fill="{c}" fill-opacity="{a}"/>')
        o.append(f'<text x="{cx + 16}" y="{cy}" font-family="{MONO}" font-size="12" fill="{T["ink2"]}">{name}'
                 f'<tspan fill="{T["ink3"]}"> {100 * p:.1f}%</tspan></text>')
    o.append(f'<text x="{lx}" y="{108 + 4 * 22 - 4}" font-family="{SERIF}" font-style="italic" font-size="13" fill="{T["ink3"]}">'
             f'Jupyter notebooks in {s["notebooks"]} repositories, left out of the bar.</text>')

    # bottom: weekly contributions as a peri-stimulus time histogram
    base, hmax = H - 22, 46
    label(48, base - hmax - 14, f"CONTRIBUTIONS PER WEEK · LAST 12 MONTHS ({fmt(s['last12'])})")
    o.append(f'<line x1="48" x2="{W - 48}" y1="{base}" y2="{base}" stroke="{T["line"]}"/>')
    weeks, peak = s["weeks"], max(s["weeks"] or [1]) or 1
    bw = (W - 96) / max(len(weeks), 1)
    for i, n in enumerate(weeks):
        if n:
            h = max(1.5, hmax * n / peak)
            o.append(f'<rect x="{48 + i * bw + 1:.1f}" y="{base - h:.1f}" width="{bw - 2:.1f}" height="{h:.1f}" fill="{T["off"]}" fill-opacity="0.85"/>')
    o.append("</svg>")
    return "\n".join(o)


def main():
    global TOKEN
    TOKEN = token()
    s = fetch()
    if s["private"] == 0:
        print("warning: no private repositories visible; the token can only see public data")
    out_dir = Path(__file__).resolve().parent.parent / "assets"
    for theme in THEMES:
        (out_dir / f"stats-{theme}.svg").write_text(render(theme, s))
    print(f"{s['total']} contributions since {s['since']} ({s['this_year']} in {s['year']}), "
          f"{s['repos']} repos ({s['private']} private), {s['stars']} stars, {s['prs']} PRs, {s['issues']} issues, "
          f"contributed to {s['contributed']}; top languages: {[n for n, _ in s['langs'].most_common(4)]}")


if __name__ == "__main__":
    main()
