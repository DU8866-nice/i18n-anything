#!/usr/bin/env python3
"""i18n_check: prove a translation is complete before you ship it.

    python3 i18n_check.py [ROOT] [--source en] [--json] [--strict]

Finds every translation catalog under ROOT (i18next/next-intl/vue-i18n/FormatJS JSON, ARB,
Chrome messages.json, .xcstrings, .strings, gettext .po, Android strings.xml, .properties),
compares each language with the source language and reports:

  missing keys, empty strings, placeholders that were dropped, renamed or invented, markup tags
  that don't match, plural forms the language needs but doesn't have (CLDR rules), ICU plurals
  without 'other', fuzzy or empty gettext entries, strings left in the source language, stale keys.

Exit codes: 0 no errors, 1 errors (or warnings with --strict), 2 nothing to check.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalogs as C  # noqa: E402

__version__ = "0.1.1"


@dataclass
class Issue:
    level: str  # error | warning
    code: str
    locale: str
    path: str
    key: str
    message: str

    def as_dict(self):
        return self.__dict__.copy()


LANG_NAMES = {
    "ar": "Arabic", "cs": "Czech", "cy": "Welsh", "de": "German", "en": "English", "es": "Spanish",
    "fr": "French", "ga": "Irish", "he": "Hebrew", "hr": "Croatian", "it": "Italian", "ja": "Japanese",
    "ko": "Korean", "lt": "Lithuanian", "lv": "Latvian", "pl": "Polish", "pt": "Portuguese", "ro": "Romanian",
    "ru": "Russian", "sk": "Slovak", "sl": "Slovenian", "sr": "Serbian", "uk": "Ukrainian", "zh": "Chinese",
    "be": "Belarusian", "bs": "Bosnian", "ca": "Catalan", "tr": "Turkish", "nl": "Dutch", "sv": "Swedish",
    "vi": "Vietnamese", "th": "Thai", "id": "Indonesian", "hi": "Hindi", "fa": "Persian",
}


def lang_name(locale):
    return LANG_NAMES.get(C.language_of(locale), locale)


def _fmt_set(tokens):
    return ", ".join(sorted(tokens)) if tokens else "none"


class Checker:
    def __init__(self, allow=(), ignore_extra=False):
        # "Term" applies to every language; "fr: Total" only to French.
        self.allow, self.allow_by_lang = set(), defaultdict(set)
        for a in allow:
            loc, sep, term = a.partition(":")
            if sep and C.normalize_locale(loc.strip()) and term.strip():
                self.allow_by_lang[loc.strip().lower()].add(term.strip().lower())
            else:
                self.allow.add(a.strip().lower())
        self.ignore_extra = ignore_extra
        self.issues: list[Issue] = []

    def add(self, level, code, cat, key, msg):
        self.issues.append(Issue(level, code, cat.locale or "(base)", cat.path, key, msg))

    # ----------------------------------------------------------------- helpers

    def _allowed(self, text, locale=""):
        words = [w for w in C.strip_markup(text).replace("/", " ").split() if any(ch.isalpha() for ch in w)]
        scoped = self.allow | self.allow_by_lang.get(C.language_of(locale), set()) | self.allow_by_lang.get(locale.lower(), set())
        return bool(words) and all(w.strip(".,:;!?()[]\"'").lower() in scoped for w in words)

    def _untranslated(self, cat, key, src_text, tgt_text, form=""):
        where = f" ({form})" if form else ""
        visible = C.strip_markup(src_text).strip()
        letters = sum(ch.isalpha() for ch in visible)
        if letters < 3 or self._allowed(tgt_text, cat.locale):
            return
        if tgt_text == src_text and letters >= 4 and C.language_of(cat.locale) != C.language_of(self.src_locale):
            self.add("warning", "untranslated", cat, key, f"same as the source{where}: {_short(tgt_text)}")
            return
        script = C.expected_script(cat.locale)
        latin_words = [w for w in C.strip_markup(tgt_text).split() if any("a" <= ch.lower() <= "z" for ch in w)]
        if script and not all(re.fullmatch(r"[A-Z0-9.+&/-]{2,6}|\S*[0-9+]\S*|[A-Za-z]+[A-Z]\w*", w) for w in latin_words):
            want, latin = C.script_share(C.strip_markup(tgt_text), script)
            if want == 0 and latin >= 3:
                self.add("warning", "wrong-script", cat, key,
                         f"no {lang_name(cat.locale)} script in the translation{where}: {_short(tgt_text)}")

    def _placeholders(self, cat, key, src_texts, tgt_text, form="", must_have=None):
        """Every token in the target must exist in the source; must_have tokens must all be present."""
        src_tokens = set()
        for t in src_texts:
            src_tokens |= set(C.placeholders(t))
        tgt = C.placeholders(tgt_text)
        where = f" in '{form}'" if form else ""
        invented = set(tgt) - src_tokens
        lost = set(must_have or ()) - set(tgt)
        renamed = {t for t in invented if not t.startswith("<")}
        gone = {t for t in lost if not t.startswith("<")}
        if renamed and gone:
            self.add("error", "placeholder", cat, key,
                     f"placeholder changed{where}: {_fmt_set(gone)} became {_fmt_set(renamed)}; keep it exactly as in the source")
            invented -= renamed
            must_have = set(must_have) - gone
        if invented:
            tags = {t for t in invented if t.startswith("<")}
            if tags:
                self.add("error", "markup", cat, key, f"markup not in the source{where}: {_fmt_set(tags)}")
            rest = invented - tags
            if rest:
                self.add("error", "placeholder", cat, key,
                         f"placeholder not in the source{where}: {_fmt_set(rest)} (source has {_fmt_set(src_tokens)})")
        if must_have is not None:
            lost = set(must_have) - set(tgt)
            tags = {t for t in lost if t.startswith("<")}
            if tags:
                self.add("error", "markup", cat, key, f"markup dropped{where}: {_fmt_set(tags)}")
            if lost - tags:
                self.add("error", "placeholder", cat, key, f"placeholder dropped{where}: {_fmt_set(lost - tags)}")

    def _plural_forms(self, cat, key, forms, kind):
        rules = C.plural_rules(cat.locale)
        if not rules:
            return
        needed, big, dec = rules
        everything = set(needed) | set(big) | set(dec)
        have = {f for f in forms if not f.startswith("=")}
        name = lang_name(cat.locale)
        missing = [c for c in needed if c not in have]
        if kind == "icu" and "other" not in have:
            self.add("error", "plural", cat, key, "ICU plural has no 'other' branch, so the message fails to format")
            missing = [c for c in missing if c != "other"]
        if missing:
            self.add("error", "plural", cat, key,
                     f"{name} needs {', '.join(needed)}; missing {', '.join(missing)}")
        miss_big = [c for c in big if c not in have]
        if miss_big:
            self.add("warning", "plural-large", cat, key,
                     f"{name} needs '{miss_big[0]}' for counts of 1,000,000 and up")
        miss_dec = [c for c in dec if c not in have]
        if miss_dec:
            self.add("warning", "plural-decimal", cat, key,
                     f"{name} uses '{', '.join(miss_dec)}' for decimals (1.5); add it if counts can be fractional")
        # 'zero' is left alone: i18next and ICU (=0) can use it as an extra form in any language.
        never = [c for c in C.PLURAL_ORDER if c in have and c not in everything and c != "zero"]
        if never and kind != "icu":
            self.add("warning", "plural-unused", cat, key,
                     f"{name} never uses {', '.join(never)}; those forms are dead text")

    # ----------------------------------------------------------------- comparisons

    def compare(self, src, tgt):
        self.src_locale = src.locale or "en"
        consumed = set()
        for key, sm in src.messages.items():
            tm = tgt.messages.get(key)
            if tm is None and sm.style == "i18next-plural":
                # the translation has key_one/key_few but no key_other: still a plural, just incomplete
                forms = {c: tgt.messages[f"{key}_{c}"].text for c in C.PLURAL_ORDER if f"{key}_{c}" in tgt.messages}
                if forms:
                    tm = C.Message(key, plurals=forms, style="i18next-plural")
                    consumed |= {f"{key}_{c}" for c in forms}
            if tm is None:
                self.add("error", "missing", tgt, key, f"not translated: {_short(_text_of(sm))}")
                continue
            self.compare_message(tgt, key, sm, tm)
        if not self.ignore_extra:
            for key in tgt.messages:
                if key not in src.messages and key not in consumed:
                    self.add("warning", "extra", tgt, key, "not in the source; stale or misspelled key")

    def compare_message(self, tgt, key, sm, tm):
        src_icu = sm.text is not None and C.is_icu(sm.text)
        if sm.plurals is not None or (src_icu and C.parse_icu(sm.text)[1]):
            src_forms = sm.plurals if sm.plurals is not None else C.parse_icu(sm.text)[1]
            if tm.plurals is not None:
                tgt_forms, kind = tm.plurals, "forms"
            elif tm.text is not None and C.is_icu(tm.text) and C.parse_icu(tm.text)[1] is not None:
                tgt_forms, kind = C.parse_icu(tm.text)[1], "icu"
            else:
                self.add("error", "plural", tgt, key, "the source has plural forms; the translation is a single string")
                return
            self._plural_forms(tgt, key, tgt_forms, kind)
            src_other = src_forms.get("other") or list(src_forms.values())[-1]
            for form, text in tgt_forms.items():
                if not (text or "").strip():
                    self.add("error", "empty", tgt, key, f"plural form '{form}' is empty")
                    continue
                must = C.placeholders(src_other) if form == "other" else None
                self._placeholders(tgt, key, list(src_forms.values()), text, form, must)
                self._untranslated(tgt, key, src_forms.get(form, src_other), text, form)
            if kind == "icu":
                self._placeholders(tgt, key, [sm.text], tm.text, "", None)
            return
        if tm.plurals is not None:
            self.add("warning", "plural", tgt, key, "the translation has plural forms; the source is a single string")
            return
        if not (tm.text or "").strip():
            if (sm.text or "").strip():
                self.add("error", "empty", tgt, key, "empty translation")
            return
        self._placeholders(tgt, key, [sm.text], tm.text, "", C.placeholders(sm.text))
        self._untranslated(tgt, key, sm.text, tm.text)

    def check_po(self, cat, pot=None):
        self.src_locale = "en"
        if pot is not None:
            for key in pot.messages:
                if key not in cat.messages:
                    self.add("error", "missing", cat, key, f"msgid not in this .po (run msgmerge): {_short(key)}")
        rules = C.plural_rules(cat.locale)
        if cat.nplurals and rules and cat.nplurals < len(rules[0]):
            self.add("error", "plural", cat, "(header)",
                     f"Plural-Forms says nplurals={cat.nplurals}, but {lang_name(cat.locale)} needs {len(rules[0])} "
                     f"({', '.join(rules[0])})")
        for key, m in cat.messages.items():
            label = key.split("\x04")[-1]
            if m.fuzzy:
                self.add("warning", "fuzzy", cat, label, "marked fuzzy; gettext will not use it")
            if m.plurals is not None:
                srcs = [key.split("\x04")[-1], m.source_text or ""]
                n = cat.nplurals or len(m.plurals)
                for i in range(n):
                    text = m.plurals.get(str(i), "")
                    if not text.strip():
                        self.add("error", "empty", cat, label, f"msgstr[{i}] is empty")
                    else:
                        self._placeholders(cat, label, srcs, text, f"msgstr[{i}]", None)
                continue
            if not (m.text or "").strip():
                self.add("error", "missing", cat, label, "empty msgstr: not translated")
                continue
            self._placeholders(cat, label, [m.source_text], m.text, "", C.placeholders(m.source_text))
            self._untranslated(cat, label, m.source_text, m.text)


def _text_of(m):
    return m.text if m.text is not None else " / ".join(f"{k}: {v}" for k, v in (m.plurals or {}).items())


def _short(s, n=70):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


# --------------------------------------------------------------------------- grouping


def pick_source(cats, wanted):
    for c in cats:
        if c.is_source:
            return c, None
    lang = C.language_of(wanted)
    exact = [c for c in cats if c.locale.lower() == wanted.lower()]
    same = exact or [c for c in cats if C.language_of(c.locale) == lang]
    if same:
        return same[0], None
    best = max(cats, key=lambda c: len(c.messages))
    return best, f"no '{wanted}' catalog here; using {best.locale} ({best.path}) as the source"


def run(root, source="en", only=None, allow=(), ignore_extra=False):
    cats = C.discover(root)
    checker = Checker(allow, ignore_extra)
    groups_out = []
    notes = []
    for cat in cats:
        for p in cat.problems:
            checker.add("error", "file", cat, "", p)
    po = [c for c in cats if c.fmt == "po"]
    pots = {os.path.splitext(os.path.basename(c.path))[0]: c for c in cats if c.fmt == "pot"}
    for cat in po:
        if only and cat.locale not in only:
            continue
        stem = os.path.splitext(os.path.basename(cat.path))[0]
        checker.check_po(cat, pots.get(stem))
        groups_out.append({"namespace": cat.path, "source": "msgid", "locales": [cat.locale]})
    grouped = defaultdict(list)
    for c in cats:
        if c.fmt not in ("po", "pot") and c.locale != "?":
            grouped[c.namespace].append(c)
    for ns, members in sorted(grouped.items()):
        if len(members) < 2:
            notes.append(f"{members[0].path}: only one language, nothing to compare")
            continue
        src, note = pick_source(members, source)
        if note:
            notes.append(f"{ns}: {note}")
        targets = [m for m in members if m is not src and (not only or m.locale in only)]
        for t in targets:
            checker.compare(src, t)
        groups_out.append({"namespace": ns, "source": src.locale or "(base)", "source_path": src.path,
                           "locales": [t.locale for t in targets], "keys": len(src.messages)})
    return cats, groups_out, checker.issues, notes


# --------------------------------------------------------------------------- output


def summarize(issues):
    table = defaultdict(lambda: Counter())
    for i in issues:
        table[(i.locale, i.path)][i.level] += 1
        if i.code == "missing":
            table[(i.locale, i.path)]["missing"] += 1
    return table


def render(root, cats, groups, issues, notes, color):
    def c(code, s):
        return f"\033[{code}m{s}\033[0m" if color else s

    lines = []
    n_loc = len({x.locale for x in cats})
    lines.append(f"i18n check: {len(cats)} catalog file(s), {n_loc} language(s), {len(groups)} group(s) under {root}")
    for n in notes:
        lines.append(c("2", f"  note: {n}"))
    if not issues:
        lines.append(c("1;32", "✓ no problems: every key, placeholder and plural form is accounted for"))
        return "\n".join(lines)
    by_file = defaultdict(list)
    for i in issues:
        by_file[(i.path, i.locale)].append(i)
    lines.append("")
    lines.append(f"  {'locale':<10}{'errors':>7}{'warnings':>10}  file")
    for (path, loc), items in sorted(by_file.items(), key=lambda kv: kv[0][1]):
        e = sum(1 for i in items if i.level == "error")
        w = len(items) - e
        lines.append(f"  {loc:<10}{c('31', f'{e:>7}') if e else f'{e:>7}'}{c('33', f'{w:>10}') if w else f'{w:>10}'}  {path}")
    for (path, loc), items in sorted(by_file.items(), key=lambda kv: kv[0][1]):
        lines.append("")
        lines.append(c("1", f"{path}  [{loc}]"))
        for i in sorted(items, key=lambda i: (i.level != "error", i.key)):
            mark = c("31", "✗") if i.level == "error" else c("33", "!")
            key = f"{i.key}  " if i.key else ""
            lines.append(f"  {mark} {key}{c('2', i.code + ':')} {i.message}")
    e = sum(1 for i in issues if i.level == "error")
    lines.append("")
    lines.append(c("1;31" if e else "1;33", f"{e} error(s), {len(issues) - e} warning(s)"))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="i18n_check", description="Check translation catalogs against the source language.")
    ap.add_argument("root", nargs="?", default=".", help="project folder to scan (default: .)")
    ap.add_argument("--source", default="en", help="source locale (default: en)")
    ap.add_argument("--only", action="append", help="check only this locale (repeatable)")
    ap.add_argument("--allow", action="append", default=[], help="term that may stay untranslated (repeatable)")
    ap.add_argument("--allow-file", help="file with one allowed term per line (brand names, product terms)")
    ap.add_argument("--ignore-extra", action="store_true", help="don't warn about keys that only exist in a translation")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--version", action="version", version=f"i18n_check {__version__}")
    args = ap.parse_args(argv)

    allow = list(args.allow)
    allow_file = args.allow_file or os.path.join(args.root, ".i18n-allow")
    if os.path.exists(allow_file):
        with open(allow_file, encoding="utf-8") as fh:
            allow += [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    cats, groups, issues, notes = run(args.root, args.source, set(args.only) if args.only else None, allow, args.ignore_extra)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except (ValueError, OSError):
            pass
    if args.json:
        print(json.dumps({"catalogs": [{"path": c.path, "locale": c.locale, "format": c.fmt, "keys": len(c.messages)} for c in cats],
                          "groups": groups, "notes": notes, "issues": [i.as_dict() for i in issues]}, ensure_ascii=False, indent=1))
    else:
        print(render(args.root, cats, groups, issues, notes, sys.stdout.isatty() and not os.environ.get("NO_COLOR")))
    if not cats:
        if not args.json:
            print("No translation catalogs found. Pass the project folder, or see references/libraries.md for layouts.", file=sys.stderr)
        return 2
    errors = sum(1 for i in issues if i.level == "error")
    if errors or (args.strict and issues):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
