"""
Bootstrap the Ethiogen role and database on PostgreSQL.

Creates a dedicated least-privilege login and a database owned by it.
Refuses to touch any other database on the server.

    python tools/pg_bootstrap.py --admin-password <postgres-password>
"""
import argparse
import os
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

APP_ROLE = 'ethiogen'
APP_DB = 'ethiogen'


def make_password(length=28):
    alphabet = string.ascii_letters + string.digits
    # guarantee at least one of each class
    while True:
        pw = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--admin-password', required=True)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', default='5432')
    ap.add_argument('--role', default=APP_ROLE)
    ap.add_argument('--db', default=APP_DB)
    ap.add_argument('--app-password', default=None,
                    help='Set a specific app password instead of generating one.')
    ap.add_argument('--show-password', action='store_true',
                    help='Print the app password to stdout.')
    args = ap.parse_args()

    try:
        import psycopg
        from psycopg import sql
    except ImportError:
        sys.exit('psycopg is not installed. pip install "psycopg[binary]"')

    app_pw = args.app_password or make_password()

    dsn = (f"host={args.host} port={args.port} dbname=postgres "
           f"user=postgres password={args.admin_password}")
    print(f'-- connecting to {args.host}:{args.port} as postgres')

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT version()')
            print('   server:', cur.fetchone()[0].split(',')[0])

            # --- never touch anyone else's data ---
            cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false")
            existing = sorted(r[0] for r in cur.fetchall())
            print('   existing databases:', ', '.join(existing))
            if args.db in existing:
                print(f'   NOTE: database {args.db!r} already exists, reusing it')

            # --- role ---
            # NOTE: `ALTER ROLE ... PASSWORD` does not accept a bind
            # parameter, so the value has to be inlined as a properly quoted
            # literal. psycopg.sql.Literal does that escaping for us --
            # never use an f-string here.
            pw_literal = sql.Literal(app_pw)
            role_ident = sql.Identifier(args.role)

            cur.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (args.role,))
            if cur.fetchone():
                print(f'   role {args.role!r} exists -- updating its password')
                cur.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {}').format(
                    role_ident, pw_literal))
            else:
                print(f'   creating role {args.role!r}')
                cur.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(
                    role_ident, pw_literal))

            # Least privilege: the app must not create databases or roles.
            cur.execute(sql.SQL('ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE '
                                'NOINHERIT LOGIN').format(role_ident))
            print('   role privileges: NOSUPERUSER NOCREATEDB NOCREATEROLE')

            # --- database ---
            if args.db not in existing:
                print(f'   creating database {args.db!r} (UTF8, from template0)')
                cur.execute(
                    sql.SQL('CREATE DATABASE {} OWNER {} ENCODING {} '
                            'TEMPLATE {}').format(
                        sql.Identifier(args.db), role_ident,
                        sql.Literal('UTF8'), sql.Identifier('template0')))
            else:
                cur.execute(sql.SQL('ALTER DATABASE {} OWNER TO {}').format(
                    sql.Identifier(args.db), role_ident))

    # --- verify the app role actually works ---
    app_dsn = (f"host={args.host} port={args.port} dbname={args.db} "
               f"user={args.role} password={app_pw}")
    with psycopg.connect(app_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT current_user, current_database()')
            usr, db = cur.fetchone()
            cur.execute('SELECT pg_encoding_to_char(encoding) FROM pg_database '
                        'WHERE datname = current_database()')
            enc = cur.fetchone()[0]
            cur.execute("SELECT rolsuper, rolcreatedb FROM pg_roles "
                        "WHERE rolname = current_user")
            su, cdb = cur.fetchone()
    print(f'   verified: {usr}@{db} encoding={enc} superuser={su} createdb={cdb}')

    if args.show_password:
        print()
        print('APP_PASSWORD=' + app_pw)
    else:
        (ROOT / '.pg_app_password').write_text(app_pw, encoding='utf-8')
        print(f'   app password written to .pg_app_password (gitignored check below)')

    print()
    print('Add to .env:')
    print(f'   DB_ENGINE=postgresql')
    print(f'   DB_NAME={args.db}')
    print(f'   DB_USER={args.role}')
    print(f'   DB_PASSWORD={app_pw if args.show_password else "<see .pg_app_password>"}')
    print(f'   DB_HOST={args.host}')
    print(f'   DB_PORT={args.port}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())