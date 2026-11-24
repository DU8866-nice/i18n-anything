"""Read translation catalogs in the common formats into one model.

Formats: i18next / next-intl / vue-i18n / react-intl / FormatJS JSON (nested or flat),
Chrome extension messages.json, Flutter ARB, Apple .xcstrings and .strings, gettext .po/.pot,
Android strings.xml, Java .properties. Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- plural rules

CLDR_VERSION = "48"
# language -> (categories integer counts 0..1000 can select,
#              extra categories only a million or more selects,
#              extra categories only decimals select)
# Generated from Intl.PluralRules (ICU 78.3, CLDR 48); see scripts in tests/ to regenerate.
PLURALS = {
    "af": ("one other", "", ""), "am": ("one other", "", ""),
    "ar": ("zero one two few many other", "", ""), "az": ("one other", "", ""),
    "be": ("one few many", "", "other"), "bg": ("one other", "", ""), "bn": ("one other", "", ""),
    "bs": ("one few other", "", ""), "ca": ("one other", "many", ""), "cs": ("one few other", "", "many"),
    "cy": ("zero one two few many other", "", ""), "da": ("one other", "", ""), "de": ("one other", "", ""),
    "el": ("one other", "", ""), "en": ("one other", "", ""), "es": ("one other", "many", ""),
    "et": ("one other", "", ""), "eu": ("one other", "", ""), "fa": ("one other", "", ""),
    "fi": ("one other", "", ""), "fil": ("one other", "", ""), "fr": ("one other", "many", ""),
    "ga": ("one two few many other", "", ""), "gl": ("one other", "", ""), "gu": ("one other", "", ""),
    "he": ("one two other", "", ""), "hi": ("one other", "", ""), "hr": ("one few other", "", ""),
    "hu": ("one other", "", ""), "hy": ("one other", "", ""), "id": ("other", "", ""),
    "is": ("one other", "", ""), "it": ("one other", "many", ""), "ja": ("other", "", ""),
    "ka": ("one other", "", ""), "kk": ("one other", "", ""), "km": ("other", "", ""),
    "kn": ("one other", "", ""), "ko": ("other", "", ""), "ky": ("one other", "", ""),
    "lo": ("other", "", ""), "lt": ("one few other", "", "many"), "lv": ("zero one other", "", ""),
    "mk": ("one other", "", ""), "ml": ("one other", "", ""), "mn": ("one other", "", ""),
    "mr": ("one other", "", ""), "ms": ("other", "", ""), "my": ("other", "", ""),
    "nb": ("one other", "", ""), "no": ("one other", "", ""), "ne": ("one other", "", ""),
    "nl": ("one other", "", ""), "pa": ("one other", "", ""), "pl": ("one few many", "", "other"),
    "pt": ("one other", "many", ""), "ro": ("one few other", "", ""), "ru": ("one few many", "", "other"),
    "si": ("one other", "", ""), "sk": ("one few other", "", "many"), "sl": ("one two few other", "", ""),
    "sq": ("one other", "", ""), "sr": ("one few other", "", ""), "sv": ("one other", "", ""),
    "sw": ("one other", "", ""), "ta": ("one other", "", ""), "te": ("one other", "", ""),
    "th": ("other", "", ""), "tl": ("one other", "", ""), "tr": ("one other", "", ""),
    "uk": ("one few many", "", "other"), "ur": ("one other", "", ""), "uz": ("one other", "", ""),
    "vi": ("other", "", ""), "yue": ("other", "", ""), "zh": ("other", "", ""), "zu": ("one other", "", ""),
}
PLURAL_ORDER = ("zero", "one", "two", "few", "many", "other")
KNOWN_LANGS = set(PLURALS) | {"iw", "in", "zh-hans", "zh-hant"}


def language_of(locale: str) -> str:
    lang = re.split(r"[-_]", locale)[0].lower()
    return {"iw": "he", "in": "id", "nn": "nb", "fil": "fil"}.get(lang, lang)


def plural_rules(locale: str):
    """(needed, needed_for_millions, needed_for_decimals) category tuples, or None if unknown."""
    row = PLURALS.get(language_of(locale))
    if not row:
        return None
    return tuple(tuple(part.split()) for part in row)


# --------------------------------------------------------------------------- locales in paths

LOCALE_TOKEN = re.compile(
    r"^(?P<lang>[a-z]{2,3})(?:[-_](?P<script>[A-Z][a-z]{3}|[a-z]{4}))?(?:[-_](?P<region>[A-Z]{2}|[a-z]{2}|\d{3}))?$"
)


def normalize_locale(token: str) -> str | None:
    """'zh_CN' -> 'zh-CN', 'pt-br' -> 'pt-BR', 'zh-hans' -> 'zh-Hans'. None if it isn't a locale we know."""
    m = LOCALE_TOKEN.match(token)
    if not m:
        return None
    lang = m.group("lang").lower()
    if lang not in PLURALS and lang not in ("iw", "in", "nn"):
        return None
    out = lang
    if m.group("script"):
        out += "-" + m.group("script").title()
    if m.group("region"):
        out += "-" + m.group("region").upper()
    return out


