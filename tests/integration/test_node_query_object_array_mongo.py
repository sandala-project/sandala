from __future__ import annotations

import pytest

from sandala.core.time_utils import utc_now_iso
from tests.integration.helpers import mongo_services


@pytest.mark.integration
@pytest.mark.parametrize("is_array", [False, True], ids=["object", "object-array"])
def test_query_container_filter_does_not_depend_on_early_narrowing_when_links_resolve(is_array):
    with mongo_services() as (entity_service, service, repo):
        modes = {"visibility-mode": "all", "write-mode": "all"}
        payload_schema = {
            "type": "object", "additionalProperties": False,
            "x-meta": {"semantic-type": "Object", **modes},
            "properties": {"child": {
                "type": "string", "format": "uuid",
                "x-meta": {"semantic-type": "Link", **modes,
                           "link": {"module": "library", "entities": ["Person"]}},
            }},
        }
        schema = _product_schema()
        schema["properties"]["payload"] = (
            {"type": "array", "items": payload_schema, "x-meta": {"semantic-type": "Array", **modes}}
            if is_array else payload_schema
        )
        ids = _seed_object_array_dataset(entity_service, repo, product_schema=schema)
        raw_payload = {"child": ids["person_anna"]}
        repo.collection("library").update_one(
            {"id": ids["product_alpha"]},
            {"$set": {"payload": [raw_payload] if is_array else raw_payload}},
        )
        resolved_payload = {"child": {"name": "Anna"}}
        expected = [{"sku": "alpha", "payload": [resolved_payload] if is_array else resolved_payload}]

        for name in ("Anna", "Boris"):
            value = {"child": {"name": name}}
            operand = [value] if is_array else value
            for operator in ("eq", "in"):
                condition = {"payload": {operator: [operand] if operator == "in" else operand}}
                # Only the first two forms are candidates for early narrowing.
                for extra_filter in (condition, {"and": [condition]}, {"or": [condition]}):
                    rows = service.query("library", {
                        "filter": {"entity": "Product", "id": ids["product_alpha"], **extra_filter},
                        "project": ["sku", "payload.*", "payload.child.name"],
                    })
                    assert rows == (expected if name == "Anna" else [])


@pytest.mark.integration
def test_query_object_array_wildcard_keeps_nested_link_ids_without_resolve():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_object_array_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "sku", "meta.*", "variants.*"],
                "filter": {"entity": "Product", "sku": "alpha"},
            },
        )

        assert len(rows) == 1
        product = rows[0]
        assert product["name"] == "Alpha Product"
        assert product["sku"] == "alpha"
        assert product["meta"]["category"] == "Books"
        assert product["meta"]["stats"] == {"score": 90, "rank": 1}
        assert product["meta"]["manufacturer"] == ids["company_a"]

        assert len(product["variants"]) == 2
        by_code = {variant["code"]: variant for variant in product["variants"]}
        assert by_code["A-1"]["price"] == 10.5
        assert by_code["A-1"]["inspector"] == ids["person_anna"]
        assert by_code["A-1"]["backup_inspectors"] == [ids["person_boris"], ids["person_deleted"]]
        assert by_code["A-1"]["details"]["approver"] == ids["person_boris"]
        assert by_code["A-1"]["attributes"] == {"color": "red", "size": 42}
        assert by_code["A-2"]["price"] == 22.0
        assert by_code["A-2"]["inspector"] == ids["person_boris"]
        assert by_code["A-2"]["backup_inspectors"] == [ids["person_anna"]]
        assert by_code["A-2"]["details"]["approver"] == ids["person_anna"]
        assert by_code["A-2"]["attributes"] == {"color": "blue", "size": 44}


@pytest.mark.integration
def test_query_explicit_descent_resolves_link_inside_object_and_keeps_array_shape():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_object_array_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                    "project": [
                        "name",
                        "sku",
                        "meta.manufacturer.name",
                        "meta.manufacturer.country",
                        "variants.code",
                        "variants.price",
                        "variants.inspector.name",
                        "variants.backup_inspectors.name",
                        "variants.details.approver.name",
                        "variants.attributes.*",
                    ],
                "filter": {"entity": "Product", "sku": "gamma"},
            },
        )

        assert len(rows) == 1
        product = rows[0]
        assert product["name"] == "Gamma Product"
        assert product["sku"] == "gamma"
        assert product["meta"]["manufacturer"] == {"name": "Acme", "country": "RU"}

        assert len(product["variants"]) == 1
        variant = product["variants"][0]
        assert variant["code"] == "G-1"
        assert variant["price"] == 35.0
        assert "inspector" not in variant  # The narrow projection selects inspector.name, not inspector itself.
        assert variant["backup_inspectors"] == [{"name": "Anna"}]
        assert variant["details"] == {"approver": {"name": "Boris"}}
        assert variant["attributes"] == {"color": "black", "size": 40}


