# Installation

Sandala requires MongoDB. Python 3.11 or later is required when installing the
package directly or working from a source checkout; it is not required on the
host that runs the Docker image. The packaged application includes a production
build of the Sandala admin UI.

Choose one of these paths:

- **Docker** is the simplest way to run the ready-made application. The image
  runs Gunicorn and includes support for both local and S3-compatible asset
  storage.
- **The Python package** is appropriate when Sandala is embedded in a Python
  application or when a deployment has its own process-management setup.
- **A source checkout** is for developing Sandala itself or its administrative
  interface.

## Run with Docker

Build the image from a Sandala source checkout:

```bash
docker build --tag sandala:local .
```

The following commands create an isolated local MongoDB and start Sandala on
port 3000. The named volumes preserve MongoDB data and locally stored assets
when the containers are recreated.

```bash
docker network create sandala-local

docker run --detach \
  --name sandala-mongo \
  --network sandala-local \
  --volume sandala-mongo:/data/db \
  mongo:7

docker run --rm \
  --name sandala \
  --network sandala-local \
  --publish 3000:3000 \
  --volume sandala-assets:/var/lib/sandala/assets \
  --env SANDALA_MONGO_URI='mongodb://sandala-mongo:27017' \
  --env SANDALA_MONGO_DB='sandala' \
  --env SANDALA_ROOT_PASSWORD='' \
  sandala:local
```

Open `http://localhost:3000/admin/` and sign in as `root` with the password
chosen for `SANDALA_ROOT_PASSWORD`. The REST API is available below
`http://localhost:3000/api/v1/`.

To connect the container to MongoDB running on the host instead, use
`host.docker.internal` on Docker Desktop:

```bash
docker run --rm \
  --name sandala \
  --publish 3000:3000 \
  --volume sandala-assets:/var/lib/sandala/assets \
  --env SANDALA_MONGO_URI='mongodb://host.docker.internal:27017' \
  --env SANDALA_MONGO_DB='sandala' \
  --env SANDALA_ROOT_PASSWORD='' \
  sandala:local
```

On Linux, add `--add-host=host.docker.internal:host-gateway` when the Docker
engine supports the `host-gateway` mapping. Alternatively, place MongoDB and
Sandala on the same user-defined Docker network as in the first example.

> **Keep persistent storage.** Without the `sandala-assets` volume, local asset
> binaries disappear when the container is removed. Without persistent MongoDB
> storage, all Sandala metadata and nodes disappear as well.

## First bootstrap

When Sandala connects to an empty database, it creates the built-in `users`
module, the default group, and a root superuser. The bootstrap requires a
non-empty `SANDALA_ROOT_PASSWORD` that meets the password policy. The default
root username is `root`; set `SANDALA_ROOT_USERNAME` before the first start to
choose another name.

Every command on this page deliberately sets `SANDALA_ROOT_PASSWORD` to an
empty, invalid value. Replace it with a unique secret that meets the password
policy before starting against an empty database. Do not use a documented or
otherwise shared password for a root account.

Bootstrap never overwrites an existing root user or default group. If either is
missing, Sandala uses the relevant bootstrap settings to create it. The password
and username policy settings are used when Sandala first creates the
`users/user` schema; changing them later does not modify that stored schema.

## Use the Python package

For MongoDB and local filesystem asset storage:

```bash
python -m pip install sandala
```

For S3-compatible asset storage, install the optional dependency group:

```bash
python -m pip install 'sandala[s3]'
```

Set the MongoDB connection settings and the initial root password, then run the
built-in development server:

```bash
export SANDALA_MONGO_URI='mongodb://localhost:27017'
export SANDALA_MONGO_DB='sandala'
export SANDALA_ROOT_PASSWORD=''

python -m sandala.api
```

This command is for local development and exploration. Use the Docker image or
your own WSGI process manager for [deployment](deployment.md).

## Configure S3-compatible asset storage

The Docker image already contains the S3 dependency. The following command
starts Sandala with the MongoDB container from the Docker example and an
S3-compatible backend. Replace the placeholder credentials with values supplied
through your secret-management system:

```bash
docker run --rm \
  --name sandala \
  --network sandala-local \
  --publish 3000:3000 \
  --env SANDALA_MONGO_URI='mongodb://sandala-mongo:27017' \
  --env SANDALA_MONGO_DB='sandala' \
  --env SANDALA_ROOT_PASSWORD='' \
  --env SANDALA_ASSET_STORAGE_BACKEND=s3 \
  --env SANDALA_ASSET_S3_BUCKET='sandala-assets' \
  --env SANDALA_ASSET_S3_ENDPOINT='https://s3.example.com' \
  --env SANDALA_ASSET_S3_REGION='us-east-1' \
  --env SANDALA_ASSET_S3_ACCESS_KEY='…' \
  --env SANDALA_ASSET_S3_SECRET_KEY='…' \
  sandala:local
```

For Amazon S3, an endpoint URL is normally unnecessary. `SANDALA_ASSET_PUBLIC_BASE_URL`
can point returned asset URLs at a public bucket domain or CDN. See
[Asset storage configuration](../reference/configuration.md#asset-storage) for
the complete set of storage settings, including addressing style and local
filesystem options.

## Develop from a source checkout

Create a virtual environment with the project-supported interpreter and install
the package in editable mode with its development tools:

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
```

The `dev` extra includes the Python distribution builder, Twine, pytest, and
MongoDB Testcontainers. For the full backend test setup, including S3 support, see
[Testing](../development/testing.md).

For admin UI development, install its independent Node.js
dependencies and run the Vite development server:

```bash
cd admin-ui
npm ci
npm run dev
```

Start the backend in another terminal. The UI development server runs on port
3001 and proxies API requests to the backend on port 3000:

```bash
SANDALA_ROOT_PASSWORD='' \
  ./.venv/bin/python -m sandala.api
```

### Build a distribution

With Node.js and npm available, run from the repository root:

```bash
./.venv/bin/python scripts/build_distribution.py
./.venv/bin/python scripts/verify_distribution.py
```

The first command installs the locked admin UI dependencies, builds the bundled
UI, and creates a wheel and sdist in `dist/`. The second installs the wheel in a
temporary environment and checks that it serves the bundled admin UI.

### Preview the documentation

Install the documentation tools separately and start the local site:

```bash
./.venv/bin/python -m pip install -r docs/requirements.txt
./.venv/bin/python -m zensical serve
```
