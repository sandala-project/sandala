# Explore the demo library

The demo library is a repeatable dataset for exploring Sandala in the Admin UI
and through its read APIs. It creates the `demo_library` module with a
multi-level catalogue tree, related entities, resolved links, nested values,
external asset descriptors, and enough books to make filtering and table views
useful.

The seed is included only in a Sandala source checkout. It is not part of the
published Python package or Docker image. Always use an isolated development
database: the optional reset operation removes and recreates the entire
`demo_library` module.

## What the dataset contains

The default seed produces 1,200 Book nodes from a deterministic source. It
repeats a small built-in catalogue when necessary, adding a catalogue-record
suffix to repeated titles. IDs and links are stable across equivalent seed
runs; timestamps reflect the time of each run. An optional Open Library
snapshot provides a larger source set without making normal seeding depend on
the network.

Every demo node is readable, writable, and populateable by every actor. The
dataset is deliberately open so that it demonstrates navigation, queries, and
link resolution rather than an access-policy design.

| Entity | Purpose in the demo |
| --- | --- |
| `CatalogFolder` | Builds five root branches for authors, publishers, subjects, languages, and books. Authors and publishers are grouped alphabetically; books are grouped by publication year. |
| `Book` | The main records. They combine scalar fields, nullable fields, Date, RichText, Image and Array values, nested external identifiers, and links to authors, publishers, subjects, and languages. |
| `Author` | Demonstrates an independent referenced record and an Array of Objects that contains Book and Publisher links plus relationship metadata. |
| `Publisher` | A compact referenced record with an optional enumerated country. |
| `Subject` and `Language` | Reference data with reverse-looking `best_books` LinkArray fields. |

The cover and illustration descriptors point to public Open Library cover URLs;
their files are not stored in Sandala's asset storage. Their availability is
therefore outside the local demo environment.

## Seed an isolated database

From a source checkout with the project virtual environment installed, choose a
database name that is not used for application data, set a local-only root
password, and run the seed:

```bash
export SANDALA_MONGO_URI='mongodb://localhost:27017'
export SANDALA_MONGO_DB='sandala_demo'
export SANDALA_ROOT_PASSWORD=''

./.venv/bin/python -m demo_data.library.seed
```

The empty password above is deliberately invalid: replace it before running the
command with a local-only password that satisfies the configured password
policy. The seed bootstraps the built-in users module when the database is
empty, then creates or updates the demo module, its six schemas, and its
generated nodes. It prints a count for each entity when it finishes.

Start the local backend in the same shell so it uses the same configuration:

```bash
./.venv/bin/python -m sandala.api
```

Open `http://localhost:3000/admin/` and sign in as `root` with the password
chosen above.

For a smaller fresh dataset, add `--books`:

```bash
./.venv/bin/python -m demo_data.library.seed --reset --books 50
```

`--reset` drops the demo module's node collection, deletes its entity schemas,
and recreates the module before seeding. Use it when replacing an existing
dataset, especially when reducing the number of books; without it, older nodes
that are outside the new generated set remain in the collection.

## Use an Open Library snapshot

The built-in records make the demo deterministic and entirely local. To seed
from a bounded snapshot instead, download it first and then reset the demo:

```bash
./.venv/bin/python -m demo_data.library.fetch --count 1200

./.venv/bin/python -m demo_data.library.seed \
  --reset \
  --source-snapshot demo_data/library/data/openlibrary_search.json
```

`fetch` downloads a JSON `docs` array from Open Library and stores it locally.
The seed normalizes usable records from that snapshot; it does not contact Open
Library itself. Reusing the same snapshot preserves the generated records, IDs,
and links; timestamps still reflect the time of each seed run.

## Open Library acknowledgement

The demo's optional catalogue snapshot, work links, and external cover URLs use
[Open Library](https://openlibrary.org/), an Internet Archive project. Sandala
is grateful to Open Library and its contributors for making these resources
available for book discovery and experimentation.

Cover images remain hosted by `covers.openlibrary.org` and are loaded directly
from that service; Sandala neither downloads nor redistributes them. The
[Open Library Covers API](https://openlibrary.org/dev/docs/api/covers) asks
public displays to retain a cover-service URL and appreciates a link back to
Open Library. The demo keeps an `openlibrary_url` field on Book records for
that source context.

## Explore the model

In the Admin UI, choose **Nodes**, select `demo_library`, and begin in **Tree**
view. The `x-ui.labels.tree` templates give folders and reference records their
emoji labels. Expand a branch, select a Book, and inspect the editor pane to
see the schema-driven controls for its scalar, nested, link, and asset fields.

Switch to **Table**, select `Book`, and try a filter on `first_published`,
`rating`, or a linked Author. Add link fields as columns to see their resolved
labels. The [Using the Admin UI](using-the-admin-ui.md) guide explains these
workflows, and [Querying nodes](querying-nodes.md) shows their REST equivalents.

The dataset is also useful for observing link-resolution trade-offs:

- `Book.authors`, `publishers`, and `languages` are LinkArrays;
- `Book.subjects` is an Array of Objects containing a Subject Link;
- `Author.best_cooperations` is a deeper Array-of-Objects relationship with
  links to Books and Publishers.

These shapes make it possible to compare simple reference collections with
nested relationship records. The schema rationale and the ordering trade-off
are described in [Designing a schema](designing-a-schema.md).

## What the seed does not test

For speed and repeatability, the seed validates every generated document
against its effective entity schema and then writes the data through the
repository in bulk. It does not create nodes through the REST API or
`node_service`, and it does not run ordinary node-write hooks.

Use this dataset to explore reads, projections, filtering, sorting, resolution,
the Admin UI, and schema-driven rendering. Test integrations, ACL policies,
hooks, and write behavior with ordinary service or REST calls using data that
matches the scenario under test.