@pytest.mark.integration
def test_list_entity_default_project_resolves_links_inside_object_and_array():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_object_array_dataset(entity_service, node_repo)

        rows = node_service.list_entity("library", "Product", {"filter": {"sku": "gamma"}})

        assert len(rows) == 1
        product = rows[0]
        assert product["meta"]["manufacturer"]["name"] == "Acme"
        assert product["meta"]["manufacturer"]["country"] == "RU"
        variant = product["variants"][0]
        assert variant["inspector"] is None
        assert variant["backup_inspectors"][0]["name"] == "Anna"
        assert variant["details"]["approver"]["name"] == "Boris"


@pytest.mark.integration
def test_query_filters_on_nested_object_and_array_paths():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_object_array_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "sku", "meta.stats.*", "variants.code", "variants.price"],
                "filter": {
                    "entity": "Product",
                    "meta.stats.score": {"gte": 70},
                    "variants.price": {"lt": 20},
                },
                "sort": {"sku": "asc"},
            },
        )

        assert [row["sku"] for row in rows] == ["alpha", "beta"]
        assert rows[0]["meta"]["stats"] == {"score": 90, "rank": 1}
        assert rows[1]["meta"]["stats"] == {"score": 72, "rank": 2}

        alpha_variants = {item["code"]: item["price"] for item in rows[0]["variants"]}
        beta_variants = {item["code"]: item["price"] for item in rows[1]["variants"]}
        assert alpha_variants == {"A-1": 10.5, "A-2": 22.0}
        assert beta_variants == {"B-1": 15.0}


@pytest.mark.integration
def test_query_sorts_by_nested_object_field_and_is_stable():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_object_array_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "sku", "meta.stats.rank", "meta.stats.score", "meta.category"],
                "filter": {"entity": "Product"},
                "sort": {"meta.stats.rank": "asc", "sku": "asc"},
            },
        )

        assert [row["sku"] for row in rows] == ["alpha", "beta", "gamma"]
        assert rows[0]["meta"] == {"stats": {"rank": 1, "score": 90}, "category": "Books"}
        assert rows[1]["meta"] == {"stats": {"rank": 2, "score": 72}, "category": "Books"}
        assert rows[2]["meta"] == {"stats": {"rank": 3, "score": 65}, "category": "Games"}


@pytest.mark.integration
def test_query_aux_filter_and_sort_fields_do_not_leak_for_object_array_paths():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_object_array_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "sku"],
                "filter": {
                    "entity": "Product",
                    "meta.stats.rank": {"lte": 2},
                    "variants.attributes.color": {"in": ["red", "green"]},
                    "variants.details.approver.name": {"eq": "Boris"},
                },
                "sort": {
                    "meta.stats.rank": "asc",
                    "variants.details.approver.level": "desc",
                    "sku": "asc",
                },
            },
        )

        assert rows == [
            {"name": "Alpha Product", "sku": "alpha"},
            {"name": "Beta Product", "sku": "beta"},
        ]


@pytest.mark.integration
def test_query_hooks_filter_and_hide_link_targets_inside_objects_and_arrays():
    with mongo_services() as (entity_service, service, repo):
        _seed_object_array_dataset(entity_service, repo)

        def before_query(context):
            context.add_required_filter({"or": [{"entity": {"neq": "Product"}}, {"meta.stats.score": {"gte": 70}}]})
            context.add_required_filter({"or": [
                {"entity": {"neq": "Product"}}, {"variants.attributes.color": {"in": ["red", "green"]}},
            ]})
            context.add_required_filter({"or": [{"entity": {"neq": "Person"}}, {"level": {"gte": 3}}]})
            context.exclude_fields("meta.stats.rank", "variants.attributes.color", "variants.details.approver.level", "level")

        service.hooks.register("before_query", before_query, module="library")
        rows = service.query(
            "library",
            {
                "filter": {"entity": "Product"},
                "project": ["*", "meta.manufacturer.*", "variants.inspector.*", "variants.backup_inspectors.*", "variants.details.approver.*"],
                "sort": {"sku": "asc"},
            },
        )

        assert [row["sku"] for row in rows] == ["alpha", "beta"]
        assert all("rank" not in row["meta"]["stats"] for row in rows)
        assert all("color" not in variant["attributes"] for row in rows for variant in row["variants"])
        alpha = rows[0]
        assert [variant["code"] for variant in alpha["variants"]] == ["A-1", "A-2"]
        assert alpha["variants"][0]["inspector"]["name"] == "Anna"
        assert "level" not in alpha["variants"][0]["inspector"]
        assert alpha["variants"][0]["backup_inspectors"] == []
        assert alpha["variants"][0]["details"].get("approver") is None
        assert alpha["variants"][1].get("inspector") is None
        assert alpha["variants"][1]["backup_inspectors"][0]["name"] == "Anna"
        assert "level" not in alpha["variants"][1]["backup_inspectors"][0]
        assert alpha["variants"][1]["details"]["approver"]["name"] == "Anna"
        assert "level" not in alpha["variants"][1]["details"]["approver"]
        assert alpha["meta"]["manufacturer"]["name"] == "Acme"


