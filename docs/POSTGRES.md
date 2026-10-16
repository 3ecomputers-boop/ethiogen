# PostgreSQL migration

The project runs on SQLite by default so a fresh clone works with no services.
Switching to PostgreSQL is environment-driven: set `DB_ENGINE=postgresql` and
the `DB_*` variables and the same code uses Postgres.

## Why

Shared-table multi-tenancy puts every organisation's rows in one set of
tables, distinguished by `organization_id`. That works fine on SQLite, but a
workforce SaaS wants real concurrent writes and `SELECT ... FOR UPDATE` on
subscriptions, which SQLite serialises badly.

## What is already in place

* `psycopg[binary]==3.3.6` in `requirements.txt` (prebuilt wheel, no libpq
  needed on Windows or cPanel).
* `DATABASES` in `job_portal/settings.py` is env-driven, with SQLite as the
  default and Postgres as an opt-in branch.
* `tools/migrate_to_postgres.py` copies the live data and verifies row counts.

## One-time setup

### 1. Create a role and database

Use a dedicated application role, not `postgres`.

`tools/pg_bootstrap.py` does this, and applies least privilege
(`NOSUPERUSER NOCREATEDB NOCREATEROLE`):

```bash
python tools/pg_bootstrap.py --admin-password <superuser-password>
```

It only ever creates `ethiogen`; it prints the other databases it found so
you can confirm it is not colliding with anything.

By hand, the equivalent is:

```sql
CREATE ROLE ethiogen LOGIN PASSWORD 'choose-something-long';
CREATE DATABASE ethiogen OWNER ethiogen ENCODING 'UTF8' TEMPLATE template0;
GRANT ALL ON SCHEMA public TO ethiogen;
```

### 2. Configure the environment

Add to `.env` (gitignored):

```
DB_ENGINE=postgresql
DB_NAME=ethiogen
DB_USER=ethiogen
DB_PASSWORD=<the password>
DB_HOST=127.0.0.1
DB_PORT=5432
```

For a managed host that requires TLS, also set `DB_SSLMODE=require`.

### 3. Migrate the data

```bash
# preview: prints the source inventory, touches nothing
python tools/migrate_to_postgres.py --source-sqlite --dry-run

# do it
python tools/migrate_to_postgres.py --source-sqlite

# target already has application data (refuses without this)
python tools/migrate_to_postgres.py --source-sqlite --force
```

`--source-sqlite` is required once `DB_ENGINE=postgresql` is in `.env`: the
tool needs to read from the file while writing to the `DB_*` connection, and
refuses to guess which one you meant otherwise.

The script:

1. inventories the SQLite database (row count per model), and **fails** if
   any model cannot be read,
2. checks the target is reachable,
3. **refuses to write to a target that already holds application data**
   unless `--force`. Tables that `migrate` generates (content types,
   permissions) do not count as application data,
4. dumps the source one model at a time,
5. converts `django_countries` values from country **names** to ISO codes,
6. runs `migrate` against Postgres,
7. truncates the target's content-type / permission / group tables so the
   imported graph replaces them wholesale,
8. loads the fixture,
9. re-counts every model and fails loudly on any mismatch.

It never writes to the SQLite source.

### 4. Switch over

```bash
python manage.py migrate --check    # expect exit 0
python manage.py check
python manage.py runserver
```

Then run the test suites against the new backend before committing to it.

## Rolling back

The SQLite file is untouched, so reverting is just removing the `DB_*`
variables from `.env`. Take a copy first anyway:

```bash
python manage.py dumpdata --natural-foreign --output=backup.json
pg_dump -h 127.0.0.1 -U ethiogen -d ethiogen > ethiogen.sql
```

## Things that bit during the migration

**`django_countries` writes names, not codes.** `CountryField.value_to_string()`
emits `'Ethiopia'` while the column is `varchar(2)` holding `'ET'`. SQLite
does not enforce `max_length`, so this is invisible until PostgreSQL rejects
it with *"value too long for type character varying(2)"*. The migration tool
normalises these before loading.

**Django 5.2 no longer creates the default groups.** `create_permissions()`
used to create Admin/Editor/Viewer; it no longer does. This project's groups
(`JobSeeker` with 497 users, `Dashboard admin` with 100 permissions) are real
source data and are copied, with the target's own copies truncated first.

**Serialising the whole model list at once breaks.** Passing
`apps.get_models()` to `serializers.serialize()` leaves fields deferred, and a
deferred `DateTimeField` serialises as a `DeferredAttribute` descriptor:
*"'DeferredAttribute' object has no attribute 'isoformat'"*. Serialise one
model at a time.

**Swapping the database mid-process needs three changes**, not one:
`settings.DATABASES`, `connections.databases`, and the cached
`DatabaseWrapper` in `connections._connections`. Missing the last one leaves
queries pointing at the old database and reporting zero rows rather than
erroring.

## Notes

* On this machine `postgresql-x64-17` listens on **:5432** and
  `postgresql-x64-14` on :5433 — the opposite of the usual convention. Both
  use `scram-sha-256` for every connection including localhost, so there is
  no trust path and a real password is required.
* That instance also hosts other projects (`cms`, `construction_ecosystem`,
  `test_*`). The Ethiogen role has no privileges over them.
* `pg_import.json` is written to the project root during a migration and is
  gitignored. It contains all user records in cleartext — delete it when you
  are satisfied.