def android_locale(dirname: str) -> str | None:
    """'values' -> '' (default), 'values-zh-rCN' -> 'zh-CN', 'values-b+sr+Latn' -> 'sr-Latn'."""
    if dirname == "values":
        return ""
    if not dirname.startswith("values-"):
        return None
    rest = dirname[len("values-"):]
    if rest.startswith("b+"):
        return normalize_locale(rest[2:].replace("+", "-"))
    m = re.match(r"^([a-z]{2,3})(?:-r([A-Z]{2}))?$", rest)
    if not m:
        return None  # values-night, values-v21 ...
    return normalize_locale(m.group(1) + ("-" + m.group(2) if m.group(2) else ""))


# --------------------------------------------------------------------------- model


@dataclass
class Message:
    key: str
    text: str | None = None
    plurals: dict | None = None  # category -> text
    source_text: str | None = None  # gettext: msgid / msgid_plural
    fuzzy: bool = False
    style: str = "plain"  # plain | i18next-plural | icu | android-plural | po-plural | xc-plural

    def forms(self):
        if self.plurals is not None:
            return list(self.plurals.values())
        return [self.text or ""]


@dataclass
class Catalog:
    path: str
    fmt: str
    locale: str  # '' means "the default/base file" (Android values/, base .properties, .pot)
    namespace: str
    messages: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    nplurals: int | None = None  # gettext header
    is_source: bool = False  # a base/default file, or the source language of an .xcstrings file


# --------------------------------------------------------------------------- placeholders

I18NEXT_VAR = re.compile(r"\{\{-?\s*([\w.]+)\s*(?:,[^}]*)?\}\}")
RUBY_VAR = re.compile(r"%\{(\w+)\}")
PY_VAR = re.compile(r"%\((\w+)\)[-#0 +]*\d*(?:\.\d+)?[sdifrx]")
PRINTF = re.compile(r"%(?:(\d+)\$)?[-#0 +']*\d*(?:\.\d+)?(?:hh|h|ll|l|L|z|j|t)?([sdifuxXoeEgGcp@])")
NESTING = re.compile(r"\$t\(([^)]*)\)")
CHROME_VAR = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)\$")
TAG = re.compile(r"</?([A-Za-z][\w-]*|\d+)(?:\s[^<>]*)?/?>")
BRACE_ARG = re.compile(r"\{\s*(\w+)\s*\}")
ICU_HEAD = re.compile(r"\{\s*(\w+)\s*,\s*(plural|select|selectordinal|number|date|time|spellout|ordinal)\b")


def is_icu(text: str) -> bool:
    return bool(ICU_HEAD.search(text or ""))


def _match_brace(s: str, i: int) -> int:
    """Index of the '}' that closes the '{' at s[i], honouring ICU '' quoting loosely."""
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == "'" and j + 1 < len(s) and s[j + 1] in "{}":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def parse_icu(text: str):
    """Return (argument names, {category: branch text} of the first plural, plural arg name)."""
    args, branches, parg = set(), None, None
    i = 0
    while i < len(text):
        if text[i] == "{":
            end = _match_brace(text, i)
            if end == -1:
                break
            body = text[i + 1:end]
            m = re.match(r"\s*(\w+)\s*(?:,\s*(\w+)\s*(?:,(.*))?)?$", body, re.S)
            if m:
                args.add(m.group(1))
                kind = m.group(2)
                if kind in ("plural", "selectordinal", "select") and m.group(3) is not None:
                    opts = m.group(3)
                    found = {}
                    k = 0
                    while k < len(opts):
                        mm = re.match(r"\s*(?:offset:\d+\s*)?(=?\w+)\s*\{", opts[k:])
                        if not mm:
                            break
                        start = k + mm.end() - 1
                        close = _match_brace(opts, start)
                        if close == -1:
                            break
                        found[mm.group(1)] = opts[start + 1:close]
                        sub_args, _, _ = parse_icu(opts[start + 1:close])
                        args |= sub_args
                        k = close + 1
                    if kind != "select" and branches is None:
                        branches, parg = found, m.group(1)
            i = end + 1
        else:
            i += 1
    return args, branches, parg