@pytest.mark.integration
def test_query_hook_stored_filters_and_exclusions_traverse_two_array_containers():
    with mongo_services() as (entity_service, service, repo):
        modes = {"visibility-mode": "all", "write-mode": "all"}
        schema = _product_schema()
        schema["properties"]["sections"] = {
            "type": "array",
            "x-meta": {"semantic-type": "Array", **modes},
            "items": {
                "type": "object",
                "additionalProperties": False,
                "x-meta": {"semantic-type": "Object", **modes},
                "properties": {
                    "groups": {
                        "type": "array",
                        "x-meta": {"semantic-type": "Array", **modes},
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "x-meta": {"semantic-type": "Object", **modes},
                            "properties": {
                                "allowed": {"type": "boolean", "x-meta": {"semantic-type": "Boolean", **modes}},
                                "secret": {"type": "string", "x-meta": {"semantic-type": "String", **modes}},
                            },
                        },
                    },
                },
            },
        }
        ids = _seed_object_array_dataset(entity_service, repo, product_schema=schema)
        repo.collection("library").update_one(
            {"id": ids["product_alpha"]},
            {"$set": {"sections": [
                {"groups": [{"allowed": True, "secret": "a"}, {"allowed": False, "secret": "b"}]},
                {"groups": [{"allowed": False, "secret": "c"}]},
            ]}},
        )
        repo.collection("library").update_one(
            {"id": ids["product_beta"]},
            {"$set": {"sections": [{"groups": [{"allowed": False, "secret": "d"}]}]}},
        )

        def before_query(context):
            context.add_required_filter({"sections.groups.allowed": True})
            context.exclude_fields("sections.groups.secret")

        service.hooks.register("before_query", before_query, module="library")
        rows = service.query("library", {"filter": {"entity": "Product"}, "project": ["sku", "sections"]})

        assert rows == [{"sku": "alpha", "sections": [
            {"groups": [{"allowed": True}, {"allowed": False}]},
            {"groups": [{"allowed": False}]},
        ]}]
        stored = repo.find_by_id("library", ids["product_alpha"])
        assert stored["sections"][0]["groups"][0]["secret"] == "a"


@pytest.mark.integration
@pytest.mark.parametrize("semantic_type", ["Link", "LinkArray"])
@pytest.mark.parametrize("policy_enabled", [False, True], ids=["without-hooks", "with-hooks"])
def test_query_hooks_resolve_references_below_two_arrays_and_intermediate_objects(semantic_type, policy_enabled):
    with mongo_services() as (entity_service, service, repo):
        modes = {"visibility-mode": "all", "write-mode": "all"}

        def object_field(properties):
            return {
                "type": "object", "additionalProperties": False,
                "x-meta": {"semantic-type": "Object", **modes}, "properties": properties,
            }

        def array_field(items):
            return {"type": "array", "x-meta": {"semantic-type": "Array", **modes}, "items": items}

        string_field = {"type": "string", "x-meta": {"semantic-type": "String", **modes}}
        reference = {
            "x-meta": {"semantic-type": semantic_type, **modes, "link": {"module": "library", "entities": ["Person"]}},
        }
        if semantic_type == "Link":
            reference.update({"type": "string", "format": "uuid"})
        else:
            reference.update({"type": "array", "items": {"type": "string", "format": "uuid"}})
        schema = _product_schema()
        schema["properties"]["sections"] = array_field(object_field({
            "name": string_field,
            "member": object_field({"team": object_field({
                "groups": array_field(object_field({
                    "label": string_field,
                    "group": object_field({"reviewers": reference}),
                })),
            })}),
        }))
        ids = _seed_object_array_dataset(entity_service, repo, product_schema=schema)

        def group(label, *reviewers):
            value = list(reviewers) if semantic_type == "LinkArray" else reviewers[0]
            return {"label": label, "group": {"reviewers": value}}

        anna, boris, deleted = (ids[f"person_{name}"] for name in ("anna", "boris", "deleted"))
        sections = [
            {"name": "first", "member": {"team": {"groups": [group("a", anna, boris, deleted), group("b", boris)]}}},
            {"name": "second", "member": {"team": {"groups": [group("c", anna), group("d", deleted)]}}},
            {"name": "empty", "member": {"team": {"groups": []}}},
        ]
        repo.collection("library").update_one({"id": ids["product_alpha"]}, {"$set": {"sections": sections}})
        calls = []
        reviewers_path = "sections.member.team.groups.group.reviewers"

        def before_query(context):
            if context.path == reviewers_path:
                calls.append(context.path)
            context.add_required_filter({"or": [{"entity": {"neq": "Person"}}, {"level": {"gte": 3}}]})
            context.exclude_fields("level")

        if policy_enabled:
            service.hooks.register("before_query", before_query, module="library")
        rows = service.query(
            "library",
            {"filter": {"entity": "Product", "sku": "alpha"}, "project": ["sku", "sections.*", f"{reviewers_path}.*"]},
        )

        assert len(rows) == 1
        assert rows[0]["sku"] == "alpha"
        result_sections = rows[0]["sections"]
        assert [section["name"] for section in result_sections] == ["first", "second", "empty"]
        result_groups = [section["member"]["team"]["groups"] for section in result_sections]
        assert [[item["label"] for item in groups] for groups in result_groups] == [["a", "b"], ["c", "d"], []]
        expected_ids = [
            [[anna] if policy_enabled or semantic_type == "Link" else [anna, boris], [] if policy_enabled else [boris]],
            [[anna], []],
        ]
        for groups, expected_groups in zip(result_groups[:2], expected_ids):
            for item, expected in zip(groups, expected_groups):
                visible = item["group"].get("reviewers")
                if semantic_type == "Link":
                    visible = [visible] if visible is not None else []
                assert len(visible) == len(expected)
                assert {target["id"] for target in visible} == set(expected)
                for target in visible:
                    assert target["name"] == ("Anna" if target["id"] == anna else "Boris")
                    if policy_enabled:
                        assert "level" not in target
                    else:
                        assert target["level"] == (3 if target["id"] == anna else 2)
        assert calls == ([reviewers_path] if policy_enabled else [])
        filtered = service.query("library", {
            "filter": {"entity": "Product", "sku": "alpha", f"{reviewers_path}.name": "Anna"},
            "project": ["sku", "sections.*", f"{reviewers_path}.*"],
            "sort": {f"{reviewers_path}.name": "desc"}, "limit": 1,
        })
        assert filtered == rows
        assert repo.find_by_id("library", ids["product_alpha"])["sections"] == sections


