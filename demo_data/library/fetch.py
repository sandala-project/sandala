from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FIELDS = ",".join([
    "key", "title", "author_name", "author_key", "first_publish_year",
    "subject", "publisher", "isbn", "language", "cover_i",
    "number_of_pages_median",
])


def fetch(output: Path, *, count: int = 1200, query: str = "language:eng", page_size: int = 500) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    documents: list[dict] = []
    offset = 0
    while len(documents) < count:
        limit = min(page_size, count - len(documents))
        params = {"q": query, "sort": "rating desc", "fields": FIELDS, "limit": limit, "offset": offset}
        request = Request(
            "https://openlibrary.org/search.json?" + urlencode(params),
            headers={"User-Agent": "Sandala-demo-seed/0.1 (nakendlom@gmail.com)"},
        )
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
        page = payload.get("docs", [])
        if not page:
            break
        documents.extend(page)
        offset += len(page)
        if len(page) < limit:
            break
        time.sleep(1)
    output.write_text(json.dumps({"docs": documents[:count]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[openlibrary] saved {min(len(documents), count)} records to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a bounded Open Library search snapshot")
    parser.add_argument("--output", type=Path, default=Path("demo_data/library/data/openlibrary_search.json"))
    parser.add_argument("--count", type=int, default=1200)
    parser.add_argument("--query", default="language:eng")
    args = parser.parse_args()
    fetch(args.output, count=args.count, query=args.query)


if __name__ == "__main__":
    main()
