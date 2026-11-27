from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("health/index.html", "intel/index.html")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

class PageAudit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.ids = set()
        self.duplicates = []
        self.refs = []
        self.pairs = 0
        self.bad_pairs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in VOID:
            self.stack.append(tag)
        ident = attrs.get("id")
        if ident:
            if ident in self.ids:
                self.duplicates.append(ident)
            self.ids.add(ident)
        if "data-en" in attrs or "data-ar" in attrs:
            self.pairs += 1
            en, ar = attrs.get("data-en"), attrs.get("data-ar")
            if not en or not ar or en == ar or not re.search(r"[\\u0600-\\u06ff]", ar):
                self.bad_pairs.append((tag, ident or "", en, ar))
        for key in ("href", "src"):
            value = attrs.get(key, "")
            if value:
                self.refs.append((key, value))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f"Unexpected closing tag </{tag}>")
        elif self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            self.errors.append(f"Misnested closing tag </{tag}>; open stack: {self.stack[-5:]}")
            self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]
        else:
            self.errors.append(f"Closing tag </{tag}> has no matching opening tag")

def check_reference(page, value):
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith(("data:", "mailto:", "tel:", "javascript:")):
        return None
    if value.startswith("#"):
        return None
    target = (page.parent / parsed.path).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        return f"Reference escapes repository: {value}"
    if target.is_dir():
        target = target / "index.html"
    if not target.exists():
        return f"Missing local reference: {value} (resolved to {target.relative_to(ROOT)})"
    return None

failures = []
for relative in PAGES:
    page = ROOT / relative
    if not page.exists():
        failures.append(f"{relative}: page missing")
        continue
    source = page.read_text(encoding="utf-8")
    audit = PageAudit()
    audit.feed(source)
    audit.close()
    if audit.stack:
        failures.append(f"{relative}: unclosed tags {audit.stack}")
    failures.extend(f"{relative}: {error}" for error in audit.errors)
    if audit.duplicates:
        failures.append(f"{relative}: duplicate IDs {audit.duplicates}")
    if audit.bad_pairs:
        failures.append(f"{relative}: invalid bilingual content pairs ({len(audit.bad_pairs)})")
    if audit.pairs < 40:
        failures.append(f"{relative}: expected expanded bilingual content, found only {audit.pairs} pairs")
    if source.count("<main") != 1 or source.count("</main>") != 1:
        failures.append(f"{relative}: expected exactly one main landmark")
    if source.count("<h1") != 1:
        failures.append(f"{relative}: expected exactly one H1")
    if 'data-t="stage"' not in source or "CONCEPT STAGE" not in source:
        failures.append(f"{relative}: concept-stage status is missing")
    if not re.search(r'product-pages\\.js[\\s\\S]*product-expansion\\.js', source):
        failures.append(f"{relative}: language scripts are missing or in the wrong order")
    if "product-expansion.css" not in source:
        failures.append(f"{relative}: expansion stylesheet is not linked")
    for key, value in audit.refs:
        issue = check_reference(page, value)
        if issue:
            failures.append(f"{relative}: {issue}")
    print(f"PASS {relative}: {audit.pairs} bilingual elements, {len(audit.refs)} local/external references checked")

if failures:
    print("\\n".join(f"FAIL {item}" for item in failures))
    sys.exit(1)
print("All MADAAR HEALTH and INTEL page checks passed.")
