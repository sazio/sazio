"""Copy the latest news items from the website into README.md.

Reads the `news` array in https://sazio.github.io/assets/home/data.js and rewrites the block
between <!-- NEWS:START --> and <!-- NEWS:END -->. Run by .github/workflows/sync-news.yml.

    python scripts/update_news.py [path-or-url-to-data.js]
"""
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

SOURCE = "https://sazio.github.io/assets/home/data.js"
README = Path(__file__).resolve().parent.parent / "README.md"
N_ITEMS = 5
START, END = "<!-- NEWS:START -->", "<!-- NEWS:END -->"

ENTRY = re.compile(
    r'\{\s*date:\s*"(?P<date>\d{4}-\d{2}-\d{2})",\s*text:\s*"(?P<text>(?:[^"\\]|\\.)*)"'
    r'(?:,\s*url:\s*"(?P<url>[^"]*)")?\s*\}'
)


def load(src):
    if src.startswith("http"):
        with urllib.request.urlopen(src, timeout=30) as r:
            return r.read().decode("utf-8")
    return Path(src).read_text()


def news_items(js):
    block = re.search(r"\bnews:\s*\[(.*?)\n\s*\],", js, re.S)
    if not block:
        sys.exit("news array not found in data.js")
    items = [m.groupdict() for m in ENTRY.finditer(block.group(1))]
    if not items:
        sys.exit("no news entries parsed; has the data.js format changed?")
    return sorted(items, key=lambda i: i["date"], reverse=True)[:N_ITEMS]


def to_markdown(items):
    lines = []
    for i in items:
        when = date.fromisoformat(i["date"]).strftime("%b %Y")
        text = i["text"].replace('\\"', '"')
        lines.append(f"- **{when}** · " + (f"[{text}]({i['url']})" if i.get("url") else text))
    return "\n".join(lines)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else SOURCE
    readme = README.read_text()
    if START not in readme or END not in readme:
        sys.exit("README is missing the NEWS markers")
    head, rest = readme.split(START, 1)
    _, tail = rest.split(END, 1)
    updated = f"{head}{START}\n{to_markdown(news_items(load(src)))}\n{END}{tail}"
    if updated != readme:
        README.write_text(updated)
        print("README news updated")
    else:
        print("README news already up to date")


if __name__ == "__main__":
    main()
