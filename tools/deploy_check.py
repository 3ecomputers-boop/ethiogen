"""
Deploy verification -- answers "is the reverse('home') fix actually live?"

Run this ON THE SERVER:

    python tools/deploy_check.py

It checks behaviour (what actually reverses) and content (what the files on
disk actually contain), because the two can disagree when a deploy copied
some files but not others.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

problems = []
notes = []


def ok(label, detail=''):
    print(f'  PASS  {label}' + (f'  -- {detail}' if detail else ''))


def bad(label, detail=''):
    problems.append(label)
    print(f'  FAIL  {label}' + (f'  -- {detail}' if detail else ''))


print('=' * 68)
print('Ethiogen deploy check')
print('=' * 68)
print(f'project root : {ROOT}')

# ---------------------------------------------------------------- versions
print()
try:
    import django

    print(f'Django       : {django.get_version()}')
    print(f'Python       : {sys.version.split()[0]}')
except Exception as exc:
    print(f'could not import Django: {exc}')
    raise SystemExit('Cannot continue without Django.')

# Settings must be configured before anything touches the URL resolver.
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_portal.settings')
try:
    import django as _dj

    _dj.setup()
except Exception as exc:
    print(f'could not configure settings: {exc!r}')
    raise SystemExit('Cannot continue without configured settings.')

# ---------------------------------------------------------------- behaviour
print()
print('--- behaviour: what actually reverses right now ---')
from django.conf import settings  # noqa: E402
from django.urls import NoReverseMatch, reverse  # noqa: E402

try:
    url = reverse('home')
    ok("reverse('home') resolves", url)
except NoReverseMatch:
    bad("reverse('home') resolves",
        "THIS IS THE PRODUCTION ERROR -- every page using a base template "
        "with a bare {% url 'home' %} is returning HTTP 500")

for name in ('list_jobs', 'browse_job_seekers', 'employers',
             'freelancingjobs', 'register', 'login', 'logout'):
    try:
        reverse(name)
        ok(f"reverse({name!r})")
    except NoReverseMatch:
        bad(f"reverse({name!r})")

try:
    print(f'database     : {settings.DATABASES["default"]["ENGINE"]}')
except Exception:
    pass

# ---------------------------------------------------------------- content
print()
print('--- content: what the files on disk actually contain ---')

urls_file = ROOT / 'job_portal' / 'urls.py'
if not urls_file.exists():
    bad('job_portal/urls.py exists')
else:
    src = urls_file.read_text(encoding='utf-8', errors='replace')
    if 'include((jobs_urls.urlpatterns, None))' in src:
        ok('urls.py has the unnamespaced jobs include (the fix)')
    elif "include('jobs.urls')" in src:
        bad('urls.py has the unnamespaced jobs include (the fix)',
            "found include('jobs.urls') -- this is the OLD file. "
            'Only the jobs namespace is registered, so reverse("home") '
            'cannot work.')
    else:
        notes.append('urls.py does not look like either known version -- '
                     'read it manually.')

base_files = list((ROOT / 'jobs' / 'templates').glob('base*.html')) + \
             list((ROOT / 'templates').glob('base*.html'))
BARE = re.compile(r"\{%\s*url\s+(?:'[^']+'|\"[^\"]+\")\s*%\}")

for path in base_files:
    rel = path.relative_to(ROOT)
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception as exc:
        bad(f'{rel} readable', repr(exc))
        continue
    bare = []
    for match in BARE.finditer(text):
        line_no = text[:match.start()].count('\n') + 1
        bare.append((line_no, match.group(0)))
    if bare:
        bad(f'{rel} has no bare {{% url %}} tags',
            f'{len(bare)} left, e.g. line {bare[0][0]}: {bare[0][1]}')
    else:
        ok(f'{rel} has no bare {{% url %}} tags')

# ---------------------------------------------------------------- audit
print()
print('--- full template audit ---')
try:
    from django.core.management import call_command
    from io import StringIO

    buf = StringIO()
    try:
        call_command('check_url_references', stdout=buf)
        for line in buf.getvalue().strip().splitlines():
            print(f'  {line}')
    except SystemExit:
        for line in buf.getvalue().strip().splitlines():
            print(f'  {line}')
        problems.append('check_url_references reported broken references')
except Exception as exc:
    notes.append(f'check_url_references unavailable: {exc!r}')

# ---------------------------------------------------------------- verdict
print()
print('=' * 68)
if problems:
    print(f'RESULT: {len(problems)} problem(s). The site is NOT fully fixed.')
    for p in problems:
        print(f'  - {p}')
    print()
    print('Most likely cause: the fix is correct locally but the files on the')
    print('server are stale. Upload these two files and restart the app:')
    print('    job_portal/urls.py')
    print('    jobs/templates/base.html')
    print()
    print('Or commit and push, then git pull on the server.')
    raise SystemExit(1)

for n in notes:
    print(f'NOTE  {n}')
print('RESULT: all good. reverse("home") works and no template can 500 on a URL.')
raise SystemExit(0)