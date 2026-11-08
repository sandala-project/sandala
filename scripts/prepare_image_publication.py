from __future__ import annotations

import argparse
import json
import os
import re
from urllib.request import Request, urlopen


REPOSITORY = "sandala-project/sandala"
RELEASE_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def _github_json(path: str):
    request = Request(
        f"https://api.github.com/repos/{REPOSITORY}/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def prepare_publication(run_id: str, *, current_run_id: str | None = None) -> dict[str, str]:
    if re.fullmatch(r"[1-9][0-9]*", run_id) is None:
        raise RuntimeError("The source run ID must be a positive integer")

    run = _github_json(f"actions/runs/{run_id}")
    if (
        run["id"] != int(run_id)
        or run["repository"]["full_name"] != REPOSITORY
        or run["head_repository"]["full_name"] != REPOSITORY
        or run["path"] != ".github/workflows/release.yml"
        or run["event"] != "push"
    ):
        raise RuntimeError("Image artifacts must come from this repository's tag-triggered Release build")

    # Only the current tag-triggered workflow may still be running: its build
    # and documentation jobs are explicit prerequisites in release.yml.
    if run_id == current_run_id:
        if run["status"] != "in_progress":
            raise RuntimeError("Expected the current release workflow to be in progress")
    elif run["status"] != "completed" or run["conclusion"] != "success":
        raise RuntimeError("The source release workflow must have completed successfully")

    tag = run["head_branch"]
    if not isinstance(tag, str) or RELEASE_TAG.fullmatch(tag) is None:
        raise RuntimeError("Expected a release tag in vMAJOR.MINOR.PATCH format")
    sha = run["head_sha"]
    if not isinstance(sha, str) or re.fullmatch(r"[a-f0-9]{40}", sha) is None:
        raise RuntimeError("Expected a full Git commit SHA")

    target = _github_json(f"git/ref/tags/{tag}")["object"]
    for _ in range(8):
        if target["type"] != "tag":
            break
        target = _github_json(f"git/tags/{target['sha']}")["object"]
    if target["type"] != "commit" or target["sha"] != sha:
        raise RuntimeError("The release tag no longer points to the source run's commit")

    artifacts = []
    page = 1
    while True:
        batch = _github_json(f"actions/runs/{run_id}/artifacts?per_page=100&page={page}")["artifacts"]
        artifacts.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    outputs = {"run_id": run_id, "version": tag[1:], "revision": sha}
    for arch in ("amd64", "arm64"):
        matches = [artifact for artifact in artifacts if artifact["name"] == f"docker-image-linux-{arch}"]
        if len(matches) != 1 or matches[0]["expired"]:
            raise RuntimeError(f"Expected one unexpired Docker artifact for linux/{arch}")
        artifact_id = matches[0]["id"]
        if type(artifact_id) is not int or artifact_id <= 0:
            raise RuntimeError("Expected a positive artifact ID")
        outputs[f"{arch}_artifact"] = str(artifact_id)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the release run supplying Docker image artifacts.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--current-run-id", help="Allow this still-running tag release after its build jobs pass")
    args = parser.parse_args()
    try:
        outputs = prepare_publication(args.run_id, current_run_id=args.current_run_id)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    for name, value in outputs.items():
        print(f"{name}={value}")


if __name__ == "__main__":
    main()
