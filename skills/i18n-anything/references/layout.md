# Layout for every language

## Text gets longer, shorter and taller

- No fixed widths on anything holding text. Let buttons, tabs and table headers grow, wrap, or
  truncate with a tooltip, and decide which per component.
- The pseudo-locale (`pseudo.py`, 40% longer by default) shows the breaks in English before
  any translation exists. Try `--expand 1.0` for one-word labels.
- Give CJK text a font stack that has CJK glyphs (`"Noto Sans CJK SC"`, `"PingFang SC"`,
  `"Hiragino Sans"`, `"Microsoft YaHei"`) and a line height of at least 1.5.
- Don't upper-case with CSS `text-transform` in languages where it breaks words or has rules of
  its own (German ß, Turkish dotted i, Greek accents); put the casing in the translation instead.

## Right-to-left (Arabic, Hebrew, Persian, Urdu)

- Set `dir="rtl"` on `<html>` (and `lang`). Most layout flips by itself if the CSS uses logical
  properties: `margin-inline-start` instead of `margin-left`, `padding-inline-end`,
  `inset-inline-start`, `text-align: start`, `border-start-start-radius`.
- Mirror icons that point in the reading direction (back, forward, chevrons, progress). Don't
  mirror logos, media play buttons, clocks, checkmarks or anything showing the real world.
- Numbers, phone numbers, code and English product names stay left-to-right inside RTL text; wrap
  mixed snippets in `<bdi>` or use `unicode-bidi: isolate` when they sit next to punctuation.
- Test with `pseudo.py --rtl` first, then with real Arabic or Hebrew text.

## Formatting values

Never format by hand; let the platform's locale data do it.

| Value | Web | Android | iOS | Python |
|---|---|---|---|---|
| Numbers, currency | `Intl.NumberFormat` | `NumberFormat` | `NumberFormatter` / `.formatted()` | Babel `format_currency` |
| Dates and times | `Intl.DateTimeFormat` | `DateTimeFormatter.ofLocalizedDate` | `Date.FormatStyle` | Babel `format_date` |
| "3 days ago" | `Intl.RelativeTimeFormat` | `DateUtils.getRelativeTimeSpanString` | `RelativeDateTimeFormatter` | Babel `format_timedelta` |
| Lists ("A, B and C") | `Intl.ListFormat` | `ListFormatter` (ICU) | `ListFormatter` | Babel `format_list` |
| Sorting | `Intl.Collator` | `Collator` | `localizedStandardCompare` | `locale.strxfrm` / PyICU |

Currencies belong to the price, not the language: a German user buying in US dollars still sees
`12,50 $`.
