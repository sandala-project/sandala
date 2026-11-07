# Authentication

Sandala supports browser auth sessions and personal access tokens (PATs). This
page defines the HTTP endpoints that create and manage them. The built-in
`users/user` and `users/group` entities, including their node-operation
contract, are documented in [Users and groups](users-and-groups.md).

All paths on this page are below `/api/v1/`.

## Credentials on requests

An auth-session credential is sent in Sandala's configured cookie. A PAT is
sent in the `Authorization` header:

```text
Authorization: Bearer <pat-id>.<secret>
```

Bearer authentication takes precedence when both a Bearer header and an
auth-session cookie are present. An invalid Bearer credential therefore fails
the request rather than falling back to the cookie.

Session lifetime, renewal, cookie attributes, and the default PAT lifetime are
configured as described in [Configuration](../configuration.md).

## Login

`POST /auth/login/`

Send local credentials in a `credentials` wrapper. `login` accepts a username
or email address; `password` is a non-empty string.

```json
{
  "credentials": {
    "login": "root",
    "password": ""
  }
}
```

The empty password is a deliberately invalid placeholder. Replace it with the
user's actual password before sending the request.

On success, the endpoint returns `200 OK`, sets the configured auth-session
cookie, and returns `status: "ok"` plus the user representation described
in [Users and groups](users-and-groups.md#reading-users-and-groups).

The session secret appears only in the cookie, never in the JSON response.

## Logout

`POST /auth/logout/`

Logout ends the current auth session identified by the configured cookie and
clears that cookie in the response:

```json
{
  "status": "ok"
}
```

It returns `200 OK` even when the request has no session cookie or its session
has already expired or been revoked. Logout does not revoke PATs.

## Read the current user

`GET /auth/me/`

Requires authentication through either an auth-session cookie or a PAT. On
success it returns `200 OK` with the current user's `user` representation
described in [Users and groups](users-and-groups.md#reading-users-and-groups).

A session may be renewed on this or another authenticated request when session
renewal is enabled; that response sets the auth-session cookie again with its
renewed lifetime.

## PAT representation

PAT list and detail responses use this representation:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | UUID string | Public PAT identifier. |
| `subject_id` | UUID string | ID of the `users/user` node authenticated by this PAT. |
| `name` | string | Human-readable token name. |
| `expires_at` | ISO 8601 date-time or `null` | Expiry time; `null` means no expiry. |
| `revoked_at` | ISO 8601 UTC date-time or `null` | Revocation time; `null` means not revoked, but the token may already have expired. |
| `created_by` | UUID string | User who created the PAT. |
| `cdate` | ISO 8601 UTC date-time | Creation time. |
| `mdate` | ISO 8601 UTC date-time | Most recent PAT change. |

`token` is not part of this persistent representation. It is included only in
the responses that create or rotate a PAT, and must be stored by the client at
that time. Sandala never returns it again.

## Create a PAT

`POST /auth/pats/`

Requires authentication. A superuser may create a PAT for any active user;
every other actor may create one only for themselves.

```json
{
  "pat": {
    "subject_id": "8b06138e-d43d-4dba-a185-bb8c61f814c4",
    "name": "CI deployment",
    "expires_at": "2026-12-31T00:00:00Z"
  }
}
```

`subject_id` and non-empty `name` are required. Omit `expires_at` to use the
configured default lifetime, or send `null` to create a PAT without an expiry.
An explicit expiry is an ISO 8601 date-time. For consistency, send UTC values
with a trailing `Z`.

On success, the endpoint returns `201 Created` with `{"pat": {...}}`. The
PAT object contains every field in the representation above plus its one-time
Bearer token:

```json
{
  "pat": {
    "id": "021bf879-d5ae-421d-bf3e-9b3fc47c0b49",
    "subject_id": "8b06138e-d43d-4dba-a185-bb8c61f814c4",
    "name": "CI deployment",
    "expires_at": "2026-12-31T00:00:00Z",
    "revoked_at": null,
    "created_by": "8b06138e-d43d-4dba-a185-bb8c61f814c4",
    "cdate": "2026-09-27T12:00:00Z",
    "mdate": "2026-09-27T12:00:00Z",
    "token": "021bf879-d5ae-421d-bf3e-9b3fc47c0b49.<secret>"
  }
}
```

## List PATs

`GET /auth/pats/`

Requires authentication. A superuser receives all PATs; every other actor
receives only PATs whose `subject_id` is their own user ID. The response is
`200 OK`:

```json
{
  "pats": [
    {
      "id": "021bf879-d5ae-421d-bf3e-9b3fc47c0b49",
      "subject_id": "8b06138e-d43d-4dba-a185-bb8c61f814c4",
      "name": "CI deployment",
      "expires_at": "2026-12-31T00:00:00Z",
      "revoked_at": null,
      "created_by": "8b06138e-d43d-4dba-a185-bb8c61f814c4",
      "cdate": "2026-09-27T12:00:00Z",
      "mdate": "2026-09-27T12:00:00Z"
    }
  ]
}
```

The response never includes token secrets.

## Get a PAT

`GET /auth/pats/{id}/`

Requires authentication. A superuser may read any PAT; every other actor may
read only their own. A successful response is `200 OK` with `{"pat": {...}}`
using the PAT representation above, without `token`.

## Revoke a PAT

`POST /auth/pats/{id}/revoke/`

Requires the same access as Get a PAT. On success it returns `200 OK`:

```json
{
  "pat": {
    "id": "021bf879-d5ae-421d-bf3e-9b3fc47c0b49",
    "revoked_at": "2026-09-27T12:30:00Z",
    "mdate": "2026-09-27T12:30:00Z"
  }
}
```

A revoked PAT can no longer authenticate requests.

## Rotate a PAT

`POST /auth/pats/{id}/rotate/`

Requires the same access as Get a PAT. Rotation invalidates the previous
secret and returns a new one once:

```json
{
  "pat": {
    "id": "021bf879-d5ae-421d-bf3e-9b3fc47c0b49",
    "token": "021bf879-d5ae-421d-bf3e-9b3fc47c0b49.<new-secret>",
    "mdate": "2026-09-27T12:45:00Z"
  }
}
```

The response is `200 OK`.

## Errors

All failures use the [common error contract](errors.md).

### Login

`POST /auth/login/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | The JSON body is not an object or does not contain an object in `credentials`. |
| `400` | `parameter_invalid` | `login` or `password` is absent, empty, or has the wrong type. |
| `401` | `authentication_error` | The login is unknown, the user is inactive or has no password hash, or the password is incorrect. |

### Read the current user and list PATs

`GET /auth/me/` and `GET /auth/pats/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `401` | `authentication_error` | No credential was supplied, or the session or PAT is malformed, expired, revoked, invalid, or belongs to an inactive user. |

### Create a PAT

`POST /auth/pats/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | The JSON body is not an object or does not contain an object in `pat`. |
| `400` | `parameter_invalid` | `subject_id` or `name` is absent or malformed, or a supplied `expires_at` value is malformed. |
| `400` | `validation_error` | `subject_id` does not identify an active user. |
| `401` | `authentication_error` | No acceptable credential was supplied, or it is invalid. |
| `403` | `access_denied` | A non-superuser attempts to create a PAT for another user. |

### Get or revoke a PAT

`GET /auth/pats/{id}/` and `POST /auth/pats/{id}/revoke/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `401` | `authentication_error` | No acceptable credential was supplied, or it is invalid. |
| `403` | `access_denied` | A non-superuser requests a PAT belonging to another user. |
| `404` | `not_found` | The PAT ID does not exist. |

### Rotate a PAT

`POST /auth/pats/{id}/rotate/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `validation_error` | The PAT has already been revoked. |
| `401` | `authentication_error` | No acceptable credential was supplied, or it is invalid. |
| `403` | `access_denied` | A non-superuser attempts to rotate a PAT belonging to another user. |
| `404` | `not_found` | The PAT ID does not exist. |
