#!/usr/bin/env python3
"""find_strings: list user-facing text that is still hardcoded in source files.

    python3 find_strings.py [ROOT] [--json] [--fail]

Looks at JSX/TSX, Vue, Svelte, Astro and HTML templates, plain JS/TS DOM code, Android layouts,
Jetpack Compose and Android views, UIKit, and Flutter. It is a regex scan, so read each hit:
some are not user-facing (log lines, test data) and a few real strings will be missed. Run the
app in the pseudo-locale afterwards to catch what this scan cannot see.

SwiftUI is skipped on purpose: Text("Hello") is already a localization key there.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

__version__ = "0.1.0"

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", ".nuxt", ".svelte-kit", "vendor", "Pods", ".venv",
             "venv", "__pycache__", "target", ".gradle", "coverage", ".turbo", "out",
             "__tests__", "__mocks__", "test", "tests", "spec", "e2e", "fixtures", "stories", "locales", "i18n", "l10n"}
SKIP_FILE = re.compile(r"\.(test|spec|stories|story|d)\.[jt]sx?$|\.min\.js$")

TEMPLATE_EXT = {".jsx", ".tsx", ".vue", ".svelte", ".astro", ".html", ".htm", ".hbs", ".njk", ".erb", ".ejs"}
SCRIPT_EXT = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}

ATTRS = ("placeholder", "title", "alt", "aria-label", "aria-description", "aria-placeholder", "label", "helperText",
         "tooltip", "description", "confirmText", "cancelText", "okText", "emptyText", "errorMessage", "subtitle",
         "heading", "caption", "buttonText", "submitText")
ATTR_RE = re.compile(r"(?<![\w:-])(" + "|".join(re.escape(a) for a in ATTRS) + r")\s*=\s*(\"([^\"{}]*)\"|'([^'{}]*)')")
# an opening tag may hold {expressions} with '>' in them (onClick={() => go()}), one level of nesting
_ATTRS_BODY = r"(?:[^<>{}]|\{(?:[^{}]|\{[^{}]*\})*\})*?"
TEXT_AFTER_TAG = re.compile(r"(<[A-Za-z][\w.:-]*(?:\s" + _ATTRS_BODY + r")?/?>|</[A-Za-z][\w.:-]*\s*>|\})([^<>{}]+?)(?=<|\{)", re.S)
DOM_ASSIGN = re.compile(r"\.(textContent|innerText|placeholder|title|ariaLabel)\s*=\s*(['\"`])((?:(?!\2).){2,})\2")
DOM_CALLS = re.compile(r"\b(alert|confirm|prompt|toast(?:\.\w+)?|notify|message\.(?:success|error|info|warning))\(\s*(['\"`])((?:(?!\2).){2,})\2")
DOC_TITLE = re.compile(r"document\.title\s*=\s*(['\"`])((?:(?!\1).){2,})\1")

ANDROID_XML_ATTR = re.compile(r"android:(text|hint|contentDescription|title|summary|label)\s*=\s*\"([^\"@?][^\"]*)\"")
KOTLIN = re.compile(r"\b(Text|Button|Toast\.makeText\([^,]+,|setText|setTitle|setMessage|\.text\s*=|title\s*=|label\s*=\s*\{?\s*Text)\s*\(?\s*\"((?:[^\"\\$]|\\.)+)\"")
UIKIT = re.compile(r"\.(text|title|placeholder|accessibilityLabel)\s*=\s*\"((?:[^\"\\]|\\.)+)\"|setTitle\(\s*\"((?:[^\"\\]|\\.)+)\"")
DART = re.compile(r"\b(Text|Tooltip|SnackBar\(content:\s*Text|hintText:|labelText:|helperText:|errorText:|tooltip:|title:\s*(?:const\s+)?Text)\s*\(?\s*(?:const\s+)?(['\"])((?:(?!\2).)+)\2")


def looks_like_text(s: str, text_node: bool = False) -> bool:
    s = re.sub(r"&[a-z]+;|&#\d+;", " ", s).strip()
    if not s or len(s) > 300:
        return False
    words = re.findall(r"[^\W\d_]{2,}", s)
    if not words:
        return False
    if re.fullmatch(r"[\w./:#?=&%-]+", s) and (" " not in s):
        # one token: a URL, class name, identifier or key. Keep capitalised words like "Save" or "OK".
        if re.fullmatch(r"[A-Z][a-z]+|[A-Z]{2,4}|[A-Z][a-z]+[.!?:]", s):
            return True
        if text_node and re.fullmatch(r"[^\W\d_]{2,}[.!?:]?", s) and not re.search(r"[a-z][A-Z]", s):
            return True  # "items", "or", "días" between tags; camelCase stays out
        return False
    if re.fullmatch(r"[a-z0-9_-]+(\s+[a-z0-9_-]+)*", s) and ("-" in s or "_" in s):
        return False  # "btn btn-primary"
    return True


def _line_col(text, pos):
    line = text.count("\n", 0, pos) + 1
    col = pos - (text.rfind("\n", 0, pos) + 1) + 1
    return line, col


def _template_part(path, text):
    if path.endswith((".vue", ".svelte")):
        m = re.search(r"<template[^>]*>(.*)</template>", text, re.S)
        if m:
            return m.start(1), m.group(1)
        if path.endswith(".vue"):
            return 0, ""
    if path.endswith(".astro"):
        parts = text.split("---")
        if len(parts) >= 3:
            return len("---".join(parts[:2])) + 3, "---".join(parts[2:])
    return 0, text


def scan_text(path: str, text: str):
    ext = os.path.splitext(path)[1].lower()
    hits = []

    def add(pos, kind, s):
        s = " ".join(s.split())
        if looks_like_text(s, text_node=(kind == "text")):
            line, col = _line_col(text, pos)
            hits.append({"path": path, "line": line, "col": col, "kind": kind, "text": s})

    code_like = re.compile(r";|=>|==|&&|\|\||\breturn\b|\bfunction\b|\bconst\b|\blet\b|=\s")
    if ext in TEMPLATE_EXT or ext in (".js", ".mjs", ".cjs"):
        # .js can hold JSX or HTML in template literals; plain .ts is skipped (generics look like tags)
        strict = ext not in TEMPLATE_EXT
        offset, body = _template_part(path, text)
        # drop comments, <script>/<style>/<code>/<pre> blocks and {expressions} so they aren't read as text
        masked = re.sub(r"<!--.*?-->|<(script|style|code|pre)\b.*?</\1\s*>|\{/\*.*?\*/\}",
                        lambda m: " " * len(m.group(0)), body, flags=re.S)
        for m in TEXT_AFTER_TAG.finditer(masked):
            tag = m.group(1)
            if re.match(r"</?(?:svg|path|g|style|script)\b", tag):
                continue
            if (strict or tag == "}") and (code_like.search(m.group(2)) or re.search(r"[()\[\]]\s*$|^\s*[).,:?]", m.group(2))):
                continue
            add(offset + m.start(2) + (len(m.group(2)) - len(m.group(2).lstrip())), "text", m.group(2))
        for m in ATTR_RE.finditer(masked):
            add(offset + m.start(), f"attr:{m.group(1)}", m.group(3) if m.group(3) is not None else m.group(4))
    if ext in SCRIPT_EXT or ext in (".vue", ".svelte"):
        for rx, kind_i, text_i in ((DOM_ASSIGN, 1, 3), (DOM_CALLS, 1, 3)):
            for m in rx.finditer(text):
                if "${" in m.group(text_i):
                    continue
                add(m.start(), m.group(kind_i), m.group(text_i))
        for m in DOC_TITLE.finditer(text):
            add(m.start(), "document.title", m.group(2))
    if ext == ".xml" and "/res/layout" in "/" + path.replace(os.sep, "/") or (ext == ".xml" and "/res/menu" in path):
        for m in ANDROID_XML_ATTR.finditer(text):
            add(m.start(), f"android:{m.group(1)}", m.group(2))
    if ext in (".kt", ".java"):
        for m in KOTLIN.finditer(text):
            add(m.start(), "kotlin", m.group(2))
    if ext in (".swift", ".m"):
        for m in UIKIT.finditer(text):
            add(m.start(), "uikit", m.group(2) or m.group(3))
    if ext == ".dart":
        for m in DART.finditer(text):
            if "$" in m.group(3):
                continue
            add(m.start(), "flutter", m.group(3))
    # a hit inside an obvious i18n call on the same line is a false alarm
    out = []
    lines = text.splitlines()
    for h in hits:
        src_line = lines[h["line"] - 1] if h["line"] - 1 < len(lines) else ""
        if re.search(r"(?:\bt|\$t|i18n\.t|intl\.formatMessage|formatMessage|gettext|_)\(\s*['\"`]" + re.escape(h["text"][:20]), src_line):
            continue
        if "data-i18n-ignore" in src_line or "i18n-ignore" in src_line:
            continue
        out.append(h)
    return out


def scan(root: str):
    root = os.path.abspath(root)
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEMPLATE_EXT | SCRIPT_EXT | {".xml", ".kt", ".java", ".swift", ".m", ".dart"}:
                continue
            if SKIP_FILE.search(fn):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                with open(full, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            if max((len(l) for l in text.splitlines()), default=0) > 1000:
                continue  # minified or generated
            hits.extend(scan_text(rel, text))
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(prog="find_strings", description="List hardcoded user-facing strings.")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail", action="store_true", help="exit 1 if anything is found (for CI)")
    args = ap.parse_args(argv)
    hits = scan(args.root)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except (ValueError, OSError):
            pass
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=1))
    else:
        for h in hits:
            print(f"{h['path']}:{h['line']}:{h['col']}  {h['kind']:<16} {h['text']}")
        files = len({h['path'] for h in hits})
        print(f"\n{len(hits)} hardcoded string(s) in {files} file(s)" if hits else "No hardcoded strings found.")
    return 1 if (args.fail and hits) else 0


if __name__ == "__main__":
    sys.exit(main())
