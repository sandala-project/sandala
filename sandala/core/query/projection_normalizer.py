from __future__ import annotations

from sandala.core.errors import QueryValidationError


class ProjectionNormalizer:
    def filter_exclusions(self, paths: set[str], projection: dict[str, int]) -> list[str]:
        included = [path for path, value in projection.items() if value == 1]
        if not included:
            return sorted(paths)
        return sorted(path for path in paths if any(
            path == field or path.startswith(f"{field}.") or field.startswith(f"{path}.")
            for field in included
        ))

    def normalize_exclusions(self, paths: set[str]) -> list[str]:
        normalized: list[str] = []
        for path in sorted(paths, key=lambda value: (value.count("."), value)):
            if not any(path.startswith(f"{parent}.") for parent in normalized):
                normalized.append(path)
        return normalized

    def normalize_final(self, project: list[str]) -> list[str]:
        records: dict[str, bool] = {}
        for path in project:
            if path.endswith(".*"):
                base = path[:-2]
                if not base:
                    raise QueryValidationError("Invalid project path '*.': missing base field")
                records[base] = True
            else:
                records[path] = records.get(path, False)

        wildcard_bases = {base for base, is_wildcard in records.items() if is_wildcard}
        candidates = set(records.keys())

        for path in list(candidates):
            if any(path != base and path.startswith(f"{base}.") for base in wildcard_bases):
                candidates.discard(path)

        ordered = sorted(candidates, key=lambda p: (p.count("."), p))
        normalized: list[str] = []
        for path in ordered:
            if records.get(path, False):
                normalized.append(path)
                continue
            if any(other != path and other.startswith(f"{path}.") for other in ordered):
                continue
            normalized.append(path)
        return normalized

    def normalize_lookup(self, project: list[str]) -> list[str]:
        records: dict[str, bool] = {}
        for path in project:
            if path.endswith(".*"):
                base = path[:-2]
                if not base:
                    raise QueryValidationError("Invalid project path '*.': missing base field")
                records[base] = True
            else:
                records[path] = records.get(path, False)

        ordered = sorted(records.keys(), key=lambda p: (p.count("."), p))
        normalized: list[str] = []
        for path in ordered:
            if records.get(path, False):
                normalized.append(path)
                continue
            if any(other != path and other.startswith(f"{path}.") for other in ordered):
                continue
            normalized.append(path)
        return normalized
