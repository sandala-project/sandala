# Errors

Sandala returns application and domain errors as JSON. Clients should use the
stable `error` code and HTTP status to make decisions. `error_description` and
the messages in `details` are intended for people and can change as the
implementation evolves.

```json
{
  "error": "request_body_invalid",
  "error_description": "Request body must be a JSON object"
}
```

Every Sandala application error has these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `error` | string | Stable, machine-readable error code. |
| `error_description` | string | Human-readable summary. |
| `details` | object, optional | Structured information specific to the error code. |

An endpoint's reference defines the error codes and any `details` members that
are specific to that endpoint. Do not parse `error_description` to determine
the type of failure.

## HTTP status codes

Sandala maps its error families to HTTP status codes as follows:

| Status | Error family | Meaning |
| --- | --- | --- |
| `400 Bad Request` | Validation | The request, a parameter, a query, a node document, or an entity schema is invalid. |
| `401 Unauthorized` | Authentication | No acceptable credential was supplied, or the credential is invalid, expired, revoked, or belongs to an inactive user. |
| `403 Forbidden` | Authorization | The authenticated actor is not allowed to perform the operation. |
| `404 Not Found` | Not found | The requested resource does not exist or is not readable to the actor. |
| `409 Conflict` | Conflict | The request conflicts with existing state, such as a duplicate identity or a resource still in use. |
| `500 Internal Server Error` | Unexpected failure | An internal error occurred. |

A status does not identify one particular failure. For example, `400` can use
`request_body_invalid`, `parameter_invalid`, `query_validation_failed`,
`document_validation_failed`, or `schema_validation_failed`.

Unexpected failures always have a safe response:

```json
{
  "error": "internal_error",
  "error_description": "Internal server error"
}
```

Sandala does not expose the underlying exception text in that response.

## Field errors

When Sandala can associate a failure with a field or container in a JSON
document, `details.field_errors` contains one or more entries:

| Field | Type | Meaning |
| --- | --- | --- |
| `location` | array of strings and integers | Path from the document root to the affected field or container. String segments select object properties; integer segments select array items. |
| `message` | string | Human-readable explanation for this location. |
| `keyword` | string | Machine-readable condition: a JSON Schema keyword for schema validation, or a Sandala domain-check identifier. |

`field_errors` is a general location mechanism, not a JSON Schema-only format.
Domain rules use it too, so a client can show an error next to the appropriate
control. A response can contain more than one field error.

For example, a nested schema validation failure can identify a property:

```json
{
  "error": "document_validation_failed",
  "error_description": "Node validation failed at 'profile.email': 'abc' is not a 'email'",
  "details": {
    "field_errors": [
      {
        "location": ["profile", "email"],
        "message": "'abc' is not a 'email'",
        "keyword": "format"
      }
    ]
  }
}
```

For a missing required property, `location` includes the missing property's
name rather than ending at its parent object. For a failure concerning an
array, the location can end at the array container when that is the smallest
meaningful place to present the error.

This example is a domain-rule error rather than a JSON Schema error:

```json
{
  "error": "link_patch_acl_hidden_references_missing",
  "error_description": "Patch must retain ACL-hidden references",
  "details": {
    "field_errors": [
      {
        "location": ["variants"],
        "message": "Value must retain ACL-hidden references",
        "keyword": "acl_hidden_references"
      }
    ]
  }
}
```

## Other structured details

Some errors carry `details` that are not field errors. Their keys and value
shapes belong to the corresponding error code. For example, `identity_in_use`
identifies the user or group that is still referenced and the reference that
prevents its deletion. Treat those structures as part of that error code's
endpoint contract rather than as a shared `details` schema.

## Framework HTTP errors

An HTTP failure generated before Sandala reaches domain logic is not converted
to the application-error envelope. For example, an unknown route returns the
web framework's normal `404` response, and an unsupported method returns its
normal `405` response. Clients should therefore distinguish a Sandala JSON
error response from a generic HTTP error response.
