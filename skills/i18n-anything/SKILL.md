---
name: i18n-anything
description: Translate any app's UI into any language and prove nothing was missed. Use when asked to internationalize or localize an app, add a language, set up i18n, extract hardcoded strings, translate catalogs (i18next, next-intl, vue-i18n, FormatJS, gettext, Android, iOS, Flutter, Java), or check translation files before a release.
---

# i18n-anything

Coding agents translate an interface fast and get the same things wrong every time: strings left
hardcoded, `{{name}}` translated into `{{nombre}}`, English `one`/`other` plural forms copied into
Russian, Polish and Arabic, `<b>` tags dropped, a sentence glued together from three keys,
"Check out" left in English in the Japanese file. This skill is the workflow, and three scripts
that catch those mistakes so you can show the result instead of asserting it.

Scripts live in this skill's `scripts/` folder and need only Python 3.10+:

| Script | What it does |
|---|---|
| `i18n_check.py [ROOT]` | Finds every catalog and compares each language with the source: missing keys, empty strings, changed or dropped placeholders, dropped markup, plural forms the language needs (CLDR 48), ICU plurals without `other`, fuzzy gettext entries, text left in the source language, stale keys. Exit 1 on errors. |
| `find_strings.py [ROOT]` | Lists user-facing text still hardcoded in JSX/TSX, Vue, Svelte, HTML, JS DOM code, Android layouts, Compose, UIKit and Flutter. |
| `pseudo.py SOURCE_CATALOG` | Writes an `en-XA` pseudo-locale ("⟦Šåṽé çĥåñĝéš ···⟧"), or `ar-XB` with `--rtl`, keeping placeholders, tags and ICU syntax intact. |

`assets/pseudo-highlight.js` runs in the page while the app is in the pseudo-locale and outlines
every piece of text that did not come through the translation function.

## Workflow

Work through these in order. Skipping the pseudo-locale step is how hardcoded strings ship.

### 1. Take stock

- Stack, framework, and whether an i18n library is already installed.
- Source language, target languages, and who will review the translations.
- Run `python3 scripts/i18n_check.py <project>` to list the catalogs it finds. If it finds none
  and the project has no i18n library, go to step 2. If the project keeps catalogs in a format the
  checker doesn't read (XLIFF, YAML, vue-i18n pipe plurals), say so and check by hand.

### 2. Set up the library (only if there is none)

Use the platform's standard. Don't write your own runtime. See `references/libraries.md` for
the pick per stack, where catalogs go and how plurals are written.

### 3. Extract the strings

Run `python3 scripts/find_strings.py <src>` and move each hit into the source catalog. Rules:

- **Whole sentences, never fragments.** "Arrives in {{count}} days" is one message. Never build
  `t("arrives") + count + t("days")`: word order differs between languages.
- **Plurals through the library**, never `count === 1 ? "item" : "items"`.
- **Numbers, prices, dates, lists and relative times through the formatter** (`Intl.*`,
  `NumberFormatter`, `DateFormat`), never by hand.
- **Keep markup inside the message** (`"Read the <1>terms</1>"`) and render it with the library's
  rich-text support.
- **Add context when a word is ambiguous**: "Open" (verb or state?), "Post" (noun or verb?). Use
  i18next `_context`, gettext `msgctxt`, ARB `@description`, Android comments.
- Key names describe where the string lives (`cart.title`, `checkout.button`), not what it says.

### 4. Prove the extraction with the pseudo-locale

1. `python3 scripts/pseudo.py <source catalog>` writes the `en-XA` catalog next to it.
2. Switch the app to `en-XA` (each library's switch is in `references/libraries.md`; Android
   and iOS have built-in pseudo-locales you can use instead).
3. Open every screen and run `assets/pseudo-highlight.js` in the page (browser console, or inject
   it with your browser tool). Every outlined element is a string that skipped extraction.
4. Fix them and repeat until it reports nothing. Look at the screenshots too: the pseudo-locale
   is 40% longer, so anything clipped or overflowing now will break in German or Finnish.
5. If any target language is right-to-left (Arabic, Hebrew, Persian, Urdu), repeat with
   `--rtl` and check the mirrored layout (see `references/layout.md`).

### 5. Translate

Follow `references/translation.md`. The short version:

- Decide the register per language before you start (German *du* or *Sie*, French *tu* or *vous*,
  Japanese plain or polite form) and keep it consistent.
- Keep a glossary of product terms; put names that stay as they are in `.i18n-allow`
  (`Lumen` for every language, `de: Shop` for German only).
- Copy placeholders, `$t(...)` references and tags exactly. Translate the words around them.
- Write every plural form the language needs. The checker lists them; don't guess from English.
- Use the language's punctuation: full-width `，。：` in Chinese and Japanese, a space before
  `: ; ! ?` in French, `¿` and `¡` in Spanish.

### 6. Verify

- `python3 scripts/i18n_check.py <project>` until it reports 0 errors.
- Read every warning and decide: a `wrong-script` or `untranslated` warning is usually a missed
  string; `plural-large` matters if counts can reach a million.
- Screenshot the main screens in each language, and in RTL if needed.

### 7. Report

Say which languages are done, how many strings, what the checker reports, and which strings are
left hardcoded on purpose. Say plainly that machine translation is a draft: legal, payment,
medical and marketing text needs a native speaker before release.

## Rules

- Never rename, translate or reorder the inside of a placeholder. Never translate keys.
- Never concatenate translated fragments into a sentence.
- Don't change source-language text while translating, except to fix extraction problems.
- Don't describe translations as reviewed or final unless a person reviewed them.
- Don't delete a key from the source catalog because a translation is missing.

## i18n_check reference

```text
python3 scripts/i18n_check.py [ROOT] [--source en] [--only de --only ja] [--allow TERM]
                              [--allow-file FILE] [--ignore-extra] [--strict] [--json]
```

| Code | Level | Meaning |
|---|---|---|
| `missing` | error | Key in the source, not in this language (or an empty gettext `msgstr`) |
| `empty` | error | Key present, text empty |
| `placeholder` | error | A placeholder was dropped, invented, or changed (`{{name}}` → `{{nom}}`). `%s` and `%1$s` count as the same |
| `markup` | error | Tags like `<b>` or `<1>` don't match the source |
| `plural` | error | Missing plural forms this language needs; ICU plural without `other`; gettext `nplurals` too small |
| `file` | error | The file doesn't parse, or has duplicate keys |
| `plural-large` | warning | French, Spanish, Italian, Portuguese and Catalan use `many` for a million or more |
| `plural-decimal` | warning | A form only fractional counts use (Russian `other`, Czech `many`) |
| `plural-unused` | warning | A form this language never selects (`one` in Japanese) |
| `untranslated` | warning | Same text as the source |
| `wrong-script` | warning | No characters of the language's script (Latin text in a Japanese file) |
| `fuzzy` | warning | gettext entry marked fuzzy, which gettext ignores |
| `extra` | warning | Key only in the translation: stale or misspelled |

Formats it reads: i18next, next-intl, vue-i18n and FormatJS JSON (nested or flat, `_one` suffixes
or ICU), Flutter ARB, Chrome `_locales/*/messages.json`, Apple `.xcstrings` and `.strings`, gettext
`.po`/`.pot`, Android `res/values*/strings.xml`, Java `.properties`. Not yet: XLIFF, YAML, Apple
`.stringsdict`, vue-i18n pipe plurals (`car | cars`, compared as plain text).
