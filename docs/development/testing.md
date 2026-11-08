# Testing

Run Python commands from the repository root using the project virtual
environment. For a fresh checkout:

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev,s3]'
```

The `dev` extra supplies pytest, MongoDB Testcontainers, the Python
distribution builder, and Twine for package validation. The `s3` extra supplies
`boto3` for S3 tests; it is not needed for the non-integration suite.

## GitHub Actions

The repository has three workflows. Build and test jobs have read-only
repository permissions. GitHub Pages deployment uses `pages: write` and
`id-token: write`; PyPI publication uses only `id-token: write`. Docker
publication uses `actions: read` to download verified artifacts and
`packages: write` to push them to GHCR.

| Workflow | Runs on | Result |
| --- | --- | --- |
| **CI** | Pushes to `main`, pull requests, manual runs, and calls from Release build; documentation-only changes use the documentation workflow instead. | Unit tests on Python 3.11 and 3.14, MongoDB/S3 integration tests, verified Python distributions, and Docker builds for `linux/amd64` and `linux/arm64`. |
| **Release build** | Tags matching `v*`, or a manual run on a selected ref. | CI and documentation checks, plus downloadable Docker images for both architectures. Tag pushes in `sandala-project/sandala` also publish Python distributions to PyPI and a multi-platform Docker image to GHCR, subject to their environment approvals. A separate manual mode publishes Docker artifacts from an earlier successful tag release. |
| **Documentation build** | Documentation, Zensical configuration, or documentation-workflow changes on `main` or in a pull request; manual runs and calls from Release build. | A clean, strict Zensical build saved as the `documentation-site` artifact; eligible runs on `main` also deploy to GitHub Pages. |

Release tags use `vMAJOR.MINOR.PATCH` and match the versions in `pyproject.toml`,
`admin-ui/package.json`, and both root version entries in the npm lock file.
Manual branch runs check version consistency without requiring a tag.
Integration runs fail if tests are skipped instead of executed.

In `sandala-project/sandala`, documentation pushes to `main` deploy the site to
[GitHub Pages](https://sandala-project.github.io/sandala/). A manual Documentation
build on `main` also deploys unless its `deploy` option is disabled. Pull requests,
other branches, and calls from Release build only build the documentation.
In the repository's **Settings → Pages**, the publishing source is **GitHub Actions**.
Pages deployment uses the `github-pages` environment and GitHub's short-lived
token; no publishing secret is required. Release build grants the reusable
documentation workflow the permissions it declares, but passes `deploy: false`.
Its build job still has only `contents: read` permission.

PyPI publication waits for all CI and documentation checks, including both
Docker builds. It downloads the already verified wheel and sdist, checks their
SHA-256 checksums, and publishes without rebuilding them. CI runs
`python -m twine check --strict dist/*.whl dist/*.tar.gz` before saving the
distribution artifact. The publishing job uses
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/) and
the `pypi` GitHub environment, not a stored API token. Configure the matching
Trusted Publisher on PyPI and required reviewers for that GitHub environment
before pushing a release tag. Manual Release build runs never publish to PyPI,
even when a tag is selected.

Docker publication also waits for CI and documentation checks. It uses the
`ghcr` environment and the workflow's short-lived `GITHUB_TOKEN`, not a stored
registry password. Configure required reviewers and disable administrator
bypass on this environment; allow `v*` tags and the `main` branch. The publishing
job downloads the exact Docker artifacts, checks their platforms without
executing them, and pushes `ghcr.io/sandala-project/sandala:VERSION-amd64` and
`:VERSION-arm64`. It combines their digests into the multi-platform `:VERSION`
tag and, for tag-triggered releases, updates `:latest`. The image index includes
source, license, version, and source-commit annotations. Publication does not
rebuild the images or run project code in the job with registry write access.

To publish only Docker images from an existing release, manually run **Release
build** from `main` and set `image_run_id` to that successful tag-triggered
Release build's run ID. This mode skips tests and builds because it reuses their
verified artifacts; it does not publish Python packages. Validation checks the
source repository, workflow, event, successful completion, release-tag syntax,
current tag-to-commit mapping, and availability of both image artifacts before
requesting the `ghcr` approval. Ordinary CI runs, pull requests, manual builds,
and expired artifacts are not accepted as publication sources. Leave
`image_run_id` empty for the usual verification-only manual run.

The Docker-only mode leaves `:latest` unchanged unless `update_latest` is
enabled. Use that option when promoting a release, not when backfilling an older
version. After the first GHCR publication, change the package's visibility to
**Public** in its package settings, then verify an unauthenticated pull; a new
GHCR package is private by default. See GitHub's
[Container registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

The workflows do not create GitHub Releases.
Download artifacts from the workflow run in the Actions tab.
Python distributions include `SHA256SUMS`; saved Docker
images can be loaded with `docker load --input <downloaded-image>.tar.gz`.
Serve the extracted documentation site with a local HTTP server to preview it.
Test reports, distributions, and documentation artifacts are retained for seven
days; Docker image archives are retained for one day to limit storage usage.

## Run the backend tests

```bash
# Fast suite: no external services
./.venv/bin/python -m pytest -m 'not integration'

# Integration suite: Docker must be running
./.venv/bin/python -m pytest -m integration

# Both suites, with skip reasons
./.venv/bin/python -m pytest -ra
```

To investigate one failure or verify a focused change, select a file or use
`-k` to match test names:

```bash
./.venv/bin/python -m pytest tests/test_query_builder.py
./.venv/bin/python -m pytest tests/test_query_builder.py -k module_schemas
```

Tests directly under `tests/` use fakes, stubs, and Flask's test client to
exercise services and transport behavior without a running database.
Tests under `tests/integration/` execute against real MongoDB through
Testcontainers. The helpers currently start `mongo:7.0`; S3 scenarios also
start SeaweedFS in `mini` mode and create a test bucket. The SeaweedFS image
is pinned by version and multi-platform digest in `tests/integration/helpers.py`.
Docker needs access to the container images. No separately running Sandala
server or local MongoDB is required.

The integration helpers create fresh containers and build services with test
configuration. Local asset scenarios use temporary filesystem directories.
Keep this isolation when adding tests; do not point fixtures at a development
or production database.

Missing Testcontainers causes integration tests to be **skipped**, and missing
`boto3` skips S3 scenarios. Check the pytest summary and skip reasons before
treating a run as complete. An installed Testcontainers package with an
unavailable Docker daemon is not a successful integration run.

## Add coverage at the right boundary

- Use unit tests for validation, service decisions, hook dispatch, and pipeline
  construction. Use API tests for request parsing, status codes, cookies, and
  structured error responses.
- Use MongoDB integration tests when correctness depends on aggregation,
  indexes, or persisted state. A pipeline-shape assertion alone does not prove
  that MongoDB returns the intended result.
- For query and permission changes, assert both allowed results and the
  absence of hidden nodes, fields, or temporary data. Include relevant nested
  paths and actor roles; see the coverage rules in
  [Query builder](query-builder.md#extending-query-behavior-safely).
- Reuse integration helpers and datasets, but keep setup valid for the scenario
  being tested. A schema replacement validates existing nodes too; incompatible
  seed data can fail before the behavior under test is reached.

Start with the affected tests, then run the non-integration suite and relevant
integration scenarios. Changes to shared query, ACL, or persistence behavior
warrant the full backend suite.
