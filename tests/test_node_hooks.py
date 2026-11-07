from __future__ import annotations

import pytest

from sandala.core.errors import QueryValidationError
from sandala.core.services.node_hooks import NodeHookRegistry, NodeQueryHookContext


@pytest.mark.parametrize("event", ["before_query", "after_query"])
def test_query_hook_registration_rejects_entity_scope(event):
    hooks = NodeHookRegistry()

    with pytest.raises(ValueError, match="module, not entity"):
        hooks.register(event, lambda context: None, module="library", entity="Book")

    assert not hooks.has_hooks(event, module="library")


@pytest.mark.parametrize("event", ["before_query", "after_query"])
def test_query_hooks_obey_module_scope_priority_and_registration_order(event):
    hooks = NodeHookRegistry()
    calls = []
    hooks.register(event, lambda context: calls.append("later"), module="library", priority=200)
    hooks.register(event, lambda context: calls.append("global"), priority=10)
    hooks.register(event, lambda context: calls.append("first"), module="library", priority=100)
    hooks.register(event, lambda context: calls.append("second"), module="library", priority=100)
    hooks.register(event, lambda context: calls.append("other module"), module="people", priority=1)

    hooks.dispatch(NodeQueryHookContext(event=event, module="library"))

    assert calls == ["global", "first", "second", "later"]


def test_required_filters_are_snapshots_and_survive_query_replacement():
    context = NodeQueryHookContext(event="before_query", module="library", query={})
    predicate = {"allowed_groups": {"in": ["editors"]}}
    context.add_required_filter(predicate)
    predicate["allowed_groups"]["in"].append("everyone")
    snapshot = context.required_filters
    snapshot[0]["allowed_groups"]["in"].clear()
    context.query = {"filter": {}}

    assert context.required_filters == ({"allowed_groups": {"in": ["editors"]}},)


def test_later_query_hooks_see_replaced_query_and_accumulated_restrictions():
    hooks = NodeHookRegistry()
    calls = []
    context = NodeQueryHookContext(event="before_query", module="library", query={"filter": {"entity": "Book"}})

    def replace(context):
        context.query = {"filter": {"entity": "Author"}}
        context.add_required_filter({"published": True})
        context.exclude_fields("internal_notes")

    def observe(context):
        calls.append((context.query, context.required_filters, context.excluded_fields))

    hooks.register("before_query", replace, module="library", priority=10)
    hooks.register("before_query", observe, module="library", priority=20)
    hooks.dispatch(context)

    assert calls == [({"filter": {"entity": "Author"}}, ({"published": True},), ("internal_notes",))]
    assert not hasattr(context, "entities")


@pytest.mark.parametrize("predicate", [None, [], "published"])
def test_required_filter_rejects_non_object(predicate):
    context = NodeQueryHookContext(event="before_query", module="library")

    with pytest.raises(QueryValidationError, match="must be an object"):
        context.add_required_filter(predicate)


@pytest.mark.parametrize("path", [None, "", ".name", "name.", "a..b", "author.*", "$secret", "a.$secret", "a\x00b"])
def test_field_exclusions_reject_invalid_paths_without_adding_partial_restrictions(path):
    context = NodeQueryHookContext(event="before_query", module="library")

    with pytest.raises(QueryValidationError, match="field paths"):
        context.exclude_fields("valid", path)

    assert context.excluded_fields == ()


@pytest.mark.parametrize("operation", ["filter", "exclude"])
def test_query_restrictions_cannot_be_added_in_after_query(operation):
    context = NodeQueryHookContext(event="after_query", module="library", result=[])

    with pytest.raises(ValueError, match="only be added in before_query"):
        if operation == "filter":
            context.add_required_filter({"published": True})
        else:
            context.exclude_fields("secret")