def placeholders(text: str) -> Counter:
    """Every interpolation token in a message, normalised so source and target can be compared."""
    text = text or ""
    out = Counter()
    if is_icu(text):
        args, _, _ = parse_icu(text)
        for a in args:
            out[f"{{{a}}}"] = 1
        stripped = text
    else:
        stripped = I18NEXT_VAR.sub(lambda m: out.update([f"{{{{{m.group(1)}}}}}"]) or " ", text)
        stripped = BRACE_ARG.sub(lambda m: out.update([f"{{{m.group(1)}}}"]) or " ", stripped)
    stripped = RUBY_VAR.sub(lambda m: out.update([f"%{{{m.group(1)}}}"]) or " ", stripped)
    stripped = PY_VAR.sub(lambda m: out.update([m.group(0)]) or " ", stripped)
    stripped = stripped.replace("%%", " ")
    # %s and %1$s are the same argument: number the plain ones in order so they compare equal
    n = 0
    for m in PRINTF.finditer(stripped):
        if m.group(1):
            pos = m.group(1)
        else:
            n += 1
            pos = str(n)
        out[f"%{pos}${'d' if m.group(2) in 'iu' else m.group(2)}"] += 1
    for m in CHROME_VAR.finditer(text):
        out[f"${m.group(1).upper()}$"] += 1
    for m in NESTING.finditer(text):
        out[f"$t({m.group(1).strip()})"] += 1
    for m in TAG.finditer(text):
        out[f"<{'/' if m.group(0).startswith('</') else ''}{m.group(1)}>"] += 1
    return out


def strip_markup(text: str) -> str:
    text = text or ""
    if is_icu(text):
        _, branches, _ = parse_icu(text)
        if branches:
            text = " ".join(branches.values())
    for rx in (I18NEXT_VAR, RUBY_VAR, PY_VAR, NESTING, TAG, BRACE_ARG, CHROME_VAR):
        text = rx.sub(" ", text)
    return PRINTF.sub(" ", text.replace("%%", " "))


SCRIPTS = {
    "zh": ("CJK",), "yue": ("CJK",), "ja": ("CJK", "HIRAGANA", "KATAKANA"), "ko": ("HANGUL",),
    "ru": ("CYRILLIC",), "uk": ("CYRILLIC",), "bg": ("CYRILLIC",), "be": ("CYRILLIC",), "mk": ("CYRILLIC",),
    "kk": ("CYRILLIC",), "ky": ("CYRILLIC",), "mn": ("CYRILLIC",), "ar": ("ARABIC",), "fa": ("ARABIC",),
    "ur": ("ARABIC",), "he": ("HEBREW",), "el": ("GREEK",), "th": ("THAI",), "hi": ("DEVANAGARI",),
    "mr": ("DEVANAGARI",), "ne": ("DEVANAGARI",), "bn": ("BENGALI",), "ta": ("TAMIL",), "te": ("TELUGU",),
    "gu": ("GUJARATI",), "pa": ("GURMUKHI",), "kn": ("KANNADA",), "ml": ("MALAYALAM",), "si": ("SINHALA",),
    "ka": ("GEORGIAN",), "hy": ("ARMENIAN",), "km": ("KHMER",), "lo": ("LAO",), "my": ("MYANMAR",),
    "am": ("ETHIOPIC",),
}


def expected_script(locale: str):
    lang = language_of(locale)
    if lang == "sr" and "Latn" in locale:
        return None
    if lang == "sr":
        return ("CYRILLIC",)
    return SCRIPTS.get(lang)


def script_share(text: str, prefixes) -> tuple:
    """(letters in an expected script, Latin letters)."""
    want = latin = 0
    for ch in text:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        if name.startswith(prefixes):
            want += 1
        elif name.startswith("LATIN"):
            latin += 1
    return want, latin


# --------------------------------------------------------------------------- parsers

PLURAL_SUFFIX = re.compile(r"^(?P<base>.+?)_(?:(?P<ord>ordinal)_)?(?P<cat>zero|one|two|few|many|other)$")


