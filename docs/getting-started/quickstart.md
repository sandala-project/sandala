# Quickstart

This quickstart creates a small `library` module, a `Book` entity schema, and
one book node through Sandala's REST API. It assumes a fresh local instance
started as described in [Installation](installation.md).

## 1. Set shell variables

Run the commands from a new shell. `COOKIE_JAR` is a temporary file that lets
`curl` send the authentication session returned by the login endpoint.

```bash
export SANDALA_URL='http://localhost:3000/api/v1'
export COOKIE_JAR="$(mktemp)"
```

## 2. Sign in as the bootstrap superuser

On its first start, Sandala creates the `root` user with the password supplied
as `SANDALA_ROOT_PASSWORD`. The empty password below is deliberately invalid;
replace it with the secret chosen for the initial bootstrap before running the
request.

```bash
curl --fail-with-body --silent --show-error \
  --cookie-jar "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data '{
    "credentials": {
      "login": "root",
      "password": ""
    }
  }' \
  "$SANDALA_URL/auth/login/"
```

The response includes the authenticated user profile. The session identifier is
stored in `COOKIE_JAR`, not in the JSON response.

## 3. Create a module

A module owns a collection of related entity schemas and one tree of nodes.
The root owner and group are omitted here, so Sandala takes both from the
authenticated superuser.

```bash
curl --fail-with-body --silent --show-error \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data '{
    "module": {
      "name": "library",
      "description": "My first library",
      "root_perm": {
        "owner": {"p": true},
        "group": {"p": false},
        "others": {"p": false}
      },
      "root_children_entities": []
    }
  }' \
  "$SANDALA_URL/modules/"
```

An empty `root_children_entities` list permits any entity of this module at the
root. The permission settings allow only the virtual root's owner to create or
move root nodes.

## 4. Create a `Book` entity schema

Entity schemas are JSON Schema documents with Sandala metadata. This minimal
schema defines one required, publicly visible and writable `title` field. Its
default node permissions allow every actor to read and write it; that permissive
choice is only for this short example. Its empty child-entity list means that
Book nodes cannot have children.

```bash
curl --fail-with-body --silent --show-error \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data '{
    "entity": {
      "description": "A book",
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "title": {
          "description": "Book title",
          "type": "string",
          "x-meta": {
            "semantic-type": "String",
            "visibility-mode": "all",
            "write-mode": "all"
          }
        }
      },
      "required": ["title"],
      "x-ui": {
        "labels": {
          "tree": "📖 {{title}}",
          "reference": "📖 {{title}}"
        }
      },
      "x-meta": {
        "children": {"entities": []},
        "perm": {
          "default": {
            "owner": {"r": true, "w": true, "p": true},
            "group": {"r": true, "w": true, "p": true},
            "others": {"r": true, "w": true, "p": true}
          }
        }
      }
    }
  }' \
  "$SANDALA_URL/modules/library/entities/Book/"
```

The entity name comes from the URL. Sandala adds it to the schema's `title`
field and adds the standard system fields when returning the schema.

## 5. Create a node

Nodes carry an `entity` value and data that conforms to the matching schema:

```bash
curl --fail-with-body --silent --show-error \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data '{
    "node": {
      "entity": "Book",
      "title": "A Wizard of Earthsea"
    }
  }' \
  "$SANDALA_URL/nodes/library/"
```

Sandala generates the node ID and system fields, assigns the current user and
their primary group, and applies the entity's default permissions.

## 6. List the books

The entity-scoped endpoint returns only `Book` nodes. It applies the normal ACL
filter and uses the default projection when `project` is omitted:

```bash
curl --fail-with-body --silent --show-error \
  --cookie "$COOKIE_JAR" \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"query": {}}' \
  "$SANDALA_URL/nodes/library/entity/Book/query/"
```

You now have a working schema-driven collection. Next, learn how schemas,
semantic types, ACL, links, filters, and projections fit together in the
Concepts section.

## Clean up

Remove the local cookie file when you finish:

```bash
rm -f "$COOKIE_JAR"
```
