# Testing

Run Python commands from the repository root using Python 3.11 or later.
For a fresh checkout, install the test dependencies:

```bash
python -m pip install -e '.[dev,s3]'
```

The `dev` extra supplies pytest, MongoDB Testcontainers, the Python
distribution builder, and Twine for package validation. The `s3` extra supplies
`boto3` for S3 tests; it is not needed for the non-integration suite.

Automated checks, build artifacts, publishing permissions, and release
procedures are described in [CI and releases](ci-and-releases.md).

## Run the backend tests

```bash
# Fast suite: no external services
python -m pytest -m 'not integration'

# Integration suite: Docker must be running
python -m pytest -m integration

# Both suites, with skip reasons
python -m pytest -ra
```

To investigate one failure or verify a focused change, select a file or use
`-k` to match test names:

```bash
python -m pytest tests/test_query_builder.py
python -m pytest tests/test_query_builder.py -k module_schemas
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