@pytest.mark.integration
@pytest.mark.parametrize("policy_enabled", [False, True], ids=["without-hooks", "with-hooks"])
def test_array_objects_resolve_links_with_ordered_items_and_all_projection_modes(policy_enabled):
    from copy import deepcopy

    with mongo_services() as (entity_service, service, repo):
        ids = _seed_object_array_dataset(entity_service, repo)
        variants = repo.find_by_id("library", ids["product_alpha"])["variants"]
        anna, boris, deleted = (ids[f"person_{name}"] for name in ("anna", "boris", "deleted"))
        missing = "93000000-0000-4930-8930-000000000199"
        unresolved = {**deepcopy(variants[0]), "code": "A-3", "inspector": deleted,
                      "backup_inspectors": [deleted, missing]}
        repeated = {**deepcopy(variants[0]), "code": "A-4", "backup_inspectors": [boris, anna]}
        variants.extend([unresolved, repeated])
        repo.collection("library").update_one({"id": ids["product_alpha"]}, {"$set": {"variants": variants}})
        before = repo.find_by_id("library", ids["product_alpha"])

        def policy(context):
            context.add_required_filter({"or": [{"entity": {"neq": "Person"}}, {"level": {"gte": 3}}]})
            context.exclude_fields("level")

        if policy_enabled:
            service.hooks.register("before_query", policy, module="library")
        for project in (["variants.*", "variants.inspector.*", "variants.backup_inspectors.*"],
                        ["variants.code", "variants.inspector.id", "variants.inspector.name",
                         "variants.backup_inspectors.id", "variants.backup_inspectors.name"], None):
            result = service.get("library", ids["product_alpha"], project=project)["variants"]
            assert [item["code"] for item in result] == ["A-1", "A-2", "A-3", "A-4"]
            expected_inspectors = [anna, None if policy_enabled else boris, None, anna]
            expected_backups = [set() if policy_enabled else {boris}, {anna}, set(),
                                {anna} if policy_enabled else {anna, boris}]
            for item, inspector_id, backups in zip(result, expected_inspectors, expected_backups):
                if inspector_id is None:
                    if project is not None and "variants.*" not in project:
                        assert "inspector" not in item
                    else:
                        assert item["inspector"] is None
                else:
                    assert item["inspector"]["id"] == inspector_id
                    if policy_enabled:
                        assert "level" not in item["inspector"]
                assert {target["id"] for target in item["backup_inspectors"]} == backups
                if policy_enabled:
                    assert all("level" not in target for target in item["backup_inspectors"])
        assert service.get("library", ids["product_alpha"], project=["*"])["variants"] == variants
        assert repo.find_by_id("library", ids["product_alpha"]) == before


