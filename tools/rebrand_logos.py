"""
Replace the scattered hard-coded <img> logo markup with {% brand_logo %}.

Run once:  .venv\\Scripts\\python.exe tools\\rebrand_logos.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every old logo reference, by the element that carries it.
PRELOADER = re.compile(
    r'<img\s+src="\{%\s*static\s+[\'"][^\'"]*logo[^\'"]*[\'"]\}\s*\s*alt=""\s*>',
    re.IGNORECASE,
)
HEADER = re.compile(
    r'<a\s+href="index\.html"\s*>\s*<img\s+src="\{%\s*static\s+[\'"][^\'"]*logo[^\'"]*[\'"]\}\s*'
    r'width="150px"\s*alt="[^"]*"\s*>\s*</a>',
    re.IGNORECASE,
)
FOOTER = re.compile(
    r'<a\s+href="index\.html"\s*>\s*<img\s+src="(?:\{%\s*static\s+)?[\'"]?[\w/\.\-]*logo2_footer\.png'
    r'[\'"]?\s*alt="[^"]*"\s*>\s*</a>',
    re.IGNORECASE,
)
BARE_FOOTER = re.compile(
    r'<a\s+href="index\.html"\s*>\s*<img\s+src="assets/img/logo/logo2_footer\.png"\s*alt="[^"]*"\s*>\s*</a>',
    re.IGNORECASE,
)

TARGETS = [
    'jobs/templates/base.html',
    'jobs/templates/home.html',
    'employers/templates/employers/base.html',
    'employers/templates/employers/employers.html',
    'templates/base.html',
    'templates/home.html',
]

replacements = 0

for rel in TARGETS:
    path = ROOT / rel
    if not path.exists():
        print(f'skip (missing): {rel}')
        continue

    original = path.read_text(encoding='utf-8', errors='replace')
    text = original

    # favicon / manifest-style head links
    text = re.sub(
        r'<link\s+rel="shortcut icon"[^>]*>',
        '<!-- Logo and favicon come from Billing -> Integration settings -->\n'
        '\t\t<link rel="shortcut icon" type="image/png" href="{% favicon_url %}">',
        text,
        flags=re.IGNORECASE,
    )

    text, n1 = PRELOADER.subn(
        '{% brand_logo height=40 show_caption=False css_class="mx-auto" %}', text)
    text, n2 = HEADER.subn('{% brand_logo height=54 link_url="/" %}', text)
    text, n3 = FOOTER.subn('{% brand_logo height=46 link_url="/" %}', text)
    text, n4 = BARE_FOOTER.subn('{% brand_logo height=46 link_url="/" %}', text)

    # Any straggler <img> pointing at a logo file.
    text, n5 = re.subn(
        r'<img\s+src="\{%\s*static\s+[\'"][^\'"]*logo[^\'"]*[\'"]\}\s*'
        r'(?:width="[^"]*"\s*)?alt="[^"]*"\s*/?>',
        '{% brand_logo height=46 show_caption=False %}',
        text,
    )

    total = n1 + n2 + n3 + n4 + n5
    if text == original:
        print(f'no change      : {rel}')
        continue

    if '{% load ethiogen_tags %}' not in text:
        text = re.sub(
            r'(\{%\s*load\s+static\s*%})', r'\1\n{% load ethiogen_tags %}', text, count=1
        )

    path.write_text(text, encoding='utf-8')
    replacements += total
    print(f'updated        : {rel}  ({total} logo refs)')

print(f'\n{replacements} logo references replaced across {len(TARGETS)} templates')
sys.exit(0)
