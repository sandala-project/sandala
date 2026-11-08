# CI and releases

Sandala's GitHub Actions workflows check changes, build distributions, and
publish releases and documentation. Their definitions are in
`.github/workflows/`. For local test commands and coverage guidelines, see
[Testing](testing.md).

## Workflows

| Workflow | Runs on | Result |
| --- | --- | --- |
| **CI** | Pushes to `main` and pull requests, with the path exclusions described below; manual runs and calls from Release build. | Unit tests on Python 3.11 and 3.14, MongoDB/S3 integration tests, verified Python distributions, and Docker builds for `linux/amd64` and `linux/arm64`. |
| **Release build** | Tags matching `v*`, or a manual run on a selected ref. | CI and documentation checks, plus downloadable Docker images for both architectures. Tag pushes in `sandala-project/sandala` also publish Python distributions to PyPI and a multi-platform Docker image to GHCR, subject to their environment approvals. |
| **Documentation build** | Documentation, Zensical configuration, or documentation-workflow changes on `main` or in a pull request; manual runs and calls from Release build. | A clean, strict Zensical build saved as the `documentation-site` artifact; eligible runs on `main` also deploy to GitHub Pages. |

Automatic CI runs are skipped when all changed files are under `docs/` or are
`zensical.toml`, `README.md`, or `AGENTS.md`. Changes to dependencies, tests,
build scripts, Docker configuration, or workflows still trigger CI. These path
exclusions do not apply to manual runs or calls from Release build. The
documentation workflow has its own triggers; README-only and AGENTS-only
changes do not rebuild the site.

CI rejects integration runs with skipped tests rather than treating them as
successful checks.

## Versions and release triggers

Release tags use `vMAJOR.MINOR.PATCH` and match the versions in `pyproject.toml`,
`admin-ui/package.json`, and both root version entries in the npm lock file.
Manual branch runs check version consistency without requiring a tag.

Both publication jobs wait for all CI and documentation checks, including both
Docker builds. They use separate environment approvals and do not depend on
each other's publication result. Manual Release build runs perform checks
only: they never publish Python packages or Docker images, even when a tag is
selected.

The workflows do not create GitHub Releases.

## Python package publication

CI runs `python -m twine check --strict dist/*.whl dist/*.tar.gz` before saving
the distribution artifact. Publication downloads the already verified wheel
and sdist from the same workflow run, checks their SHA-256 checksums, and
publishes without rebuilding them.

The publishing job uses
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
and the `pypi` GitHub environment, not a stored API token. Configure the matching
Trusted Publisher on PyPI and required reviewers for that GitHub environment
before pushing a release tag.

## Docker image publication

Docker publication uses the `ghcr` environment and the workflow's short-lived
`GITHUB_TOKEN`, not a stored registry password. Configure required reviewers
and disable administrator bypass on this environment, and allow `v*` tags.

The publishing job receives the validated version from CI and downloads both
Docker artifacts from the same workflow run. It checks their platforms without
executing them, and pushes `ghcr.io/sandala-project/sandala:VERSION-amd64` and
`:VERSION-arm64`. It combines their digests into the multi-platform `:VERSION`
tag and updates `:latest`.

ORAS publishes an explicit OCI index so that annotations are preserved even
when the architecture-specific manifests use the Docker media type.
Publication reads the index back and checks it against the expected platforms,
digests, and source, description, license, version, and source-commit
annotations. It does not rebuild the images or run project code in the job
with registry write access.

## Documentation publication

In `sandala-project/sandala`, documentation pushes to `main` deploy the site to
[GitHub Pages](https://sandala-project.github.io/sandala/). A manual Documentation
build on `main` also deploys unless its `deploy` option is disabled. Pull requests,
other branches, and calls from Release build only build the documentation.

In the repository's **Settings → Pages**, the publishing source is **GitHub
Actions**. Pages deployment uses the `github-pages` environment and GitHub's
short-lived token; no publishing secret is required. Release build grants the
reusable documentation workflow the permissions it declares, but passes
`deploy: false`. Its build job still has only `contents: read` permission.

## Permissions

Build and test jobs have read-only repository permissions. GitHub Pages
deployment uses `pages: write` and `id-token: write`; PyPI publication uses only
`id-token: write`. Docker publication uses only `packages: write` to push the
verified images to GHCR.

## Build artifacts

Download artifacts from the workflow run in the Actions tab. Python
distributions include `SHA256SUMS`; saved Docker images can be loaded with
`docker load --input <downloaded-image>.tar.gz`. Serve the extracted
documentation site with a local HTTP server to preview it.

Test reports, distributions, and documentation artifacts are retained for
seven days; Docker image archives are retained for one day to limit storage
usage.