@pytest.mark.integration
@pytest.mark.parametrize("semantic_type", ["Array", "Link", "LinkArray"])
@pytest.mark.parametrize("nullable", [False, True])
def test_entity_schema_rejects_direct_array_and_reference_array_items(semantic_type, nullable):
    from sandala.core.errors import NotFoundError, SchemaValidationError

    with mongo_services() as (entity_service, _service, repo):
        ids = _seed_object_array_dataset(entity_service, repo)
        modes = {"visibility-mode": "all", "write-mode": "all"}
        if semantic_type == "Array":
            item = {"type": "array", "x-meta": {"semantic-type": "Array", **modes}, "items": {
                "type": "string", "x-meta": {"semantic-type": "String", **modes},
            }}
        else:
            item = {"x-meta": {"semantic-type": semantic_type, **modes,
                               "link": {"module": "library", "entities": ["Person"]}}}
            item.update({"type": "string", "format": "uuid"} if semantic_type == "Link"
                        else {"type": "array", "items": {"type": "string", "format": "uuid"}})
        if nullable:
            item = {"anyOf": [item, {"type": "null"}]}
        schema = _product_schema()
        schema["properties"]["values"] = {
            "type": "array", "items": item, "x-meta": {"semantic-type": "Array", **modes},
        }
        before_schema = entity_service.get_schema("library", "Product")
        before_node = repo.find_by_id("library", ids["product_alpha"])

        with pytest.raises(SchemaValidationError):
            entity_service.create("library", "InvalidProduct", schema)
        with pytest.raises(NotFoundError):
            entity_service.get_schema("library", "InvalidProduct")
        with pytest.raises(SchemaValidationError):
            entity_service.update("library", "Product", schema)
        assert entity_service.get_schema("library", "Product") == before_schema
        assert repo.find_by_id("library", ids["product_alpha"]) == before_node


@pytest.mark.integration
@pytest.mark.parametrize("depth", [2, 3])
def test_nested_arrays_through_objects_hide_invisible_fields_in_raw_and_resolved_projections(depth):
    with mongo_services() as (entity_service, service, repo):
        modes = {"visibility-mode": "all", "write-mode": "all"}
        items = {"type": "object", "additionalProperties": False,
                 "x-meta": {"semantic-type": "Object", **modes}, "properties": {
                     "public": {"type": "string", "x-meta": {"semantic-type": "String", **modes}},
                     "secret": {"type": "string", "x-meta": {
                         "semantic-type": "String", "visibility-mode": "none", "write-mode": "none",
                     }},
                 }}
        field = {"type": "array", "items": items, "x-meta": {"semantic-type": "Array", **modes}}
        raw, expected = [{"public": "visible", "secret": "must-not-leak"}], [{"public": "visible"}]
        for _ in range(depth - 1):
            field = {"type": "array", "x-meta": {"semantic-type": "Array", **modes}, "items": {
                "type": "object", "additionalProperties": False, "properties": {"children": field},
                "x-meta": {"semantic-type": "Object", **modes},
            }}
            raw, expected = [{"children": raw}, {"children": []}], [{"children": expected}, {"children": []}]
        schema = _product_schema()
        schema["properties"]["matrix"] = field
        ids = _seed_object_array_dataset(entity_service, repo, product_schema=schema)
        repo.collection("library").update_one({"id": ids["product_alpha"]}, {"$set": {"matrix": raw}})
        for project in (["*"], ["matrix.*"], None):
            for actor in (None, {"role": "superuser"}):
                result = service.get("library", ids["product_alpha"], project=project, actor=actor)
                assert result["matrix"] == expected


@pytest.mark.integration
@pytest.mark.parametrize("semantic_type", ["Link", "LinkArray"])
def test_nested_array_resolution_preserves_nullable_and_missing_containers(semantic_type):
    from copy import deepcopy

    with mongo_services() as (entity_service, service, repo):
        modes = {"visibility-mode": "all", "write-mode": "all"}

        def nullable(schema):
            return {"anyOf": [schema, {"type": "null"}]}

        def obj(properties):
            return nullable({"type": "object", "additionalProperties": False,
                             "properties": properties, "x-meta": {"semantic-type": "Object", **modes}})

        def arr(items):
            return nullable({"type": "array", "items": items, "x-meta": {"semantic-type": "Array", **modes}})

        reference = {"x-meta": {"semantic-type": semantic_type, **modes,
                               "link": {"module": "library", "entities": ["Person"]}}}
        reference.update({"type": "string", "format": "uuid"} if semantic_type == "Link"
                         else {"type": "array", "items": {"type": "string", "format": "uuid"}})
        reference = nullable(reference)
        schema = _product_schema()
        schema["properties"]["nested"] = obj({
            "sections": arr(obj({"branch": obj({"groups": arr(obj({"leaf": obj({"ref": reference})}))})})),
        })
        ids = _seed_object_array_dataset(entity_service, repo, product_schema=schema)
        anna = ids["person_anna"]
        raw_ref = anna if semantic_type == "Link" else [anna]
        missing = "93000000-0000-4930-8930-000000000199"
        absent_target_ids = [ids["person_deleted"], missing, ids["company_a"]]
        unresolved_leaves = [
            {"leaf": {"ref": target if semantic_type == "Link" else [target]}}
            for target in absent_target_ids
        ]
        nested = {"sections": [
            None, {}, {"branch": None}, {"branch": {}}, {"branch": {"groups": None}},
            {"branch": {"groups": []}},
            {"branch": {"groups": [None, {}, {"leaf": None}, {"leaf": {}}, {"leaf": {"ref": None}},
                                   *unresolved_leaves,
                                   {"leaf": {"ref": raw_ref}}]}},
        ]}
        expected = deepcopy(nested)
        expected_groups = expected["sections"][-1]["branch"]["groups"]
        for index in range(5, 5 + len(unresolved_leaves)):
            expected_groups[index] = {"leaf": {"ref": None if semantic_type == "Link" else []}}
        if semantic_type == "LinkArray":
            nested["sections"].append({"branch": {"groups": [{"leaf": {"ref": []}}]}})
            expected["sections"].append({"branch": {"groups": [{"leaf": {"ref": []}}]}})
        resolved = {"id": anna, "entity": "Person", "name": "Anna", "level": 3}
        expected_groups[-1]["leaf"]["ref"] = (
            resolved if semantic_type == "Link" else [resolved]
        )
        # Keep target projection narrow, so all remaining assertions compare
        # whole structures rather than overlooking introduced empty objects.
        project = ["nested.*", "nested.sections.branch.groups.leaf.ref.id",
                   "nested.sections.branch.groups.leaf.ref.entity",
                   "nested.sections.branch.groups.leaf.ref.name",
                   "nested.sections.branch.groups.leaf.ref.level"]
        for value in (nested, {"sections": []}, {"sections": None}, {}, None):
            repo.collection("library").update_one({"id": ids["product_alpha"]}, {"$set": {"nested": value}})
            result = service.get("library", ids["product_alpha"], project=project)
            assert result["nested"] == (expected if value is nested else value)
        repo.collection("library").update_one({"id": ids["product_alpha"]}, {"$unset": {"nested": ""}})
        assert "nested" not in service.get("library", ids["product_alpha"], project=project)


