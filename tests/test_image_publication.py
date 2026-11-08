import copy
import importlib.util
from pathlib import Path

import pytest


RUN_ID = "42468206654"
SHA = "a" * 40
TAG_SHA = "b" * 40


@pytest.fixture
def source(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "prepare_image_publication.py"
    spec = importlib.util.spec_from_file_location("prepare_image_publication", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    run = {
        "id": int(RUN_ID),
        "repository": {"full_name": "sandala-project/sandala"},
        "head_repository": {"full_name": "sandala-project/sandala"},
        "path": ".github/workflows/release.yml",
        "event": "push",
        "head_branch": "v0.1.0",
        "head_sha": SHA,
        "status": "completed",
        "conclusion": "success",
    }
    artifacts = [
        {"id": 101, "name": "docker-image-linux-amd64", "expired": False},
        {"id": 102, "name": "docker-image-linux-arm64", "expired": False},
    ]
    responses = {
        f"actions/runs/{RUN_ID}": run,
        "git/ref/tags/v0.1.0": {"object": {"type": "tag", "sha": TAG_SHA}},
        f"git/tags/{TAG_SHA}": {"object": {"type": "commit", "sha": SHA}},
        f"actions/runs/{RUN_ID}/artifacts?per_page=100&page=1": {"artifacts": artifacts},
    }
    monkeypatch.setattr(script, "_github_json", lambda route: copy.deepcopy(responses[route]))
    return script, responses, run, artifacts


def test_image_publication_selects_exact_release_artifacts(source):
    script, _, _, _ = source
    assert script.prepare_publication(RUN_ID) == {
        "run_id": RUN_ID,
        "version": "0.1.0",
        "revision": SHA,
        "amd64_artifact": "101",
        "arm64_artifact": "102",
    }


def test_image_publication_accepts_lightweight_tag(source):
    script, responses, _, _ = source
    responses["git/ref/tags/v0.1.0"]["object"] = {"type": "commit", "sha": SHA}
    assert script.prepare_publication(RUN_ID)["version"] == "0.1.0"


@pytest.mark.parametrize("run_id", ["", "0", "-1", "1\nversion=9.9.9", "1; echo unsafe", "12x"])
def test_image_publication_rejects_invalid_run_id(source, run_id):
    script, _, _, _ = source
    with pytest.raises(RuntimeError, match="positive integer"):
        script.prepare_publication(run_id)


@pytest.mark.parametrize(("field", "value"), [
    ("id", 1),
    ("repository", {"full_name": "another/repository"}),
    ("head_repository", {"full_name": "fork/sandala"}),
    ("path", ".github/workflows/ci.yml"),
    ("event", "pull_request"),
    ("event", "workflow_dispatch"),
    ("event", "workflow_run"),
])
def test_image_publication_rejects_non_release_source(source, field, value):
    script, _, run, _ = source
    run[field] = value
    with pytest.raises(RuntimeError, match="tag-triggered Release build"):
        script.prepare_publication(RUN_ID)


@pytest.mark.parametrize(("status", "conclusion"), [
    ("in_progress", None), ("queued", None), ("completed", "failure"),
    ("completed", "cancelled"), ("completed", "skipped"),
])
def test_image_publication_requires_successful_historical_run(source, status, conclusion):
    script, _, run, _ = source
    run.update(status=status, conclusion=conclusion)
    with pytest.raises(RuntimeError, match="completed successfully"):
        script.prepare_publication(RUN_ID)


def test_image_publication_allows_only_current_release_to_still_be_running(source):
    script, _, run, _ = source
    run.update(status="in_progress", conclusion=None)
    assert script.prepare_publication(RUN_ID, current_run_id=RUN_ID)["version"] == "0.1.0"
    with pytest.raises(RuntimeError, match="completed successfully"):
        script.prepare_publication(RUN_ID, current_run_id="1")


@pytest.mark.parametrize("tag", ["main", "v0.1.0-extra", "v00.1.0", "0.1.0", None])
def test_image_publication_requires_normal_release_tag(source, tag):
    script, _, run, _ = source
    run["head_branch"] = tag
    with pytest.raises(RuntimeError, match="release tag"):
        script.prepare_publication(RUN_ID)


def test_image_publication_rejects_moved_tag(source):
    script, responses, _, _ = source
    responses[f"git/tags/{TAG_SHA}"]["object"]["sha"] = "c" * 40
    with pytest.raises(RuntimeError, match="no longer points"):
        script.prepare_publication(RUN_ID)


def test_image_publication_rejects_tag_chain_without_commit(source):
    script, responses, _, _ = source
    responses[f"git/tags/{TAG_SHA}"]["object"] = {"type": "tag", "sha": TAG_SHA}
    with pytest.raises(RuntimeError, match="no longer points"):
        script.prepare_publication(RUN_ID)


@pytest.mark.parametrize("problem", ["missing", "expired", "duplicate", "invalid_id"])
def test_image_publication_requires_both_unexpired_unique_artifacts(source, problem):
    script, _, _, artifacts = source
    if problem == "missing":
        artifacts.pop()
    elif problem == "expired":
        artifacts[1]["expired"] = True
    elif problem == "duplicate":
        artifacts.append(copy.deepcopy(artifacts[1]))
    else:
        artifacts[1]["id"] = "102\nversion=9.9.9"
    with pytest.raises(RuntimeError, match="artifact"):
        script.prepare_publication(RUN_ID)


def test_image_publication_reads_all_artifact_pages(source):
    script, responses, _, artifacts = source
    responses[f"actions/runs/{RUN_ID}/artifacts?per_page=100&page=1"]["artifacts"] = [
        {"id": i + 1000, "name": f"unrelated-{i}", "expired": False} for i in range(100)
    ]
    responses[f"actions/runs/{RUN_ID}/artifacts?per_page=100&page=2"] = {"artifacts": artifacts}
    assert script.prepare_publication(RUN_ID)["arm64_artifact"] == "102"
