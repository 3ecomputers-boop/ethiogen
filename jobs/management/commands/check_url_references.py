"""
Find {% url %} references in templates that cannot be reversed.

A single unresolvable name raises NoReverseMatch *during rendering*, which
returns a 500 for the whole page -- not just the broken link. This is what
took /jobs/ down.

Run this after any URL refactor, and on the server after a deploy:

    python manage.py check_url_references

Exit code 0 = clean, 1 = broken references found.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, get_resolver, reverse

# {% url 'name' %} and {% url "name" %}
TAG = re.compile(r"\{%\s*url\s+(?:'(?P<q1>[^']+)'|\"(?P<q2>[^\"]+)\")")

SKIP_DIRS = {'venv', '.git', '__pycache__', 'node_modules', 'static',
             'media', '.idea', '.vscode'}


def resolvable_names():
    """Every registered URL name, including namespace:name."""
    names = set()

    def walk(resolver, prefix=''):
        for pattern in resolver.url_patterns:
            if hasattr(pattern, 'url_patterns'):
                namespace = getattr(pattern, 'namespace', None)
                if namespace:
                    child = f'{prefix}{namespace}:'
                else:
                    child = prefix
                walk(pattern, child)
            elif pattern.name:
                names.add(pattern.name)
                if prefix:
                    names.add(f'{prefix}{pattern.name}')

    walk(get_resolver())
    return names


class Command(BaseCommand):
    help = 'Report template {% url %} tags that cannot be reversed.'

    def add_arguments(self, parser):
        parser.add_argument('--paths', nargs='*', default=None,
                            help='Limit to these directories (relative to BASE_DIR).')

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR)
        roots = [root / p for p in options['paths']] if options['paths'] else [root]

        names = resolvable_names()
        total = 0
        broken = []

        for base in roots:
            if not base.exists():
                continue
            for path in base.rglob('*.html'):
                if any(part in SKIP_DIRS for part in path.parts):
                    continue
                text = path.read_text(encoding='utf-8', errors='replace')
                for match in TAG.finditer(text):
                    name = match.group('q1') or match.group('q2')
                    total += 1
                    line_no = text[:match.start()].count('\n') + 1
                    if name in names:
                        continue
                    try:
                        reverse(name)
                    except NoReverseMatch:
                        rel = path.relative_to(root)
                        broken.append((name, str(rel), line_no))

        self.stdout.write(f'scanned {total} {{% url %}} reference(s)')

        if not broken:
            self.stdout.write(self.style.SUCCESS(
                'OK - every url reference resolves.'))
            return

        by_name = {}
        for name, rel, line_no in broken:
            by_name.setdefault(name, []).append((rel, line_no))

        self.stdout.write(self.style.ERROR(
            f'{len(broken)} broken reference(s) in {len(by_name)} name(s):'))
        for name in sorted(by_name):
            places = by_name[name]
            self.stdout.write(self.style.ERROR(f'\n  {name}  ({len(places)} use(s))'))
            for rel, line_no in places[:15]:
                self.stdout.write(f'      {rel}:{line_no}')
            if len(places) > 15:
                self.stdout.write(f'      ... and {len(places) - 15} more')

        self.stdout.write('')
        self.stdout.write('Each of these returns HTTP 500 for the whole page.')
        raise SystemExit(1)