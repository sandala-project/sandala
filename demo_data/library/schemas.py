from __future__ import annotations

from copy import deepcopy
from typing import Any


MODULE = "demo_library"
ENTITIES = ("CatalogFolder", "Book", "Author", "Publisher", "Subject", "Language")

COUNTRIES = [
    "Afghanistan", "Åland Islands", "Albania", "Algeria", "American Samoa", "Andorra", "Angola", "Anguilla", "Antarctica", "Antigua and Barbuda", "Argentina", "Armenia", "Aruba", "Australia", "Austria", "Azerbaijan",
    "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bermuda", "Bhutan", "Bolivia, Plurinational State of", "Bonaire, Sint Eustatius and Saba", "Bosnia and Herzegovina", "Botswana", "Bouvet Island", "Brazil", "British Indian Ocean Territory", "Brunei Darussalam", "Bulgaria", "Burkina Faso", "Burundi",
    "Cabo Verde", "Cambodia", "Cameroon", "Canada", "Cayman Islands", "Central African Republic", "Chad", "Chile", "China", "Christmas Island", "Cocos (Keeling) Islands", "Colombia", "Comoros", "Congo", "Congo, Democratic Republic of the", "Cook Islands", "Costa Rica", "Côte d'Ivoire", "Croatia", "Cuba", "Curaçao", "Cyprus", "Czechia",
    "Denmark", "Djibouti", "Dominica", "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Falkland Islands (Malvinas)", "Faroe Islands", "Fiji", "Finland", "France", "French Guiana", "French Polynesia", "French Southern Territories",
    "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Gibraltar", "Greece", "Greenland", "Grenada", "Guadeloupe", "Guam", "Guatemala", "Guernsey", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Heard Island and McDonald Islands", "Holy See", "Honduras", "Hong Kong", "Hungary",
    "Iceland", "India", "Indonesia", "Iran, Islamic Republic of", "Iraq", "Ireland", "Isle of Man", "Israel", "Italy", "Jamaica", "Japan", "Jersey", "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Korea, Democratic People's Republic of", "Korea, Republic of", "Kuwait",
    "Lao People's Democratic Republic", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Macao", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Marshall Islands", "Martinique", "Mauritania", "Mauritius", "Mayotte", "Mexico", "Micronesia, Federated States of", "Moldova, Republic of", "Monaco", "Mongolia", "Montenegro", "Montserrat", "Morocco", "Mozambique", "Myanmar",
    "Namibia", "Nauru", "Nepal", "Netherlands, Kingdom of the", "New Caledonia", "New Zealand", "Nicaragua", "Niger", "Nigeria", "Niue", "Norfolk Island", "North Macedonia", "Northern Mariana Islands", "Norway", "Oman", "Pakistan", "Palau", "Palestine, State of", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Pitcairn", "Poland", "Portugal", "Puerto Rico",
    "Qatar", "Réunion", "Romania", "Russian Federation", "Rwanda", "Saint Barthélemy", "Saint Helena, Ascension and Tristan da Cunha", "Saint Kitts and Nevis", "Saint Lucia", "Saint Martin (French part)", "Saint Pierre and Miquelon", "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Sint Maarten (Dutch part)", "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Georgia and the South Sandwich Islands", "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Svalbard and Jan Mayen", "Sweden", "Switzerland", "Syrian Arab Republic",
    "Taiwan, Province of China", "Tajikistan", "Tanzania, United Republic of", "Thailand", "Timor-Leste", "Togo", "Tokelau", "Tonga", "Trinidad and Tobago", "Tunisia", "Türkiye", "Turkmenistan", "Turks and Caicos Islands", "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom of Great Britain and Northern Ireland", "United States of America", "United States Minor Outlying Islands", "Uruguay", "Uzbekistan", "Vanuatu", "Venezuela, Bolivarian Republic of", "Viet Nam", "Virgin Islands (British)", "Virgin Islands (U.S.)", "Wallis and Futuna", "Western Sahara", "Yemen", "Zambia", "Zimbabwe",
]

PERM = {
    "owner": {"r": True, "w": True, "p": True},
    "group": {"r": True, "w": True, "p": True},
    "others": {"r": True, "w": True, "p": True},
}


def _meta(kind: str, *, visibility: str = "all", write: str = "all", **extra: Any) -> dict[str, Any]:
    value = {"semantic-type": kind, "visibility-mode": visibility, "write-mode": write}
    value.update(extra)
    return value


def field(kind: str, description: str, *, nullable: bool = False, **schema: Any) -> dict[str, Any]:
    base = {"description": description, "x-meta": _meta(kind), **schema}
    if kind == "String":
        base.setdefault("type", "string")
    elif kind == "Number":
        base.setdefault("type", "number")
    elif kind == "Text":
        base.setdefault("type", "string")
    elif kind == "RichText":
        base.setdefault("type", "string")
    elif kind == "Integer":
        base.setdefault("type", "integer")
    elif kind == "Boolean":
        base.setdefault("type", "boolean")
    elif kind == "Date":
        base.update({"type": "string", "format": "date"})
    elif kind == "DateTime":
        base.update({"type": "string", "format": "date-time"})
    if not nullable:
        return base
    return {"anyOf": [base, {"type": "null"}]}


def link(description: str, entity: str, *, nullable: bool = False) -> dict[str, Any]:
    value = field("Link", description, type="string", format="uuid")
    value["x-meta"]["link"] = {"module": MODULE, "entities": [entity]}
    if nullable:
        return {"anyOf": [value, {"type": "null"}]}
    return value


def link_array(description: str, entity: str, *, min_items: int = 0) -> dict[str, Any]:
    value = field(
        "LinkArray",
        description,
        type="array",
        items={"type": "string", "format": "uuid"},
        minItems=min_items,
    )
    value["x-meta"]["link"] = {"module": MODULE, "entities": [entity]}
    return value


