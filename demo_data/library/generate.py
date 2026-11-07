from __future__ import annotations

from collections import defaultdict
from random import Random
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sandala.core.time_utils import utc_now_iso

from .source import builtin_records


LANGUAGES = {
    "English": ("en", "English"),
    "Russian": ("ru", "Русский"),
    "German": ("de", "Deutsch"),
    "Spanish": ("es", "Español"),
    "Italian": ("it", "Italiano"),
    "Greek": ("el", "Ελληνικά"),
    "Chinese": ("zh", "中文"),
}

PUBLISHERS = [
    "Penguin Books", "Random House", "Oxford University Press", "Vintage Books",
    "HarperCollins", "Издательство АСТ", "Эксмо", "Gallimard",
]


def node_id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"sandala-demo-library:{kind}:{key}"))


def generate_dataset(*, book_count: int = 1200, seed: int = 20260712, records: list[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    if book_count < 1:
        raise ValueError("book_count must be positive")

    rng = Random(seed)
    source = records or builtin_records()
    now = utc_now_iso()
    folders: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    indexes: dict[str, dict[str, str]] = {key: {} for key in ("author", "publisher", "subject", "language")}
    author_source_keys: dict[str, str] = {}
    books: list[dict[str, Any]] = []

    def add_folder(key: str, title: str, parent: str | None) -> str:
        identifier = node_id("folder", key)
        ancestors = []
        if parent:
            parent_node = next(item for item in folders if item["id"] == parent)
            ancestors = [*parent_node["ancestors"], parent]
        folders.append(node(identifier, "CatalogFolder", now, parent=parent, ancestors=ancestors, title=title, description=None))
        return identifier

    author_root = add_folder("authors", "Authors", None)
    publisher_root = add_folder("publishers", "Publishers", None)
    subject_root = add_folder("subjects", "Subjects", None)
    language_root = add_folder("languages", "Languages", None)
    books_root = add_folder("books", "Books", None)

    author_folders: dict[str, str] = {}
    publisher_folders: dict[str, str] = {}
    author_folders["Non Latin"] = add_folder("authors/non-latin", "Non Latin", author_root)
    publisher_folders["Non Latin"] = add_folder("publishers/non-latin", "Non Latin", publisher_root)
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        author_folders[letter] = add_folder(f"authors/{letter}", letter, author_root)
        publisher_folders[letter] = add_folder(f"publishers/{letter}", letter, publisher_root)

    def get_ref(kind: str, key: str) -> str:
        if key not in indexes[kind]:
            indexes[kind][key] = node_id(kind, key)
        return indexes[kind][key]

    for index in range(book_count):
        base = source[index % len(source)]
        variant = index // len(source)
        source_key = str(base["key"])
        book_key = f"{source_key}#demo-{index}"
        title = str(base["title"])
        if variant:
            title = f"{title} ({variant + 1}th catalog record)"
        author_name = str(base.get("author") or "Unknown Author")
        if isinstance(base.get("author_key"), str) and base["author_key"]:
            author_source_keys[author_name] = base["author_key"]
        language_name = str(base.get("language") or "English")
        subject_name = str(base.get("subject") or "Fiction")
        author_ref = get_ref("author", author_name)
        language_ref = get_ref("language", language_name)
        subject_ref = get_ref("subject", subject_name)
        year = base.get("year") if isinstance(base.get("year"), int) else None
        if year is not None and year < 1:
            year = None
        first_published = None
        if year is not None:
            first_published = f"{year:04d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        book_year = year or 0
        year_folder_key = f"books/{book_year}"
        year_folder = next((item["id"] for item in folders if item["id"] == node_id("folder", year_folder_key)), None)
        if year_folder is None:
            year_folder = add_folder(year_folder_key, str(year) if year else "Unknown date", books_root)
        book_id = node_id("book", book_key)
        cover_id = base.get("cover_i")
        cover = image_descriptor(index, cover_id)
        source_isbn = [value for value in base.get("isbn", []) if isinstance(value, str)]
        isbn10 = [value for value in source_isbn if len(value.replace("-", "")) == 10][:3]
        isbn13 = [value for value in source_isbn if len(value.replace("-", "")) == 13][:3]
        source_publishers = base.get("publishers") or []
        publisher_names = [value for value in source_publishers if isinstance(value, str) and value]
        if not publisher_names:
            publisher_names = [PUBLISHERS[index % len(PUBLISHERS)]]
        publisher_refs = [get_ref("publisher", name) for name in publisher_names[:3]]
        book = node(
            book_id, "Book", now, parent=year_folder,
            ancestors=ancestors_for(folders, year_folder),
            title=title,
            subtitle=None if index % 5 == 0 else ("A demo subtitle" if index % 3 == 0 else None),
            description=base.get("description") if index % 4 else f"A catalog description for {title}.",
            first_published=first_published,
            number_of_pages_median=base.get("number_of_pages_median"),
            authors=[author_ref],
            subjects=[] if index % 11 == 0 else [{"subject": subject_ref}],
            languages=[] if index % 13 == 0 else [language_ref],
            publishers=publisher_refs,
            cover=cover,
            illustrations=[],
            identifiers={
                "isbn10": isbn10 if source_isbn else ([] if index % 7 == 0 else [f"0{index % 10_000_000:09d}"]),
                "isbn13": isbn13 if source_isbn else ([] if index % 9 == 0 else [f"978{index % 1_000_000_000:09d}"]),
                "oclc_numbers": [] if index % 6 else [f"ocn{100000 + index}"],
                "lccn": [],
            },
            rating=None if index % 8 == 0 else round(2.5 + rng.random() * 2.5, 2),
            source_key=source_key,
            openlibrary_url=f"https://openlibrary.org{source_key}",
        )
        books.append(book)

    for index, book in enumerate(books):
        other_indexes = [other_index for other_index in range(len(books)) if other_index != index]
        illustration_count = rng.randint(0, min(7, len(other_indexes)))
        selected_indexes = rng.sample(other_indexes, illustration_count)
        book["illustrations"] = [
            image_descriptor(other_index, source[other_index % len(source)].get("cover_i"))
            for other_index in selected_indexes
        ]

    author_rooted = make_reference_nodes("Author", indexes["author"], author_folders, folders, books, now, rng, author_source_keys=author_source_keys)
    publisher_rooted = make_reference_nodes("Publisher", indexes["publisher"], publisher_folders, folders, books, now, rng, publisher=True)
    subject_rooted = make_subject_nodes(indexes["subject"], subject_root, folders, books, now, rng)
    language_rooted = make_language_nodes(indexes["language"], language_root, folders, books, now, rng)
    nodes.extend(folders)
    nodes.extend(book for book in books)
    nodes.extend(author_rooted)
    nodes.extend(publisher_rooted)
    nodes.extend(subject_rooted)
    nodes.extend(language_rooted)
    return {"CatalogFolder": folders, "Book": books, "Author": author_rooted, "Publisher": publisher_rooted, "Subject": subject_rooted, "Language": language_rooted, "_all": nodes}


def node(identifier: str, entity: str, now: str, *, parent: str | None, ancestors: list[str], deleted: bool = False, **fields: Any) -> dict[str, Any]:
    return {
        "id": identifier, "entity": entity, "parent": parent,
        "owner": "", "group": "", "perm": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": True, "w": True, "p": True}, "others": {"r": True, "w": True, "p": True}},
        "depth": len(ancestors), "ancestors": ancestors, "deleted": deleted,
        "cdate": now, "mdate": now, **fields,
    }


def ancestors_for(folders: list[dict[str, Any]], identifier: str) -> list[str]:
    folder = next(item for item in folders if item["id"] == identifier)
    return [*folder["ancestors"], identifier]


def image_descriptor(index: int, cover_id: Any = None) -> dict[str, Any]:
    image_id = cover_id if isinstance(cover_id, int) else index + 1
    return {"url": f"https://covers.openlibrary.org/b/id/{image_id}-M.jpg", "mime-type": "image/jpeg", "width": 300, "height": 450, "size": 0}


def make_reference_nodes(entity: str, refs: dict[str, str], folders_by_letter: dict[str, str], folders: list[dict[str, Any]], related: list[dict[str, Any]], now: str, rng: Random, *, publisher: bool = False, author_source_keys: dict[str, str] | None = None) -> list[dict[str, Any]]:
    reverse: dict[str, list[str]] = defaultdict(list)
    related_by_id: dict[str, dict[str, Any]] = {}
    if not publisher:
        related_by_id = {item["id"]: item for item in related}
        for item in related:
            for identifier in item.get("authors", []):
                reverse[identifier].append(item["id"])
    result = []
    for index, (name, identifier) in enumerate(sorted(refs.items())):
        letter = name[:1].upper()
        parent = folders_by_letter.get(letter) if letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" else folders_by_letter["Non Latin"]
        if publisher:
            fields = {"name": name, "source_key": f"/publishers/{name}"}
        else:
            cooperation_count = rng.randint(1, min(7, len(reverse[identifier])))
            cooperation_book_ids = rng.sample(reverse[identifier], cooperation_count)
            best_cooperations = []
            for book_id in cooperation_book_ids:
                book = related_by_id[book_id]
                first_published = book.get("first_published")
                best_cooperations.append({
                    "book": book_id,
                    "publisher": book["publishers"][0],
                    "year": int(first_published[:4]) if first_published else None,
                })
            fields = {
                "name": name,
                "alternate_names": [] if index % 4 == 0 else [name.split()[-1]],
                "bio": None if index % 5 else f"Biography of {name}.",
                "best_cooperations": best_cooperations,
                "source_key": f"/authors/{name}",
                "openlibrary_url": f"https://openlibrary.org{author_source_keys[name]}" if author_source_keys and name in author_source_keys else None,
            }
        result.append(node(identifier, entity, now, parent=parent, ancestors=ancestors_for(folders, parent), **fields))
    return result


def make_subject_nodes(refs: dict[str, str], parent: str, folders: list[dict[str, Any]], books: list[dict[str, Any]], now: str, rng: Random) -> list[dict[str, Any]]:
    reverse: dict[str, list[str]] = defaultdict(list)
    for book in books:
        for item in book["subjects"]:
            reverse[item["subject"]].append(book["id"])
    categories = ["Fiction", "History", "Science", "Biography", "Children", "Technology", "Philosophy", "Poetry"]
    result = []
    for index, (name, identifier) in enumerate(sorted(refs.items())):
        book_ids = reverse[identifier]
        best_books = rng.sample(book_ids, rng.randint(1, min(15, len(book_ids)))) if book_ids else []
        result.append(node(identifier, "Subject", now, parent=parent, ancestors=ancestors_for(folders, parent), name=name, category=categories[index % len(categories)], description=None if index % 3 else f"Books about {name}.", best_books=best_books, source_key=f"/subjects/{name}"))
    return result


def make_language_nodes(refs: dict[str, str], parent: str, folders: list[dict[str, Any]], books: list[dict[str, Any]], now: str, rng: Random) -> list[dict[str, Any]]:
    reverse_books: dict[str, list[str]] = defaultdict(list)
    for book in books:
        for identifier in book["languages"]:
            reverse_books[identifier].append(book["id"])
    result = []
    for name, identifier in sorted(refs.items()):
        code, native = LANGUAGES.get(name, (name[:2].lower(), name))
        book_ids = reverse_books[identifier]
        best_books = rng.sample(book_ids, rng.randint(1, min(15, len(book_ids)))) if book_ids else []
        result.append(node(identifier, "Language", now, parent=parent, ancestors=ancestors_for(folders, parent), code=code, name=name, native_name=native if native != name else None, best_books=best_books, source_key=f"/languages/{code}"))
    return result
