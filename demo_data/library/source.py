from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


SEED_RECORDS = [
    ("OL45804W", "Pride and Prejudice", "Jane Austen", 1813, "English", "Fiction"),
    ("OL27448W", "The Great Gatsby", "F. Scott Fitzgerald", 1925, "English", "Fiction"),
    ("OL468431W", "The Trial", "Franz Kafka", 1925, "German", "Philosophy"),
    ("OL243553W", "One Hundred Years of Solitude", "Gabriel García Márquez", 1967, "Spanish", "Fiction"),
    ("OL152715W", "War and Peace", "Leo Tolstoy", 1869, "Russian", "History"),
    ("OL165531W", "The Master and Margarita", "Mikhail Bulgakov", 1967, "Russian", "Philosophy"),
    ("OL262758W", "The Hobbit", "J. R. R. Tolkien", 1937, "English", "Children"),
    ("OL1968015W", "A Brief History of Time", "Stephen Hawking", 1988, "English", "Science"),
    ("OL93528W", "The Odyssey", "Homer", -700, "Greek", "Poetry"),
    ("OL102749W", "The Art of War", "Sun Tzu", -500, "Chinese", "Philosophy"),
    ("OL103043W", "The Name of the Rose", "Umberto Eco", 1980, "Italian", "History"),
    ("OL2214459W", "The Left Hand of Darkness", "Ursula K. Le Guin", 1969, "English", "Science"),
]


def builtin_records() -> list[dict[str, Any]]:
    return [
        {"key": f"/works/{key}", "title": title, "author": author, "year": year, "language": language, "subject": subject}
        for key, title, author, year, language, subject in SEED_RECORDS
    ]


def load_snapshot(path: str | Path) -> Iterable[dict[str, Any]]:
    """Load the JSON snapshot produced by ``demo_data.library.fetch``."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("docs"), list):
        raise ValueError("Open Library snapshot must be a JSON object with a 'docs' array")
    yield from payload["docs"]


def normalize_records(items: Iterable[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        key = item.get("key") or item.get("source_key")
        title = item.get("title")
        if not isinstance(key, str) or not isinstance(title, str) or not title.strip():
            continue
        authors = item.get("authors") or []
        author = item.get("author")
        author_names = item.get("author_name") or []
        if not author and authors and isinstance(authors[0], dict):
            author = authors[0].get("name") or authors[0].get("author", {}).get("key")
        if not author and author_names:
            author = author_names[0]
        if not isinstance(author, str) or not author:
            author = "Unknown Author"
        result.append({
            "key": key,
            "title": title.strip(),
            "author": author.rsplit("/", 1)[-1].replace("_", " "),
            "author_key": _first_key(item.get("author_key"), prefix="/authors/"),
            "year": _year(item.get("first_publish_year") or item.get("first_publish_date") or item.get("publish_date")),
            "number_of_pages_median": item.get("number_of_pages_median") if isinstance(item.get("number_of_pages_median"), int) else None,
            "language": _language(item),
            "subject": _subject(item),
            "description": _description(item),
            "publishers": [value.strip() for value in (item.get("publisher") or []) if isinstance(value, str) and value.strip()][:3],
            "isbn": [value for value in (item.get("isbn") or []) if isinstance(value, str)][:20],
            "cover_i": item.get("cover_i"),
        })
        if len(result) >= limit:
            break
    return result


def _first_key(value: Any, *, prefix: str) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, str) or not value:
        return None
    return value if value.startswith("/") else f"{prefix}{value}"


def _year(value: Any) -> int | None:
    if isinstance(value, int) and -3000 < value < 3000:
        return value
    if isinstance(value, str):
        for token in value.replace("/", " ").replace("-", " ").split():
            if token.lstrip("+").lstrip("-").isdigit() and 3 <= len(token.lstrip("+-")) <= 4:
                year = int(token)
                if -3000 < year < 3000:
                    return year
    return None


def _language(item: dict[str, Any]) -> str:
    languages = item.get("languages") or item.get("language") or []
    if isinstance(languages, str):
        languages = [languages]
    if languages and isinstance(languages[0], dict):
        return str(languages[0].get("key", "")).rsplit("/", 1)[-1] or "English"
    if languages and isinstance(languages[0], str):
        return {"eng": "English", "en": "English", "rus": "Russian", "ru": "Russian", "ger": "German", "de": "German", "spa": "Spanish", "es": "Spanish", "ita": "Italian", "it": "Italian", "jpn": "Japanese", "ja": "Japanese", "zho": "Chinese", "zh": "Chinese", "ell": "Greek", "el": "Greek", "pol": "Polish", "fre": "French", "fra": "French", "por": "Portuguese", "ukr": "Ukrainian", "nld": "Dutch", "swe": "Swedish", "dan": "Danish", "fin": "Finnish", "ara": "Arabic", "heb": "Hebrew", "hin": "Hindi", "tur": "Turkish"}.get(languages[0], languages[0])
    return str(item.get("language") or "English")


def _subject(item: dict[str, Any]) -> str:
    subjects = item.get("subjects") or item.get("subject") or []
    if isinstance(subjects, list) and subjects:
        return str(subjects[0])
    return "Fiction"


def _description(item: dict[str, Any]) -> str | None:
    value = item.get("description")
    if isinstance(value, dict):
        value = value.get("value")
    return value if isinstance(value, str) else None