@pytest.mark.integration
@pytest.mark.parametrize("semantic_type", ["Link", "LinkArray"])
def test_resolution_preserves_source_states_in_objects_and_nested_lookups(semantic_type):
    from copy import deepcopy

    with mongo_services() as (entity_service, service, repo):
        modes = {"visibility-mode": "all", "write-mode": "all"}

        def nullable(field):
            return {"anyOf": [field, {"type": "null"}]}

        def obj(properties):
            return nullable({"type": "object", "additionalProperties": False, "properties": properties,
                             "x-meta": {"semantic-type": "Object", **modes}})

        ref = nullable({
            **({"type": "string", "format": "uuid"} if semantic_type == "Link" else
               {"type": "array", "items": {"type": "string", "format": "uuid"}}),
            "x-meta": {"semantic-type": semantic_type, **modes,
                       "link": {"module": "library", "entities": ["Person"]}},
        })
        payload = obj({"ref": ref, "child": obj({"ref": ref})})
        product, company = _product_schema(), _company_schema()
        for schema in (product, company):
            schema["properties"].update({"ref": ref, "payload": payload})
        ids = _seed_object_array_dataset(entity_service, repo, product_schema=product, company_schema=company)
        missing = "93000000-0000-4930-8930-000000000199"
        hidden = "93000000-0000-4930-8930-000000000198"
        policy_hidden = "93000000-0000-4930-8930-000000000197"
        now = utc_now_iso()
        hidden_node = _node(hidden, "Person", now, name="Hidden", level=4)
        hidden_node["perm"]["others"]["r"] = False
        repo.collection("library").insert_many([
            hidden_node, _node(policy_hidden, "Person", now, name="Policy hidden", level=0),
        ])

        def policy(context):
            context.add_required_filter({"or": [{"entity": {"neq": "Person"}}, {"level": {"gte": 1}}]})

        service.hooks.register("before_query", policy, module="library")
        resolved = {"id": ids["person_anna"]}
        samples = [({}, {}), ({"ref": None}, {"ref": None})]
        if semantic_type == "LinkArray":
            samples.append(({"ref": []}, {"ref": []}))
        for target in (ids["person_anna"], missing, ids["person_deleted"], hidden, policy_hidden, ids["company_b"]):
            visible = target == ids["person_anna"]
            raw_ref = target if semantic_type == "Link" else [target]
            expected_ref = (resolved if visible else None) if semantic_type == "Link" else ([resolved] if visible else [])
            samples.append(({"ref": raw_ref}, {"ref": expected_ref}))
        for raw, expected in samples:
            for child in (None, {}, raw):
                source = {**raw, "payload": {**raw, "child": child}}
                want = {**expected, "payload": {**expected, "child": expected if child is raw else child}}
                for node_id in (ids["product_alpha"], ids["company_a"]):
                    repo.collection("library").update_one({"id": node_id}, {
                        "$unset": {"ref": "", "payload": ""},
                    })
                    repo.collection("library").update_one({"id": node_id}, {"$set": deepcopy(source)})
                before = repo.find_by_id("library", ids["product_alpha"])
                for prefix in ("", "meta.manufacturer."):
                    paths = ["*", "ref.id", "payload.ref.id", "payload.child.ref.id"]
                    result = service.query("library", {
                        "filter": {"entity": "Product", "id": ids["product_alpha"]},
                        "project": [prefix + path for path in paths],
                    })[0]
                    actual = result["meta"]["manufacturer"] if prefix else result
                    actual = {key: actual[key] for key in ("ref", "payload") if key in actual}
                    assert actual == want
                    assert "__sandala_" not in repr(result)
                assert repo.find_by_id("library", ids["product_alpha"]) == before
        # A missing/null object must not be materialized by its child lookups.
        for source in ({}, {"payload": None}, {"payload": {}}, {"payload": {"child": {}}}):
            repo.collection("library").update_one({"id": ids["product_alpha"]}, {"$unset": {"ref": "", "payload": ""}})
            if source:
                repo.collection("library").update_one({"id": ids["product_alpha"]}, {"$set": source})
            result = service.get("library", ids["product_alpha"], project=[
                "*", "ref.id", "payload.ref.id", "payload.child.ref.id",
            ])
            assert {key: result[key] for key in ("ref", "payload") if key in result} == source