def string_array(description: str) -> dict[str, Any]:
    return field(
        "Array",
        description,
        type="array",
        items=field("String", "Array item"),
    )


def object_field(description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return field(
        "Object",
        description,
        type="object",
        properties=properties,
        required=required,
        additionalProperties=False,
    )


def subject_item() -> dict[str, Any]:
    return object_field(
        "Book subject item",
        {"subject": link("Subject", "Subject")},
        ["subject"],
    )


def cooperation_item() -> dict[str, Any]:
    return object_field(
        "Author and publisher cooperation",
        {
            "book": link("Book", "Book"),
            "publisher": link("Publisher", "Publisher"),
            "year": field("Number", "Publication year", nullable=True),
        },
        ["book", "publisher", "year"],
    )


def image_field(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "mime-type": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "size": {"type": "integer"},
        },
        "required": ["url", "mime-type", "width", "height", "size"],
        "additionalProperties": False,
        "x-meta": _meta("Image"),
    }


def image_array(description: str, *, min_items: int = 0, max_items: int | None = None) -> dict[str, Any]:
    value = field("Array", description, type="array", items=image_field("Image item"), minItems=min_items)
    if max_items is not None:
        value["maxItems"] = max_items
    return value


def _schema(
    entity: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
    children: list[str] | None = None,
    label_template: str | None = None,
) -> dict[str, Any]:
    schema = {
        "title": entity,
        "description": description,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
        "x-meta": {
            "children": {"entities": children or []},
            "perm": {"default": deepcopy(PERM)},
        },
    }
    if label_template is not None:
        schema["x-ui"] = {
            "labels": {
                "tree": label_template,
                "reference": label_template,
            },
        }
    return schema


def schemas() -> dict[str, dict[str, Any]]:
    identifiers = object_field(
        "External identifiers",
        {
            "isbn10": string_array("ISBN-10 identifiers"),
            "isbn13": string_array("ISBN-13 identifiers"),
            "oclc_numbers": string_array("OCLC identifiers"),
            "lccn": string_array("Library of Congress identifiers"),
        },
        [],
    )
    return {
        "CatalogFolder": _schema(
            "CatalogFolder", "Folder",
            {
                "title": field("String", "Folder title"),
                "description": field("Text", "Folder description", nullable=True),
            },
            ["title"],
            list(ENTITIES),
            "📁 {{title}}",
        ),
        "Book": _schema(
            "Book", "",
            {
                "title": field("String", "Book title"),
                "subtitle": field("String", "Book subtitle", nullable=True),
                "description": field("RichText", "Book description", nullable=True),
                "first_published": field("Date", "First publication date", nullable=True),
                "number_of_pages_median": field("Integer", "Median number of pages", nullable=True, minimum=1),
                "authors": link_array("Authors", "Author", min_items=1),
                "subjects": field("Array", "Subjects", type="array", items=subject_item()),
                "languages": link_array("Languages", "Language"),
                "publishers": link_array("Publishers", "Publisher"),
                "cover": image_field("Book cover"),
                "illustrations": image_array("Illustrations", max_items=7),
                "identifiers": identifiers,
                "rating": field("Number", "Rating", nullable=True, minimum=0, maximum=5),
                "source_key": field("String", "Open Library work key"),
                "openlibrary_url": field("String", "Open Library URL"),
            },
            ["title", "authors", "publishers", "cover", "illustrations", "identifiers", "source_key", "openlibrary_url"],
            label_template="📖 {{title}}",
        ),
        "Author": _schema(
            "Author", "",
            {
                "name": field("String", "Display name"),
                "alternate_names": string_array("Alternate names"),
                "birth_date": field("Date", "Birth date", nullable=True),
                "death_date": field("Date", "Death date", nullable=True),
                "bio": field("RichText", "Biography", nullable=True),
                "best_cooperations": field("Array", "Best cooperations", type="array", items=cooperation_item()),
                "source_key": field("String", "Open Library author key"),
                "openlibrary_url": field("String", "Open Library URL", nullable=True),
            },
            ["name", "alternate_names", "best_cooperations", "source_key"],
            label_template="🖋️ {{name}}",
        ),
        "Publisher": _schema(
            "Publisher", "",
            {
                "name": field("String", "Publisher name"),
                "country": field("String", "Country", nullable=True, enum=COUNTRIES),
                "source_key": field("String", "Stable publisher key"),
            },
            ["name", "source_key"],
            label_template="© {{name}}",
        ),
        "Subject": _schema(
            "Subject", "",
            {
                "name": field("String", "Subject name"),
                "category": field("String", "Subject category", enum=["Fiction", "History", "Science", "Biography", "Children", "Technology", "Philosophy", "Poetry"]),
                "description": field("Text", "Subject description", nullable=True),
                "best_books": link_array("Best books", "Book"),
                "source_key": field("String", "Stable subject key"),
            },
            ["name", "category", "best_books", "source_key"],
            label_template="🏷️ {{name}}",
        ),
        "Language": _schema(
            "Language", "",
            {
                "code": field("String", "ISO-like language code", minLength=2, maxLength=3),
                "name": field("String", "Language name"),
                "native_name": field("String", "Native language name", nullable=True),
                "best_books": link_array("Best books", "Book"),
                "source_key": field("String", "Stable language key"),
            },
            ["code", "name", "best_books", "source_key"],
            label_template="💬 {{name}}",
        ),
    }


def placeholder_schema(entity: str) -> dict[str, Any]:
    return _schema(entity, f"Demo {entity}.", {"label": field("String", "Temporary label")}, ["label"])
