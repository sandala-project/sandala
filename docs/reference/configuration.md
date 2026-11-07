# Configuration

Sandala builds one configuration dictionary before it creates repositories and
services. The same keys work for the packaged REST application and for direct
Python use through `build_container()` or `create_app()`.

## Configuration precedence

Values are merged in this order, with later sources taking precedence:

1. Sandala defaults;
2. environment variables named `SANDALA_<KEY>`;
3. an explicit Python `config` dictionary passed to `build_container(config)`
   or `create_app(config)`.

For example, an explicit `{"MONGO_DB": "test"}` overrides both
`SANDALA_MONGO_DB` and the default `sandala` database name.

Only the environment variables listed on this page are read. Unknown
`SANDALA_*` variables are ignored.

## Environment value formats

Integer settings must contain a base-10 integer. Boolean settings accept
`1`, `true`, `yes`, or `on` for true, and `0`, `false`, `no`, or `off` for
false; matching is case-insensitive. All other environment settings are read
as strings.

## Network and MongoDB

| Python key | Environment variable | Default | Meaning |
| --- | --- | --- | --- |
| `HOST` | `SANDALA_HOST` | `0.0.0.0` | Bind address used by `python -m sandala.api`. |
| `PORT` | `SANDALA_PORT` | `3000` | Bind port used by `python -m sandala.api`. |
| `MONGO_URI` | `SANDALA_MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection URI. |
| `MONGO_DB` | `SANDALA_MONGO_DB` | `sandala` | MongoDB database name. |

`HOST` and `PORT` configure only Sandala's built-in development server. A WSGI
server such as the one in the Docker image controls its own listener.

## Sessions and cookies

| Python key | Environment variable | Default | Meaning |
| --- | --- | --- | --- |
| `AUTH_SESSION_RENEWAL_ENABLED` | `SANDALA_AUTH_SESSION_RENEWAL_ENABLED` | `false` | Enables renewal of an active session near its expiry. |
| `AUTH_SESSION_IDLE_TTL_SECONDS` | `SANDALA_AUTH_SESSION_IDLE_TTL_SECONDS` | `1209600` | Session idle lifetime in seconds (14 days). |
| `AUTH_SESSION_ABSOLUTE_TTL_SECONDS` | `SANDALA_AUTH_SESSION_ABSOLUTE_TTL_SECONDS` | `1209600` | Maximum session lifetime in seconds, regardless of renewal. |
| `AUTH_SESSION_RENEWAL_WINDOW_SECONDS` | `SANDALA_AUTH_SESSION_RENEWAL_WINDOW_SECONDS` | `1800` | Remaining lifetime that makes an active session eligible for renewal. |
| `AUTH_SESSION_COOKIE_NAME` | `SANDALA_AUTH_SESSION_COOKIE_NAME` | `sandala_session` | Auth-session cookie name. |
| `AUTH_SESSION_COOKIE_DOMAIN` | `SANDALA_AUTH_SESSION_COOKIE_DOMAIN` | unset | Cookie `Domain` attribute. |
| `AUTH_SESSION_COOKIE_PATH` | `SANDALA_AUTH_SESSION_COOKIE_PATH` | `/` | Cookie `Path` attribute. |
| `AUTH_SESSION_COOKIE_SECURE` | `SANDALA_AUTH_SESSION_COOKIE_SECURE` | `true` | Sets the cookie `Secure` attribute. |
| `AUTH_SESSION_COOKIE_HTTPONLY` | `SANDALA_AUTH_SESSION_COOKIE_HTTPONLY` | `true` | Sets the cookie `HttpOnly` attribute. |
| `AUTH_SESSION_COOKIE_SAMESITE` | `SANDALA_AUTH_SESSION_COOKIE_SAMESITE` | `Lax` | Cookie `SameSite` attribute. |
| `AUTH_PAT_DEFAULT_TTL_SECONDS` | `SANDALA_AUTH_PAT_DEFAULT_TTL_SECONDS` | `1209600` | Default lifetime for a newly created personal access token, in seconds. |

## Users bootstrap and password policy

| Python key | Environment variable | Default | Meaning |
| --- | --- | --- | --- |
| `ROOT_USERNAME` | `SANDALA_ROOT_USERNAME` | `root` | Bootstrap root username. It is normalized to lowercase and validated by the users schema. |
| `ROOT_PASSWORD` | `SANDALA_ROOT_PASSWORD` | empty string | Password used when bootstrap creates a missing root user. It must be non-empty and meet the password schema. |
| `DEFAULT_GROUP_GROUPNAME` | `SANDALA_DEFAULT_GROUP_GROUPNAME` | `default` | Bootstrap default-group name, normalized to lowercase. |
| `AUTH_PASSWORD_MIN_LENGTH` | `SANDALA_AUTH_PASSWORD_MIN_LENGTH` | `8` | Minimum length written into the initial `users/user` password schema. |
| `AUTH_PASSWORD_PATTERN` | `SANDALA_AUTH_PASSWORD_PATTERN` | `^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[^A-Za-z0-9]).*$` | JSON Schema regular expression written into the initial password schema. By default it requires uppercase and lowercase letters, a digit, and a special character. Use `.*` for no additional pattern restriction. |
| `AUTH_USERNAME_MIN_LENGTH` | `SANDALA_AUTH_USERNAME_MIN_LENGTH` | `3` | Minimum username length written into the initial `users/user` schema. |
| `AUTH_USERNAME_MAX_LENGTH` | `SANDALA_AUTH_USERNAME_MAX_LENGTH` | `32` | Maximum username length written into the initial `users/user` schema. |
| `AUTH_USERNAME_PATTERN` | `SANDALA_AUTH_USERNAME_PATTERN` | `^[a-z0-9._-]+$` | JSON Schema regular expression written into the initial username schema. |
| `ALLOW_ANONYMOUS_USER_REGISTRATION` | `SANDALA_ALLOW_ANONYMOUS_USER_REGISTRATION` | `false` | Allows anonymous creation of `users/user` nodes through the registration behavior of the built-in hook. |

The password and username policy settings are consumed when Sandala first
creates the `users/user` schema. Changing them afterwards does not modify that
stored schema or retroactively change validation of existing installations.

Bootstrap does not reset an existing root user or default group. If either is
missing, the relevant bootstrap settings are used to create the missing record.

## Asset storage

| Python key | Environment variable | Default | Meaning |
| --- | --- | --- | --- |
| `ASSET_STORAGE_BACKEND` | `SANDALA_ASSET_STORAGE_BACKEND` | `local_fs` | Asset backend: `local_fs` or `s3`. |
| `ASSET_LOCAL_ROOT` | `SANDALA_ASSET_LOCAL_ROOT` | `.sandala_assets` | Root directory for local filesystem assets. |
| `ASSET_PUBLIC_BASE_URL` | `SANDALA_ASSET_PUBLIC_BASE_URL` | unset | Optional public base URL used when returning asset descriptor URLs. It may include a path prefix. |
| `ASSET_S3_ENDPOINT` | `SANDALA_ASSET_S3_ENDPOINT` | unset | S3-compatible endpoint URL. Leave unset for the AWS default endpoint selection. |
| `ASSET_S3_BUCKET` | `SANDALA_ASSET_S3_BUCKET` | empty string | Bucket that stores asset objects. Required by a functional S3 configuration. |
| `ASSET_S3_REGION` | `SANDALA_ASSET_S3_REGION` | unset | S3 region. |
| `ASSET_S3_ACCESS_KEY` | `SANDALA_ASSET_S3_ACCESS_KEY` | unset | S3 access key. |
| `ASSET_S3_SECRET_KEY` | `SANDALA_ASSET_S3_SECRET_KEY` | unset | S3 secret key. |
| `ASSET_S3_ADDRESSING_STYLE` | `SANDALA_ASSET_S3_ADDRESSING_STYLE` | `path` | S3 addressing style: `path` or `virtual`. |

The Python package requires the optional `s3` dependency group for
`ASSET_STORAGE_BACKEND=s3`. The Docker image includes it already. Asset URLs
remain public delivery URLs: granting permission to upload in a schema context
does not grant or restrict read access to a previously returned URL.

## Hooks and admin UI

| Python key | Environment variable | Default | Meaning |
| --- | --- | --- | --- |
| `HOOK_MODULES` | `SANDALA_HOOK_MODULES` | empty list | Hook-module import paths. In Python it accepts `list[str]` or a comma-separated string; in ENV it is comma-separated. Each module must define `register_hooks(app, container)`. |
| `ADMIN_UI_DIST` | `SANDALA_ADMIN_UI_DIST` | unset | Explicit path to a built Sandala admin UI directory. It must contain `index.html`. |

Without `ADMIN_UI_DIST`, the standard application serves the build bundled in
the installed Sandala package at `/admin/`. If that bundled build is absent,
the application still starts as an API-only service. An explicitly configured
but invalid directory makes application creation fail.

## Docker-only process settings

These are not Sandala configuration keys and have no `SANDALA_` form. They are
read only by the repository Docker image's command:

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `GUNICORN_WORKERS` | `2` | Number of Gunicorn worker processes. |
| `GUNICORN_THREADS` | `4` | Number of threads per Gunicorn worker. |

The image passes `SANDALA_HOST` and `SANDALA_PORT` to Gunicorn as its bind
address and port; their image defaults are `0.0.0.0` and `3000`.
