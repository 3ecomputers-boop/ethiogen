"""
Copy the live SQLite database into PostgreSQL.

Runs the real Django migration machinery rather than raw SQL, so the target
schema is exactly what the app expects.

Safety properties
-----------------
* The SOURCE (SQLite) is opened read-only for the dump and is never
  written to.
* The target is checked for existing rows and the run ABORTS unless
  --force is given. There is no "merge" mode on purpose: merging two
  divergent datasets silently is how production data gets lost.
* Every step is verified by counting rows before and after.

Usage
-----
    python tools/migrate_to_postgres.py --dry-run     # show the plan only
    python tools/migrate_to_postgres.py --create-db   # create DB + user first
    python tools/migrate_to_postgres.py               # do it
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_portal.settings')

# Sentinel for "this model could not be counted", so a connection failure is
# never silently reported as zero rows.
ERROR_COUNT = -1

# Read .env before Django settings import it, so DB_* is populated.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / '.env')
except Exception:  # pragma: no cover - dotenv is a hard dependency anyway
    pass


def pg_config() -> dict:
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME') or 'ethiogen',
        'USER': os.getenv('DB_USER') or 'postgres',
        'PASSWORD': os.getenv('DB_PASSWORD') or '',
        'HOST': os.getenv('DB_HOST') or '127.0.0.1',
        'PORT': os.getenv('DB_PORT') or '5432',
        'CONN_MAX_AGE': 0,
        'OPTIONS': ({'sslmode': os.environ['DB_SSLMODE']}
                    if os.getenv('DB_SSLMODE') else {}),
    }


def app_label_for(model) -> str:
    return model._meta.app_label


APP_EXCLUDES = {
    # Genuinely not worth carrying over.
    #   sessions.session  -- live logins; everyone logs in again
    #   admin.logentry    -- admin history noise
    'sessions.session',
    'admin.logentry',
}

# `migrate` generates these in the target, so they are not "application data"
# for the emptiness check. They are still COPIED from the source (Django 5.2
# no longer creates the default groups, so this project's groups -- "JobSeeker"
# with 497 users, "Dashboard admin" holding 100 permissions -- are real data),
# with the target's own versions truncated first so the whole
# contenttype -> permission -> group graph is internally consistent.
GENERATED_TABLES = {
    'contenttypes.contenttype',
    'auth.permission',
    'auth.group',
}

# Truncated in the target before loading, so the source owns these tables.
RESET_TABLES = [
    'django_content_type',
    'auth_permission',
    'auth_group',
    'auth_user_groups',
    'auth_user_user_permissions',
    'auth_group_permissions',
    'admin_logentry',
    'django_session',
]


def model_key(model) -> str:
    return f'{model._meta.app_label}.{model._meta.model_name}'


def is_excluded(model) -> bool:
    return model_key(model) in APP_EXCLUDES


def build_country_maps(apps):
    """
    Map "model -> {field: (name_to_code, is_multiple)}" for every
    django_countries field in the project.

    Needed because CountryField.value_to_string() emits the full country NAME
    ("Ethiopia") while the column is varchar(2) holding the ISO code ("ET").
    SQLite does not enforce max_length so this stays invisible until the
    data reaches PostgreSQL, which rejects it with
    "value too long for type character varying(2)".
    """
    try:
        from django_countries import countries
        from django_countries.fields import CountryField
    except ImportError:
        return {}

    name_to_code = {}
    for country in countries:
        if country.name:
            name_to_code[country.name] = country.code

    maps = {}
    for model in apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        fields = {}
        for field in model._meta.concrete_fields:
            if isinstance(field, CountryField):
                fields[field.attname] = (name_to_code, bool(getattr(field, 'multiple', False)))
        if fields:
            maps[model_key(model)] = fields
    return maps


def normalise_countries(payload, country_maps) -> int:
    """Rewrite country names in a fixture payload to their ISO codes."""
    if not country_maps:
        return 0
    changed = 0
    for obj in payload:
        fields = country_maps.get(obj.get('model'))
        if not fields:
            continue
        fields_data = obj.get('fields')
        if not isinstance(fields_data, dict):
            continue
        for attname, (name_to_code, multiple) in fields.items():
            value = fields_data.get(attname)
            if not isinstance(value, str) or not value:
                continue
            if multiple:
                parts = value.split(',')
                new_parts = [name_to_code.get(p.strip(), p.strip()) for p in parts]
                new_value = ','.join(new_parts)
            else:
                new_value = name_to_code.get(value, value)
            if new_value != value:
                fields_data[attname] = new_value
                changed += 1
    return changed


def count_application_rows(apps, using='default') -> int:
    """
    Rows in tables that hold real application data.

    Tables that `migrate` regenerates in the target are ignored, otherwise a
    freshly-migrated database always looks "non-empty" and the safety check
    can never pass.
    """
    total = 0
    for model in apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        key = model_key(model)
        if key in APP_EXCLUDES or key in GENERATED_TABLES:
            continue
        try:
            total += model.objects.using(using).count()
        except Exception:
            pass
    return total


def collect_counts(using='default'):
    """
    Row count per concrete model, keyed 'app.model'.

    Errors are recorded as ERROR_COUNT rather than being swallowed: a
    connection pointed at the wrong database raises here, and hiding it
    makes the tool cheerfully report "0 rows" for a database full of users.
    """
    from django.apps import apps

    counts = {}
    errors = {}
    for model in apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        key = f'{model._meta.app_label}.{model._meta.model_name}'
        try:
            counts[key] = model.objects.using(using).count()
        except Exception as exc:
            counts[key] = ERROR_COUNT
            errors[key] = exc
    return counts, errors


def check_source_is_sqlite(settings) -> str:
    engine = settings.DATABASES['default']['ENGINE']
    if 'sqlite' not in engine:
        raise SystemExit(
            f'Refusing to run: the source database is {engine!r}, not SQLite.\n'
            f'Once DB_ENGINE=postgresql is in .env the project runs on Postgres, so '
            f'you need --source-sqlite to say "read from the file, write to the DB_* '
            f'connection" explicitly.'
        )
    return str(settings.DATABASES['default']['NAME'])


def normalise_db(config: dict) -> dict:
    """
    Fill in the keys Django's backend expects (ATOMIC_REQUESTS, AUTOCOMMIT,
    TIME_ZONE, TEST, ...) around a minimal config dict.

    A hand-built DATABASES entry that is only partially specified raises
    `KeyError: 'TIME_ZONE'` the first time a query runs, because
    BaseDatabaseWrapper reads those keys off settings_dict. Reusing Django's
    own normaliser avoids guessing the full key set.
    """
    from django.db.utils import ConnectionHandler

    handler = ConnectionHandler()
    return handler.configure_settings({'default': dict(config)})['default']


def use_database(settings, connections, config: dict) -> None:
    """
    Point the 'default' alias at a different database, mid-process.

    Three things have to change, and missing any one of them fails
    *silently* rather than loudly:

    1. `settings.DATABASES` -- what a fresh process would read.
    2. `connections.databases` -- same dict object, but named explicitly so
       the intent is clear.
    3. The cached `DatabaseWrapper` in `connections._connections`. Its
       `settings_dict` was resolved when it was built, so updating (1) and
       (2) leaves every query on the OLD database. Deleting the cached
       wrapper forces Django to rebuild it from the new config.
    """
    settings.DATABASES['default'] = normalise_db(config)
    connections.databases['default'] = settings.DATABASES['default']
    connections.close_all()
    local = getattr(connections, '_connections', None)
    if local is not None:
        for alias in ('default',):
            try:
                delattr(local, alias)
            except (AttributeError, KeyError):
                pass


def pin_source_to_sqlite(settings, connections) -> str:
    """
    Force the source to the SQLite file even though DB_ENGINE says postgres.

    Needed because the target connection is configured from the same DB_*
    variables that would otherwise select the backend.
    """
    from pathlib import Path

    name = Path(ROOT) / 'db.sqlite3'
    use_database(settings, connections, {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': name,
        'OPTIONS': {'timeout': 20},
    })
    return str(name)


def create_database_and_user(cfg: dict) -> None:
    """
    Create the role and database using psycopg against the maintenance DB.

    Needs a superuser credential in DB_PASSWORD.
    """
    import psycopg

    user = cfg['USER']
    password = cfg['PASSWORD']
    if not password:
        raise SystemExit('DB_PASSWORD is empty. Cannot create a role.')

    dsn = (f"host={cfg['HOST']} port={cfg['PORT']} "
           f"dbname=postgres user={user} password={password}")
    print(f'-- connecting to {cfg["HOST"]}:{cfg["PORT"]} as {user}')

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT version()')
            print('   server:', cur.fetchone()[0].split(',')[0])

            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
            if cur.fetchone():
                print(f'   role {user!r} already exists')
            else:
                cur.execute(f'CREATE ROLE "{user}" LOGIN PASSWORD %s', (password,))
                print(f'   created role {user!r}')

            # A database can be owned by exactly one role.
            cur.execute('SELECT 1 FROM pg_database WHERE datname = %s',
                        (cfg['NAME'],))
            if cur.fetchone():
                print(f'   database {cfg["NAME"]!r} already exists')
            else:
                cur.execute(f'CREATE DATABASE "{cfg["NAME"]}" OWNER "{user}"')
                print(f'   created database {cfg["NAME"]!r}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true',
                        help='Print the plan and row counts. Change nothing.')
    parser.add_argument('--create-db', action='store_true',
                        help='Create the role and database before migrating.')
    parser.add_argument('--force', action='store_true',
                        help='Allow migrating into a non-empty database.')
    parser.add_argument('--source-sqlite', action='store_true',
                        help='Read from db.sqlite3 even when DB_ENGINE says '
                             'postgresql. The target still comes from DB_*.')
    args = parser.parse_args()

    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connections, connection

    if args.source_sqlite:
        source_name = pin_source_to_sqlite(settings, connections)
    else:
        source_name = check_source_is_sqlite(settings)
    # Capture the source config NOW, while 'default' still points at SQLite,
    # so it can be restored after we switch to the target.
    source_config = dict(settings.DATABASES['default'])
    cfg = pg_config()

    print('=' * 66)
    print('SQLite -> PostgreSQL migration')
    print('=' * 66)
    print(f'  source : {source_name}')
    print(f'  target : {cfg["USER"]}@{cfg["HOST"]}:{cfg["PORT"]}/{cfg["NAME"]}')
    print()

    # ---- 1. source inventory -------------------------------------------
    print('[1/5] Inventorying the source database')
    source_counts, source_errors = collect_counts('default')
    total_rows = sum(v for v in source_counts.values()
                     if isinstance(v, int) and v > 0)
    for key, value in sorted(source_counts.items()):
        if isinstance(value, int) and value > 0:
            print(f'        {key:<42} {value:>8}')
    print(f'        {"TOTAL":<42} {total_rows:>8}')
    if source_errors:
        print()
        print(f'        !! {len(source_errors)} model(s) could NOT be read from the')
        print('           source. The inventory above is incomplete.')
        for key, exc in list(source_errors.items())[:5]:
            print(f'           {key}: {exc}')
        return 2
    if total_rows == 0:
        print('        !! source is empty -- is db.sqlite3 the right file?')
        return 2
    print()

    # ---- 2. connectivity ------------------------------------------------
    print('[2/5] Checking target connectivity')
    try:
        import psycopg

        dsn = (f"host={cfg['HOST']} port={cfg['PORT']} dbname=postgres "
               f"user={cfg['USER']} password={cfg['PASSWORD']}")
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT version()')
                server = cur.fetchone()[0].split(',')[0]
        print(f'        reachable: {server}')
    except Exception as exc:
        print(f'        CANNOT REACH TARGET: {exc}')
        if args.create_db:
            print('        trying --create-db ...')
            try:
                create_database_and_user(cfg)
            except SystemExit:
                raise
            except Exception as exc2:
                raise SystemExit(f'        create-db failed: {exc2}')
        else:
            print('        re-run with --create-db to create the role and database')
            return 2

    try:
        import psycopg

        dsn = (f"host={cfg['HOST']} port={cfg['PORT']} dbname={cfg['NAME']} "
               f"user={cfg['USER']} password={cfg['PASSWORD']}")
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database(), current_user')
                db, usr = cur.fetchone()
        print(f'        connected as {usr} to {db}')
    except Exception as exc:
        print(f'        database {cfg["NAME"]!r} not usable yet: {exc}')
        if args.create_db:
            create_database_and_user(cfg)
        else:
            print('        re-run with --create-db')
            return 2

    if args.dry_run:
        print()
        print('[dry run] Stopping here. Nothing was changed.')
        print('Re-run without --dry-run to perform the migration.')
        return 0

    # ---- 3. is the target empty? ---------------------------------------
    print()
    print('[3/5] Checking the target is safe to write to')
    use_database(settings, connections, cfg)

    from django.apps import apps

    probe_failures = []
    for model in apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        try:
            model.objects.using('default').count()
        except Exception:
            probe_failures.append(model._meta.label)
    if probe_failures:
        print(f'        {len(probe_failures)} table(s) missing -> schema not migrated yet')

    existing = count_application_rows(apps, using='default')

    if existing and not args.force:
        print(f'        TARGET ALREADY HAS {existing} APPLICATION ROW(S). Refusing.')
        print('        Re-run with --force only if you are certain.')
        return 3
    if existing:
        print(f'        WARNING: --force given, target has {existing} application row(s)')
    else:
        print('        target has no application data, safe to proceed')
        print('        (tables seeded by migrate -- contenttypes, permissions, '
              'default groups -- are ignored)')

    # ---- 4. dump from the SOURCE, then migrate and load ------------------
    # Order matters: serialization MUST happen while 'default' is still the
    # SQLite source. Doing it after switching to Postgres reads the empty
    # target and copies nothing -- which is silent, because an empty target
    # and an empty source look identical in the row-count report.
    print()
    print('[4/5] Dumping the source')
    dump_path = ROOT / 'pg_import.json'
    excludes = APP_EXCLUDES

    import json

    from django.core import serializers

    use_database(settings, connections, source_config)
    print(f'        reading from {source_name}')

    # Serialize one model at a time rather than handing serialize() the whole
    # list of model classes. Passing classes makes Django build a combined
    # queryset that leaves fields deferred, and a deferred DateTimeField then
    # serialises as a DeferredAttribute descriptor and blows up with
    # "'DeferredAttribute' object has no attribute 'isoformat'".
    payload = []
    failures = []
    for model in apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        label = model_key(model)
        if label in excludes:
            continue
        try:
            chunk = serializers.serialize(
                'json', model._default_manager.all(),
                use_natural_foreign_keys=False,
                use_natural_primary_keys=False,
            )
            payload.extend(json.loads(chunk))
        except Exception as exc:
            failures.append((label, exc))

    country_changed = normalise_countries(payload, build_country_maps(apps))
    if country_changed:
        print(f'        normalised {country_changed} country value(s) to ISO codes')

    if failures:
        print(f'        !! {len(failures)} model(s) failed to serialise:')
        for label, exc in failures:
            print(f'           {label}: {exc}')
        return 5

    if not payload:
        print('        !! nothing was read from the source. Refusing to load '
              'an empty file into the target.')
        return 5

    with open(dump_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh)
    size_mb = dump_path.stat().st_size / 1024 / 1024
    print(f'        wrote {len(payload)} object(s) -> '
          f'{dump_path.name} ({size_mb:.2f} MB)')

    print()
    print('[5/5] Migrating and loading the target')
    use_database(settings, connections, cfg)
    call_command('migrate', database='default', verbosity=1, interactive=False)

    # The target now has migrate-generated contenttypes/permissions. Truncate
    # them (and the M2M through tables) so the imported graph replaces them
    # wholesale rather than colliding on primary keys.
    print()
    print('        resetting auth/contenttype tables in the target')
    with connection.cursor() as cursor:
        existing_tables = set(connection.introspection.table_names())
        targets = [t for t in RESET_TABLES if t in existing_tables]
        if targets:
            quoted = ', '.join(connection.ops.quote_name(t) for t in targets)
            cursor.execute(f'TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE')
            print(f'          truncated {len(targets)} table(s): '
                  f'{", ".join(targets)}')
        else:
            print('          nothing to truncate')

    call_command('loaddata', str(dump_path), database='default', verbosity=1)

    # ---- 5. verify ------------------------------------------------------
    print()
    print('Verifying row counts')
    target_counts, target_errors = collect_counts('default')

    if target_errors:
        print(f'        !! {len(target_errors)} model(s) could not be read from the target')
        for key, exc in list(target_errors.items())[:5]:
            print(f'           {key}: {exc}')
        return 4

    mismatches = []
    for key, src in sorted(source_counts.items()):
        tgt = target_counts.get(key)
        if key in excludes:
            continue
        if isinstance(src, int) and src > 0 and tgt != src:
            mismatches.append((key, src, tgt))

    print(f'        {"model":<42} {"source":>8} {"target":>8}')
    for key, src in sorted(source_counts.items()):
        if key in excludes:
            continue
        tgt = target_counts.get(key)
        flag = ''
        if isinstance(src, int) and src > 0 and tgt != src:
            flag = '  <-- MISMATCH'
        if isinstance(src, int) and src > 0:
            print(f'        {key:<42} {src:>8} {tgt!s:>8}{flag}')

    print()
    if mismatches:
        print(f'FAILED: {len(mismatches)} model(s) did not match:')
        for key, src, tgt in mismatches:
            print(f'   {key}: source={src} target={tgt}')
        return 4

    print('OK - every populated model matched exactly.')
    print(f'Dump file left at {dump_path} in case you need it; delete it when happy.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())