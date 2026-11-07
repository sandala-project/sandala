# Deployment

This page covers running Sandala beyond local development. Start with
[Installation](installation.md) for the image build, package installation,
and a local MongoDB setup. The complete setting list is in
[Configuration](../reference/configuration.md).

A straightforward deployment puts a reverse proxy with HTTPS in front of
Sandala, keeps MongoDB on a private network, and uses persistent storage for
assets. The proxy can expose the bundled admin UI, REST API, and asset delivery
on the same origin without changing their default paths.

## Run the application

### Docker

The repository image includes Gunicorn, the built admin UI, and S3 support.
Keep configuration outside the image. For example, a private
`/etc/sandala/sandala.env` file could contain:

```dotenv
SANDALA_MONGO_URI=mongodb://sandala-mongo:27017
SANDALA_MONGO_DB=sandala
SANDALA_ROOT_PASSWORD=
SANDALA_ASSET_STORAGE_BACKEND=local_fs
```

The empty root password is deliberately invalid for first bootstrap. Replace
it with a unique secret that meets the password policy before the first start;
do not commit the file. You can remove the password from the startup environment
once bootstrap has succeeded. Subsequent starts do not reset the stored
password. See [First bootstrap](installation.md#first-bootstrap).

With the image and Docker network from Installation, start Sandala behind a
proxy running on the host:

```bash
docker run --detach \
  --name sandala \
  --restart unless-stopped \
  --network sandala-local \
  --publish 127.0.0.1:3000:3000 \
  --env-file /etc/sandala/sandala.env \
  --volume sandala-assets:/var/lib/sandala/assets \
  sandala:local
```

The loopback-only port is for the host's proxy, not direct public access. If
the proxy is another container, connect it to the same private Docker network
and use `sandala:3000` as its upstream instead; publishing a host port is then
unnecessary.

The image runs as a non-root user. Named volumes retain local assets across
container replacement. With a bind-mounted directory, arrange write permission
for the container user. For S3, use the settings from
[Installation](installation.md#configure-s3-compatible-asset-storage) instead
of relying on the local asset volume.

### Python package with a WSGI server

`python -m sandala.api` uses Flask's development server. For a managed Linux
deployment, install a WSGI server such as Gunicorn alongside Sandala:

```bash
python -m pip install sandala gunicorn
```

Use `sandala[s3]` instead of `sandala` when needed. Supply the `SANDALA_*`
environment through your process manager, then initialize the database before
starting multiple workers:

```bash
python -c 'from sandala.bootstrap import build_container; build_container()' && \
  gunicorn --bind 127.0.0.1:3000 \
    --workers 2 --threads 4 \
    --access-logfile - --error-logfile - \
    'sandala.api.app:create_app()'
```

This is also the initialization sequence used by the Docker image. Create the
application in each worker rather than using Gunicorn's `--preload` option,
so database clients are constructed in their worker process. Configure your
process manager to restart failed processes and retain logs.

The worker and thread counts are starting values, not a capacity guarantee.
Tune them against actual queries, uploads, hook work, memory use, and MongoDB
connections. In the image, use `GUNICORN_WORKERS` and `GUNICORN_THREADS`; see
[Docker-only process settings](../reference/configuration.md#docker-only-process-settings).
For other server settings, use the
[Gunicorn configuration reference](https://gunicorn.org/reference/settings/).

## HTTPS and reverse proxy

Expose the following paths without removing their prefixes:

| Public path | Purpose |
| --- | --- |
| `/api/v1/` | REST API, authentication, and uploads. |
| `/admin/` | Bundled admin UI, including deep links under `/admin/_app/`. |
| `/assets/` | Public binary asset delivery, unless handled by external storage or a CDN. |

For example, inside an nginx server already configured for your domain and
TLS certificate, this location forwards all paths to the host-local listener:

```nginx
location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

See nginx's [proxy module reference](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)
for upstream and path-rewriting behavior. Configure Gunicorn's trusted proxy
addresses for your actual topology when using forwarded scheme headers; only
the trusted proxy should be able to supply them.

Keep the session cookie's `Secure` and `HttpOnly` settings enabled for HTTPS.
TLS may terminate at the proxy; the browser-facing connection is what matters
for the secure cookie. Same-origin UI and API hosting works with the default
cookie domain, path, and SameSite settings. See
[Sessions and cookies](../reference/configuration.md#sessions-and-cookies).

Keep authenticated API responses out of shared caches. Set appropriate upload
body-size limits, request timeouts, and rate limits at the proxy for your
workload, including image processing and login requests.

## Persistent data and multiple instances

Back up both the MongoDB database and the asset binaries. MongoDB contains
schemas, nodes, identities, sessions, PAT records, and asset metadata; it is
not a backup of the files themselves. For local storage, preserve the configured
asset root. For S3, preserve the bucket and object keys. Test restoration of
both parts together.

Keep MongoDB reachable only by authorized services and configure its
credentials and transport security through `SANDALA_MONGO_URI`. Sandala creates
collections and indexes during initialization and module creation, so the
database account needs the corresponding permissions as well as data access.

Before starting several replicas against an empty database, complete the
initial bootstrap with one instance. The Docker startup step serializes
initialization before that container's workers; it is not a lock across
containers.

All instances need the same database, compatible configuration, and the same
integration code. With `local_fs`, they also need access to the same asset
files; separate per-container volumes do not provide this. A shared filesystem
or S3-compatible storage can provide a common asset store.

Multiple workers do not make multi-step writes transactional. Concurrent edits
can overwrite one another, and subtree operations are not all-or-nothing
transactions. Integrations that require stronger coordination need to provide
it; the implementation boundaries are described in
[Storage](../development/storage.md#consistency-boundaries).

## Asset delivery

The default `/assets/` route can serve files from either backend, including a
private S3 bucket. A public bucket or CDN is optional. Upload permission does
not make a stored file private: Sandala's delivery route does not apply node
ACL. Do not use it for confidential files.

Use `SANDALA_ASSET_PUBLIC_BASE_URL` when descriptors should point at an external
delivery origin or path prefix. Configure that origin to serve the resulting
storage-key paths. This setting does not publish a bucket, move files, or
rewrite URLs already saved in nodes. Changing the storage backend likewise
does not migrate existing binaries. URL construction examples are in
[Storage keys and descriptor URLs](../reference/rest-api/assets.md#storage-keys-and-descriptor-urls).

## Deploy integration hooks

The application process must be able to import every configured hook module.
Install your integration package into a derived image when it has additional
dependencies. For Python-only code that uses the image's existing dependencies,
you can mount a directory instead. For example, given
`./integration/my_project/sandala_hooks.py`, add these options to the Docker
command above:

```bash
--mount type=bind,source="$(pwd)/integration",target=/opt/integration,readonly \
--env PYTHONPATH=/opt/integration \
--env SANDALA_HOOK_MODULES=my_project.sandala_hooks
```

Place the options before the image name. The module provides
`register_hooks(app, container)` as described in
[Writing hooks](../guides/writing-hooks.md#register-a-hook-module-for-the-rest-application).
Registration happens in each application worker. Keep registration free of
one-time data mutations, and keep hook code safe for concurrent requests.
Restart the workers after changing code or environment; mounting a file does
not enable automatic reload.

## Host the admin UI separately

Bundled hosting at `/admin/` needs no frontend configuration. To supply another
build through Sandala, set `SANDALA_ADMIN_UI_DIST` to a directory containing the
complete production build, including `index.html`, `config.js`, and `static/`.
This still serves it at `/admin/`.

Alternatively, serve that build from your own static host, for example at
`/control/`. The host serves `index.html` for `/control/` and routes below
`/control/_app/`, while serving actual files normally. Do not use `/_app/` as
part of the mount point itself. The UI detects its mount point; no rebuild is
needed merely to change it.

Edit the build's `config.js` to change the API address at deployment time:

```javascript
window.__SANDALA_RUNTIME_CONFIG__ = {
  ...(window.__SANDALA_RUNTIME_CONFIG__ ?? {}),
  apiBaseUrl: "/api/v1",
};
```

The API address can be a root-relative path or an absolute HTTP(S) URL. Prefer
a same-origin API proxy. For a different API origin, configure credentialed
CORS and the appropriate cookie policy in your hosting/application setup;
Sandala does not enable CORS automatically. Asset descriptor URLs are used
as returned, not rebased against `apiBaseUrl`, so their origin must also be
reachable from the UI.

Revalidate `index.html`, `config.js`, and `static/manifest.json` rather than
caching them as immutable files. Hash-named JS and CSS files can be cached
long-term. Deploy matching HTML, manifest, and static files together.

## Verify a deployment

- Open the admin UI over HTTPS, sign in, and reload a deep link.
- Check a node read and write with the intended non-superuser permissions.
- Upload an asset and open its returned URL from the client-facing network.
- Verify that expected hooks run, and inspect startup and request logs.
- Replace or restart the application container and confirm that data and
  uploaded files remain available.