@pytest.mark.integration
def test_nested_arrays_through_objects_inside_lookup_apply_nested_policies():
    with mongo_services() as (entity_service, service, repo):
        modes = {"visibility-mode": "all", "write-mode": "all"}
        item = {"type": "object", "additionalProperties": False,
                "x-meta": {"semantic-type": "Object", **modes}, "properties": {
                    "reviewer": {"type": "string", "format": "uuid", "x-meta": {
                        "semantic-type": "Link", **modes, "link": {"module": "library", "entities": ["Person"]},
                    }},
                }}
        members = {"type": "array", "items": item, "x-meta": {"semantic-type": "Array", **modes}}
        item = {"type": "array", "x-meta": {"semantic-type": "Array", **modes}, "items": {
            "type": "object", "additionalProperties": False, "properties": {"members": members},
            "x-meta": {"semantic-type": "Object", **modes},
        }}
        company = _company_schema()
        company["properties"]["matrix"] = item
        ids = _seed_object_array_dataset(entity_service, repo, company_schema=company)
        matrix = [{"members": [{"reviewer": ids["person_boris"]}, {"reviewer": ids["person_anna"]}]},
                  {"members": []}, {"members": [{"reviewer": ids["person_anna"]}]}]
        repo.collection("library").update_one({"id": ids["company_a"]}, {"$set": {"matrix": matrix}})
        calls = []

        def policy(context):
            calls.append(context.path)
            context.add_required_filter({"or": [{"entity": {"neq": "Person"}}, {"level": {"gte": 3}}]})
            context.exclude_fields("level")

        service.hooks.register("before_query", policy, module="library")
        result = service.query("library", {"filter": {"entity": "Product", "sku": "alpha"}, "project": [
            "variants.*", "variants.details.approver.name", "meta.manufacturer.matrix.*",
            "meta.manufacturer.matrix.members.reviewer.*",
        ]})[0]
        actual = result["meta"]["manufacturer"]["matrix"]
        assert [len(row["members"]) for row in actual] == [2, 0, 1]
        assert actual[0]["members"][0]["reviewer"] is None
        for target in (actual[0]["members"][1]["reviewer"], actual[2]["members"][0]["reviewer"]):
            assert target["id"] == ids["person_anna"]
            assert "level" not in target
        assert calls.count("meta.manufacturer.matrix.members.reviewer") == 1
        assert calls.count("variants.details.approver") == 1


