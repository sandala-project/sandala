from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sandala.core.errors import QueryValidationError


@dataclass(frozen=True)
class PipelineBuildInput:
    initial_match: dict[str, Any]
    final_match: dict[str, Any]
    lookup_stages: list[dict[str, Any]]
    sort_stage: dict[str, int]
    project_stage: dict[str, int]
    field_exclusions: list[str]
    post_match_unset: list[str]
    offset: int
    limit: int | None


class MongoPipelineBuilder:
    def compile_sort(self, sort_dsl: dict[str, Any]) -> dict[str, int]:
        result: dict[str, int] = {}
        for field, direction in sort_dsl.items():
            if direction == "asc":
                result[field] = 1
            elif direction == "desc":
                result[field] = -1
            else:
                raise QueryValidationError(f"Sort direction for '{field}' must be 'asc' or 'desc'")
        return result

    def build_projection(self, project: list[str], final_projection_paths: list[str]) -> dict[str, int]:
        if "*" in project:
            return {"_id": 0}

        result: dict[str, int] = {"_id": 0}
        for item in final_projection_paths:
            result[item] = 1
        return result

    def build_pipeline(self, data: PipelineBuildInput) -> list[dict[str, Any]]:
        if data.lookup_stages:
            pipeline: list[dict[str, Any]] = [
                {"$match": data.initial_match},
                *data.lookup_stages,
                {"$match": data.final_match},
            ]
        else:
            pipeline = [{"$match": data.final_match}]

        if data.post_match_unset:
            pipeline.append({"$unset": data.post_match_unset})
        if data.sort_stage:
            pipeline.append({"$sort": data.sort_stage})
        pipeline.append({"$project": data.project_stage})
        if data.field_exclusions:
            pipeline.append({"$unset": data.field_exclusions})
        if data.offset:
            pipeline.append({"$skip": data.offset})
        if data.limit is not None:
            pipeline.append({"$limit": data.limit})

        return pipeline
