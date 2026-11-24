#!/usr/bin/env python3
"""pseudo: make a pseudo-locale from your source catalog, to find what is still hardcoded.

    python3 pseudo.py locales/en/translation.json          # writes locales/en-XA/translation.json
    python3 pseudo.py res/values/strings.xml --rtl         # writes res/values-ar-rXB/strings.xml
    python3 pseudo.py messages.pot --out locale/en_XA/LC_MESSAGES/messages.po

"Save changes" becomes "⟦Šåṽé çĥåñĝéš ·····⟧": still readable, about 40% longer, with brackets
that show where each string starts and ends. Run the app in that locale and every piece of plain
English left on screen is a string nobody extracted. Long German or Finnish text will overflow
the same places the padding does. Placeholders, markup and ICU syntax are left untouched.

Formats: i18next / next-intl / vue-i18n / FormatJS JSON, ARB, Chrome messages.json, gettext
.po/.pot, Android strings.xml, Apple .strings, Java .properties. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalogs as C  # noqa: E402

__version__ = "0.1.0"

ACCENTS = dict(zip(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "åƀçđéƒĝĥîĵķļɱñöþǫŕšţûṽŵẋýžÅƁÇĐÉƑĜĤÎĴĶĻṀÑÖÞǪŔŠŢÛṼŴẊÝŽ",
))
OPEN, CLOSE, PAD = "⟦", "⟧", "·"
RLO, PDF = "\u202e", "\u202c"

PROTECT = re.compile("|".join([
    C.I18NEXT_VAR.pattern, C.RUBY_VAR.pattern, C.PY_VAR.pattern, r"%%", C.PRINTF.pattern, C.NESTING.pattern,
    C.TAG.pattern, C.CHROME_VAR.pattern, r"\{\s*\w+\s*\}", r"&[a-zA-Z]+;|&#\d+;", r"\\[nt'\"]", r"https?://\S+",
]))


def _accent(s: str) -> str:
    return "".join(ACCENTS.get(ch, ch) for ch in s)


def _plain(text: str) -> str:
    out, pos = [], 0
    for m in PROTECT.finditer(text):
        out.append(_accent(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_accent(text[pos:]))
    return "".join(out)


def _icu(text: str) -> str:
    """Accent the literal text of an ICU message, branch by branch."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "{":
            end = C._match_brace(text, i)
            if end == -1:
                out.append(text[i:])
                break
            body = text[i + 1:end]
            m = re.match(r"(\s*\w+\s*,\s*(?:plural|select|selectordinal)\s*,)(.*)$", body, re.S)
            if m:
                head, opts = m.group(1), m.group(2)
                rebuilt, k = [], 0
                while k < len(opts):
                    mm = re.match(r"(\s*(?:offset:\d+\s*)?=?\w+\s*)\{", opts[k:])
                    if not mm:
                        rebuilt.append(opts[k:])
                        break
                    start = k + mm.end() - 1
                    close = C._match_brace(opts, start)
                    rebuilt.append(mm.group(1) + "{" + _icu(opts[start + 1:close]) + "}")
                    k = close + 1
                out.append("{" + head + "".join(rebuilt) + "}")
            else:
                out.append(text[i:end + 1])
            i = end + 1
        else:
            j = text.find("{", i)
            j = len(text) if j == -1 else j
            out.append(_plain(text[i:j]))
            i = j
    return "".join(out)


def pseudo(text: str, rtl: bool = False, expand: float = 0.4) -> str:
    if not isinstance(text, str) or not text.strip():
        return text
    body = _icu(text) if C.is_icu(text) else _plain(text)
    visible = len(C.strip_markup(text).strip())
    pad = PAD * max(1, round(visible * expand)) if visible else ""
    out = f"{OPEN}{body}{' ' + pad if pad else ''}{CLOSE}"
    return f"{RLO}{out}{PDF}" if rtl else out


# --------------------------------------------------------------------------- writers


def _map_json(obj, fn, skip_meta=False):
    if isinstance(obj, dict):
        return {k: (v if (skip_meta and k.startswith("@")) else _map_json(v, fn, skip_meta)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_map_json(v, fn, skip_meta) for v in obj]
    if isinstance(obj, str):
        return fn(obj)
    return obj


def convert_json(text, path, fn, locale):
    data = json.loads(text)
    if os.path.basename(path) == "messages.json" and all(isinstance(v, dict) and "message" in v for v in data.values()):
        out = {k: dict(v, message=fn(v["message"])) for k, v in data.items()}
    elif path.endswith(".arb"):
        out = _map_json(data, fn, skip_meta=True)
        out["@@locale"] = locale.replace("-", "_")
    else:
        out = _map_json(data, fn)
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def _po_quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def convert_po(text, fn, locale):
    msgs, _, _ = C.parse_po("", text)
    lines = ['msgid ""', 'msgstr ""', _po_quote(f"Language: {locale.replace('-', '_')}\n"),
             _po_quote("MIME-Version: 1.0\n"), _po_quote("Content-Type: text/plain; charset=UTF-8\n"),
             _po_quote("Plural-Forms: nplurals=2; plural=(n != 1);\n"), ""]
    for key, m in msgs.items():
        ctx, _, msgid = key.rpartition("\x04")
        if ctx:
            lines.append(f"msgctxt {_po_quote(ctx)}")
        lines.append(f"msgid {_po_quote(msgid)}")
        if m.plurals is not None:
            lines.append(f"msgid_plural {_po_quote(m.source_text or msgid)}")
            lines.append(f"msgstr[0] {_po_quote(fn(msgid))}")
            lines.append(f"msgstr[1] {_po_quote(fn(m.source_text or msgid))}")
        else:
            lines.append(f"msgstr {_po_quote(fn(msgid))}")
        lines.append("")
    return "\n".join(lines)


def convert_android(text, fn):
    root = ET.fromstring(text)

    def walk(el):
        if el.text and el.text.strip():
            el.text = fn(el.text)
        for child in el:
            walk(child)
            if child.tail and child.tail.strip():
                child.tail = fn(child.tail)

    for el in root:
        if el.get("translatable") == "false":
            continue
        if el.tag == "string":
            walk(el)
        elif el.tag in ("plurals", "string-array"):
            for item in el.findall("item"):
                walk(item)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def convert_strings(raw, fn):
    text = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
    return C.STRINGS_LINE.sub(lambda m: f'"{m.group(1)}" = "{fn(m.group(2))}";', text)


def convert_properties(text, fn):
    out = []
    for line in text.splitlines():
        m = re.match(r"^(\s*(?:[^=:\s\\#!]|\\.)+\s*[=:]\s*)(.*)$", line)
        if m and not line.lstrip().startswith(("#", "!")):
            out.append(m.group(1) + fn(m.group(2)).encode("ascii", "backslashreplace").decode("ascii")
                       .replace("\\x", "\\u00"))
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def default_out(path, locale):
    parts = path.replace(os.sep, "/").split("/")
    if path.endswith(".xml"):
        lang, _, region = locale.partition("-")
        parts[-2] = f"values-{lang}" + (f"-r{region}" if region else "")
        return "/".join(parts)
    if path.endswith(".properties"):
        stem = parts[-1][: -len(".properties")]
        stem = re.sub(r"_[a-z]{2,3}(?:_[A-Z]{2})?$", "", stem)
        parts[-1] = f"{stem}_{locale.replace('-', '_')}.properties"
        return "/".join(parts)
    if path.endswith(".pot"):
        return "/".join(parts[:-1] + [locale.replace("-", "_"), "LC_MESSAGES", parts[-1][:-4] + ".po"])
    rel = "/".join(parts)
    loc, tmpl = C._locale_in_path(rel)
    if loc is not None and tmpl and "{lang}" in tmpl:
        return tmpl.replace("{lang}", locale)
    stem, ext = os.path.splitext(parts[-1])
    parts[-1] = f"{stem}.{locale}{ext}"
    return "/".join(parts)


def convert(path, rtl=False, locale=None, expand=0.4):
    locale = locale or ("ar-XB" if rtl else "en-XA")
    fn = lambda s: pseudo(s, rtl=rtl, expand=expand)  # noqa: E731
    ext = os.path.splitext(path)[1].lower()
    if ext == ".strings":
        with open(path, "rb") as fh:
            return convert_strings(fh.read(), fn), locale
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    if ext in (".json", ".arb"):
        return convert_json(text, path, fn, locale), locale
    if ext in (".po", ".pot"):
        return convert_po(text, fn, locale), locale
    if ext == ".xml":
        return convert_android(text, fn), locale
    if ext == ".properties":
        return convert_properties(text, fn), locale
    raise ValueError(f"don't know how to read {ext} files")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pseudo", description="Write a pseudo-locale catalog from a source catalog.")
    ap.add_argument("source", help="the source-language catalog file")
    ap.add_argument("--out", help="where to write it (default: next to the source, under the pseudo locale)")
    ap.add_argument("--rtl", action="store_true", help="right-to-left pseudo-locale (ar-XB) to test mirrored layouts")
    ap.add_argument("--locale", help="locale code to write under (default en-XA, or ar-XB with --rtl)")
    ap.add_argument("--expand", type=float, default=0.4, help="how much longer to make each string (default 0.4)")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing a file")
    args = ap.parse_args(argv)
    try:
        out_text, locale = convert(args.source, args.rtl, args.locale, args.expand)
    except (ValueError, OSError, ET.ParseError) as e:
        print(f"pseudo: {e}", file=sys.stderr)
        return 2
    if args.stdout:
        sys.stdout.write(out_text)
        return 0
    out = args.out or default_out(args.source, locale)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(out_text)
    print(f"wrote {out} ({locale})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
