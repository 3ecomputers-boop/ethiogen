"""
Audit the admin templates for tag mistakes that render as a 500.

Two bugs hit this project in a row and both were invisible until a page was
requested:

  * a multi-line {# ... #} comment. Django's {# #} is single-line only, so
    every line after the first rendered as visible page text.
  * a comment block whose prose spelled its own opening tag. Comment blocks
    do not nest -- the inner tag closed the outer block early and left an
    orphaned {% endcomment %}, which is a TemplateSyntaxError on every render.

Neither shows up in `manage.py check`, because both are only reached when the
template is actually compiled.

Run:  .venv\\Scripts\\python.exe tools\\check_admin_templates.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADMIN = ROOT / "admin_templates" / "admin"

problems = []

for path in sorted(ADMIN.glob("*.html")):
    src = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(ROOT).as_posix()

    # 1. {# ... #} that does not close on its own line
    for m in re.finditer(r"\{#", src):
        line_no = src.count("\n", 0, m.start()) + 1
        end_of_line = src.find("\n", m.start())
        line = src[m.start(): end_of_line if end_of_line > 0 else len(src)]
        if "#}" not in line:
            problems.append("%s:%d  {# not closed on this line (rest renders as text)"
                            % (rel, line_no))

    # 2. comment blocks containing their own tag name (blocks do not nest)
    for m in re.finditer(r"\{%\s*comment\s*%\}(.*?)\{%\s*endcomment\s*%\}",
                         src, re.S):
        body = m.group(1)
        if re.search(r"\{%\s*(comment|endcomment)\s*%\}", body):
            line_no = src.count("\n", 0, m.start()) + 1
            problems.append("%s:%d  comment block contains its own tag name "
                            "(Django comment blocks do not nest)"
                            % (rel, line_no))

    # 3. unbalanced block tags
    #
    # Comment bodies are stripped first. Django never parses what is inside a
    # comment block, and prose that mentions a tag by name -- "overriding
    # {% block nav-sidebar %} replaces this include" -- is exactly the sort of
    # sentence that appears in a note explaining one of these bugs. Counting it
    # reported a perfectly valid template as unbalanced.
    stripped = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", src, flags=re.S)
    # a {# ... #} comment may span lines in someone's source even though
    # Django treats it as single-line, so drop whole-line ones too
    opens = len(re.findall(r"\{%\s*(?:block|if|for|with|spaceless)\b", stripped))
    closes = len(re.findall(r"\{%\s*end(?:block|if|for|with|spaceless)\b", stripped))
    if opens != closes:
        problems.append("%s     unbalanced block tags: %d open / %d close"
                        % (rel, opens, closes))

    # 3b. a comment block that never closes leaks its whole body as page text
    if len(re.findall(r"\{%\s*comment\s*%\}", src)) != len(
            re.findall(r"\{%\s*endcomment\s*%\}", src)):
        problems.append("%s     unclosed comment block (body renders as text)"
                        % rel)

    # 4. Tailwind utility classes -- the admin ships no Tailwind
    tw = re.compile(
        r"(?:^|\s)((?:[a-z0-9]+:)*(?:bg|text|border|shadow|rounded|flex|grid|gap|"
        r"p[trblxy]?|m[trblxy]?|w|h|items|justify|space|font|leading|tracking|"
        r"animate|transition|duration|opacity|z|overflow|cursor|hover|sm|md|lg|"
        r"xl|dark|from|to|ring|truncate)-[a-z0-9][a-z0-9/\[\]().%-]*)")
    found = set()
    for m in re.finditer(r'class="([^"]*)"', src):
        for t in tw.findall(" " + m.group(1)):
            if t.strip():
                found.add(t.strip())
    # staff_dashboard ships its own stylesheet with same-named classes
    if found and path.name != "staff_dashboard.html":
        problems.append("%s     %d Tailwind class(es) do nothing in the admin: %s"
                        % (rel, len(found), ", ".join(sorted(found)[:8])))

print("Admin template audit: %s" % ADMIN.relative_to(ROOT))
print("-" * 72)
if problems:
    for p in problems:
        print("  " + p)
    print("-" * 72)
    print("%d problem(s) found." % len(problems))
    sys.exit(1)

print("  OK - no nested/multi-line comments, balanced blocks, no dead Tailwind.")