def _seed_object_array_dataset(
    entity_service, node_repo, *, product_schema: dict | None = None, company_schema: dict | None = None,
) -> dict[str, str]:
    entity_service.create("library", "Person", _person_schema())
    entity_service.create("library", "Company", company_schema if company_schema is not None else _company_schema())
    entity_service.create("library", "Product", product_schema if product_schema is not None else _product_schema())

    now = utc_now_iso()
    ids = {
        "company_a": "93000000-0000-4930-8930-000000000001",
        "company_b": "93000000-0000-4930-8930-000000000002",
        "person_anna": "93000000-0000-4930-8930-000000000101",
        "person_boris": "93000000-0000-4930-8930-000000000102",
        "person_deleted": "93000000-0000-4930-8930-000000000103",
        "product_alpha": "93000000-0000-4930-8930-000000001001",
        "product_beta": "93000000-0000-4930-8930-000000001002",
        "product_gamma": "93000000-0000-4930-8930-000000001003",
    }

    node_repo.collection("library").insert_many(
        [
            _node(ids["company_a"], "Company", now, name="Acme", country="RU"),
            _node(ids["company_b"], "Company", now, name="Globex", country="US"),
            _node(ids["person_anna"], "Person", now, name="Anna", level=3),
            _node(ids["person_boris"], "Person", now, name="Boris", level=2),
            _node(ids["person_deleted"], "Person", now, deleted=True, name="Ghost", level=0),
            _node(
                ids["product_alpha"],
                "Product",
                now,
                name="Alpha Product",
                sku="alpha",
                meta={
                    "category": "Books",
                    "stats": {"score": 90, "rank": 1},
                    "manufacturer": ids["company_a"],
                },
                variants=[
                    {
                        "code": "A-1",
                        "price": 10.5,
                        "inspector": ids["person_anna"],
                        "backup_inspectors": [ids["person_boris"], ids["person_deleted"]],
                        "details": {"approver": ids["person_boris"]},
                        "attributes": {"color": "red", "size": 42},
                    },
                    {
                        "code": "A-2",
                        "price": 22.0,
                        "inspector": ids["person_boris"],
                        "backup_inspectors": [ids["person_anna"]],
                        "details": {"approver": ids["person_anna"]},
                        "attributes": {"color": "blue", "size": 44},
                    },
                ],
            ),
            _node(
                ids["product_beta"],
                "Product",
                now,
                name="Beta Product",
                sku="beta",
                meta={
                    "category": "Books",
                    "stats": {"score": 72, "rank": 2},
                    "manufacturer": ids["company_b"],
                },
                variants=[
                    {
                        "code": "B-1",
                        "price": 15.0,
                        "inspector": ids["person_boris"],
                        "backup_inspectors": [ids["person_anna"]],
                        "details": {"approver": ids["person_boris"]},
                        "attributes": {"color": "green", "size": 41},
                    }
                ],
            ),
            _node(
                ids["product_gamma"],
                "Product",
                now,
                name="Gamma Product",
                sku="gamma",
                meta={
                    "category": "Games",
                    "stats": {"score": 65, "rank": 3},
                    "manufacturer": ids["company_a"],
                },
                variants=[
                    {
                        "code": "G-1",
                        "price": 35.0,
                        "inspector": ids["person_deleted"],
                        "backup_inspectors": [ids["person_anna"], ids["person_deleted"]],
                        "details": {"approver": ids["person_boris"]},
                        "attributes": {"color": "black", "size": 40},
                    }
                ],
            ),
        ]
    )

    return ids


def _company_schema() -> dict:
    return {
        "title": "Company",
        "description": "Company",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "country": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["name", "country"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _person_schema() -> dict:
    return {
        "title": "Person",
        "description": "Person",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "level": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["name", "level"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _product_schema() -> dict:
    return {
        "title": "Product",
        "description": "Product",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "sku": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "meta": {
                "type": "object",
                "additionalProperties": False,
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                "properties": {
                    "category": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
                    "stats": {
                        "type": "object",
                        "additionalProperties": False,
                        "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                        "properties": {
                            "score": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
                            "rank": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
                        },
                        "required": ["score", "rank"],
                    },
                    "manufacturer": {
                        "type": "string",
                        "format": "uuid",
                        "x-meta": {
                            "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                            "link": {"module": "library", "entities": ["Company"]},
                        },
                    },
                },
                "required": ["category", "stats", "manufacturer"],
            },
            "variants": {
                "type": "array",
                "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                    "properties": {
                        "code": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
                        "price": {"type": "number", "x-meta": {"semantic-type": "Number", "visibility-mode": "all", "write-mode": "all"}},
                        "inspector": {
                            "type": "string",
                            "format": "uuid",
                            "x-meta": {
                                "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                                "link": {"module": "library", "entities": ["Person"]},
                            },
                        },
                        "backup_inspectors": {
                            "type": "array",
                            "items": {"type": "string", "format": "uuid"},
                            "x-meta": {
                                "semantic-type": "LinkArray", "visibility-mode": "all", "write-mode": "all",
                                "link": {"module": "library", "entities": ["Person"]},
                            },
                        },
                        "details": {
                            "type": "object",
                            "additionalProperties": False,
                            "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                            "properties": {
                                "approver": {
                                    "type": "string",
                                    "format": "uuid",
                                    "x-meta": {
                                        "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                                        "link": {"module": "library", "entities": ["Person"]},
                                    },
                                }
                            },
                            "required": ["approver"],
                        },
                        "attributes": {
                            "type": "object",
                            "additionalProperties": False,
                            "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                            "properties": {
                                "color": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
                                "size": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
                            },
                            "required": ["color", "size"],
                        },
                    },
                    "required": ["code", "price", "inspector", "backup_inspectors", "details", "attributes"],
                },
            },
        },
        "required": ["name", "sku", "meta", "variants"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _node(node_id: str, entity: str, now: str, deleted: bool = False, **fields):
    return {
        "id": node_id,
        "entity": entity,
        "parent": None,
        "owner": "owner-default",
        "group": "group-default",
        "perm": {
            "owner": {"r": True, "w": True, "p": True},
            "group": {"r": True, "w": True, "p": True},
            "others": {"r": True, "w": True, "p": True},
        },
        "depth": 0,
        "ancestors": [],
        "deleted": deleted,
        "cdate": now,
        "mdate": now,
        **fields,
    }