class _DupDict(dict):
    pass


def _pairs_hook(dups):
    def hook(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                dups.append(k)
            d[k] = v
        return d
    return hook


def _flatten(obj, prefix, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _flatten(v, f"{prefix}[{i}]", out)
    elif obj is None:
        out[prefix] = ""
    else:
        out[prefix] = obj if isinstance(obj, str) else json.dumps(obj)


def _group_i18next(flat: dict) -> dict:
    msgs = {}
    groups = {}
    for key, val in flat.items():
        m = PLURAL_SUFFIX.match(key)
        if m:
            base = m.group("base") + ("_ordinal" if m.group("ord") else "")
            groups.setdefault(base, {})[m.group("cat")] = val
        else:
            msgs[key] = Message(key, text=val, style="icu" if is_icu(val) else "plain")
    for base, forms in groups.items():
        if "other" in forms:
            msgs[base] = Message(base, plurals=forms, style="i18next-plural")
        else:
            # i18next always writes _other. Without it, names like "arrow_one" / "arrow_many"
            # are ordinary keys; the checker regroups them if the source has a plural here.
            for cat, val in forms.items():
                k = f"{base}_{cat}"
                msgs[k] = Message(k, text=val, style="icu" if is_icu(val) else "plain")
    return msgs


def parse_json(path: str, text: str):
    dups = []
    data = json.loads(text, object_pairs_hook=_pairs_hook(dups))
    problems = [f"duplicate key '{d}'" for d in dups]
    if not isinstance(data, dict):
        raise ValueError("top level is not an object")
    base = os.path.basename(path)
    if base == "messages.json" and data and all(isinstance(v, dict) and "message" in v for v in data.values()):
        flat = {k: v.get("message", "") for k, v in data.items()}  # Chrome extension
        return {k: Message(k, text=v) for k, v in flat.items()}, problems, "chrome-json"
    if path.endswith(".arb"):
        flat = {k: v for k, v in data.items() if not k.startswith("@") and isinstance(v, str)}
        return {k: Message(k, text=v, style="icu" if is_icu(v) else "plain") for k, v in flat.items()}, problems, "arb"
    flat = {}
    _flatten(data, "", flat)
    return _group_i18next(flat), problems, "json"


def parse_xcstrings(path: str, text: str):
    """One .xcstrings file holds every language. Returns {locale: messages}, source language."""
    data = json.loads(text)
    src = data.get("sourceLanguage", "en")
    per = {}
    for key, entry in (data.get("strings") or {}).items():
        if entry.get("shouldTranslate") is False:
            continue
        locs = entry.get("localizations") or {}
        if src not in locs:
            per.setdefault(src, {})[key] = Message(key, text=key)
        for loc, body in locs.items():
            if "stringUnit" in body:
                per.setdefault(loc, {})[key] = Message(key, text=body["stringUnit"].get("value", ""))
            elif "variations" in body and "plural" in body["variations"]:
                forms = {cat: (v.get("stringUnit") or {}).get("value", "") for cat, v in body["variations"]["plural"].items()}
                per.setdefault(loc, {})[key] = Message(key, plurals=forms, style="xc-plural")
    return per, src


def _po_unquote(s: str) -> str:
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return bytes(s, "utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")


def parse_po(path: str, text: str):
    msgs, problems = {}, []
    nplurals = None
    entries, cur, last = [], {}, None
    flags = set()
    for raw in text.splitlines() + [""]:
        line = raw.strip()
        if not line:
            if cur:
                cur["flags"] = flags
                entries.append(cur)
            cur, last, flags = {}, None, set()
            continue
        if line.startswith("#,"):
            flags |= {f.strip() for f in line[2:].split(",")}
            continue
        if line.startswith("#"):
            continue
        m = re.match(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+(".*")$', line)
        if m:
            last = m.group(1)
            cur[last] = _po_unquote(m.group(2))
        elif line.startswith('"') and last:
            cur[last] += _po_unquote(line)
    for e in entries:
        if "msgid" not in e:
            continue
        if e["msgid"] == "":
            m = re.search(r"nplurals\s*=\s*(\d+)", e.get("msgstr", ""))
            nplurals = int(m.group(1)) if m else None
            continue
        key = (e.get("msgctxt", "") + "\x04" if "msgctxt" in e else "") + e["msgid"]
        fuzzy = "fuzzy" in e["flags"]
        if "msgid_plural" in e:
            forms = {}
            i = 0
            while f"msgstr[{i}]" in e:
                forms[str(i)] = e[f"msgstr[{i}]"]
                i += 1
            msgs[key] = Message(key, plurals=forms, source_text=e["msgid_plural"], fuzzy=fuzzy, style="po-plural")
        else:
            msgs[key] = Message(key, text=e.get("msgstr", ""), source_text=e["msgid"], fuzzy=fuzzy)
    return msgs, problems, nplurals


def _inner_xml(el) -> str:
    parts = [el.text or ""]
    for child in el:
        parts.append(ET.tostring(child, encoding="unicode"))
    s = "".join(parts)
    s = re.sub(r"\s+xmlns:\w+=\"[^\"]*\"", "", s)
    if len(s) >= 2 and s[0] == s[-1] == '"':
        s = s[1:-1]
    return s.replace("\\'", "'").replace('\\"', '"')


def parse_android(path: str, text: str):
    root = ET.fromstring(text)
    msgs, problems, seen = {}, [], set()
    for el in root:
        name = el.get("name")
        if not name or el.get("translatable") == "false":
            continue
        if name in seen:
            problems.append(f"duplicate key '{name}'")
        seen.add(name)
        if el.tag == "string":
            msgs[name] = Message(name, text=_inner_xml(el))
        elif el.tag == "plurals":
            forms = {item.get("quantity"): _inner_xml(item) for item in el.findall("item")}
            msgs[name] = Message(name, plurals=forms, style="android-plural")
        elif el.tag == "string-array":
            for i, item in enumerate(el.findall("item")):
                msgs[f"{name}[{i}]"] = Message(f"{name}[{i}]", text=_inner_xml(item))
    return msgs, problems


STRINGS_LINE = re.compile(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;')


def parse_apple_strings(path: str, raw: bytes):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    msgs, problems = {}, []
    for m in STRINGS_LINE.finditer(text):
        k = m.group(1).replace('\\"', '"')
        if k in msgs:
            problems.append(f"duplicate key '{k}'")
        msgs[k] = Message(k, text=m.group(2).replace('\\"', '"').replace("\\n", "\n"))
    return msgs, problems


def parse_properties(path: str, text: str):
    msgs, problems = {}, []
    logical, buf = [], ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if not buf and (not stripped or stripped[0] in "#!"):
            continue
        if stripped.endswith("\\") and not stripped.endswith("\\\\"):
            buf += stripped[:-1]
            continue
        logical.append(buf + stripped)
        buf = ""
    for line in logical:
        m = re.match(r"^((?:[^=:\s\\]|\\.)+)\s*[=:\s]\s*(.*)$", line)
        if not m:
            continue
        key = m.group(1).replace("\\", "")
        val = re.sub(r"\\u([0-9a-fA-F]{4})", lambda x: chr(int(x.group(1), 16)), m.group(2))
        val = val.replace("\\n", "\n").replace("\\t", "\t").replace("\\:", ":").replace("\\=", "=")
        if key in msgs:
            problems.append(f"duplicate key '{key}'")
        msgs[key] = Message(key, text=val)
    return msgs, problems


# --------------------------------------------------------------------------- discovery

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", ".nuxt", "vendor", "Pods", ".venv", "venv",
             "__pycache__", "target", ".gradle", "coverage", ".turbo", "out", "DerivedData"}
NOT_CATALOGS = {"package.json", "package-lock.json", "tsconfig.json", "composer.json", "manifest.json",
                "app.json", "angular.json", "project.json", "jsconfig.json", "components.json", "vercel.json"}


def _locale_in_path(rel: str):
    """Find the locale token in a path. Returns (locale, namespace template) or (None, None)."""
    parts = rel.split("/")
    stem, ext = os.path.splitext(parts[-1])
    # The file name itself: en.json, zh-CN.json, de.po ...
    loc = normalize_locale(stem)
    if loc:
        return loc, "/".join(parts[:-1] + ["{lang}" + ext])
    # ... or its last part: app_de.arb, intl_pt_BR.arb, common.fr.json
    for sep in re.finditer(r"[_.-]", stem):  # longest valid suffix wins: zh_Hant_TW before TW
        loc = normalize_locale(stem[sep.end():])
        if loc and sep.start() > 0:
            return loc, "/".join(parts[:-1] + [stem[: sep.end()] + "{lang}" + ext])
    for i in range(len(parts) - 2, -1, -1):
        seg = parts[i]
        if seg.endswith(".lproj"):
            seg = seg[: -len(".lproj")]
            if seg == "Base":
                return "", "/".join(parts[:i] + ["{lang}.lproj"] + parts[i + 1:])
        loc = normalize_locale(seg)
        if loc:
            return loc, "/".join(parts[:i] + ["{lang}" + (".lproj" if parts[i].endswith(".lproj") else "")] + parts[i + 1:])
    return None, None


def discover(root: str):
    """Yield Catalog objects for every translation file under root."""
    root = os.path.abspath(root)
    catalogs = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            catalogs.extend(load_file(full, rel))
    return catalogs


def load_file(full: str, rel: str):
    fn = os.path.basename(rel)
    ext = os.path.splitext(fn)[1].lower()
    try:
        if ext == ".xcstrings":
            with open(full, encoding="utf-8") as fh:
                per, src = parse_xcstrings(full, fh.read())
            tmpl = rel + "#{lang}"
            return [Catalog(rel + "#" + loc, "xcstrings", loc, tmpl, msgs, is_source=(loc == src))
                    for loc, msgs in per.items()]
        if ext in (".json", ".arb"):
            loc, tmpl = _locale_in_path(rel)
            if loc is None:
                return []
            if fn in NOT_CATALOGS and "{lang}" not in tmpl.rsplit("/", 1)[0]:
                return []  # en/package.json is a namespace; a stray package.json is not
            with open(full, encoding="utf-8-sig") as fh:
                text = fh.read()
            try:
                msgs, problems, fmt = parse_json(full, text)
            except ValueError as e:
                return [Catalog(rel, "json", loc, tmpl, {}, [f"cannot parse: {e}"])]
            return [Catalog(rel, fmt, loc, tmpl, msgs, problems)]
        if ext in (".po", ".pot"):
            with open(full, encoding="utf-8") as fh:
                msgs, problems, npl = parse_po(full, fh.read())
            if ext == ".pot":
                return [Catalog(rel, "pot", "", rel, msgs, problems, npl, is_source=True)]
            loc, tmpl = _locale_in_path(rel)
            if loc is None:
                return []
            return [Catalog(rel, "po", loc, tmpl, msgs, problems, npl)]
        if ext == ".xml" and "/values" in "/" + rel and fn in ("strings.xml", "plurals.xml", "arrays.xml"):
            parent = rel.split("/")[-2]
            loc = android_locale(parent)
            if loc is None:
                return []
            tmpl = "/".join(rel.split("/")[:-2] + ["values{-lang}", fn])
            with open(full, encoding="utf-8") as fh:
                try:
                    msgs, problems = parse_android(full, fh.read())
                except ET.ParseError as e:
                    return [Catalog(rel, "android", loc, tmpl, {}, [f"cannot parse: {e}"])]
            return [Catalog(rel, "android", loc, tmpl, msgs, problems, is_source=(loc == ""))]
        if ext == ".strings":
            loc, tmpl = _locale_in_path(rel)
            if loc is None:
                return []
            with open(full, "rb") as fh:
                msgs, problems = parse_apple_strings(full, fh.read())
            return [Catalog(rel, "strings", loc, tmpl, msgs, problems, is_source=(loc == ""))]
        if ext == ".properties":
            stem = fn[: -len(ext)]
            m = re.match(r"^(.+?)_([a-z]{2,3}(?:_[A-Z]{2})?)$", stem)
            if m and normalize_locale(m.group(2)):
                loc, tmpl = normalize_locale(m.group(2)), "/".join(rel.split("/")[:-1] + [m.group(1) + "{_lang}.properties"])
            else:
                sib = [f for f in os.listdir(os.path.dirname(full)) if f.startswith(stem + "_") and f.endswith(ext)]
                if not sib:
                    return []
                loc, tmpl = "", "/".join(rel.split("/")[:-1] + [stem + "{_lang}.properties"])
            with open(full, encoding="utf-8", errors="replace") as fh:
                msgs, problems = parse_properties(full, fh.read())
            return [Catalog(rel, "properties", loc, tmpl, msgs, problems, is_source=(loc == ""))]
    except (OSError, UnicodeDecodeError, ValueError) as e:
        return [Catalog(rel, ext.lstrip("."), "?", rel, {}, [f"cannot read: {e}"])]
    return []
