# Libraries: what to use, where catalogs go, how plurals look

Use the platform's standard library. The checker reads every format in this table unless the
last column says otherwise.

| Stack | Library | Catalog location | Plurals | Pseudo-locale switch |
|---|---|---|---|---|
| React, Electron, vanilla JS | i18next + react-i18next | `locales/<lang>/<namespace>.json` | `key_one`, `key_few`, `key_other` | add `en-XA` to resources, `i18n.changeLanguage("en-XA")` |
| React (ICU style) | FormatJS / react-intl | `lang/<lang>.json`, flat keys | ICU `{count, plural, …}` | `<IntlProvider locale="en-XA" messages={…}>` |
| Next.js App Router | next-intl | `messages/<lang>.json` | ICU | add `en-XA` to the routing locales |
| Vue | vue-i18n | `locales/<lang>.json` | pipes `car \| cars` (checked as plain text) or ICU via a message compiler | set the i18n `locale` to `en-XA` |
| Svelte | svelte-i18n or Paraglide | `messages/<lang>.json` | ICU (svelte-i18n) | `locale.set("en-XA")` |
| Angular | `@angular/localize` | XLIFF `messages.<lang>.xlf` | ICU | build with an `en-XA` locale. **XLIFF is not read by the checker** |
| Django | gettext | `locale/<lang>/LC_MESSAGES/django.po` | `msgid_plural` / `msgstr[n]` | `makemessages`, write `en_XA` .po with `pseudo.py`, `compilemessages`, set `LANGUAGE_CODE` |
| Flask, FastAPI | Babel / Flask-Babel | `translations/<lang>/LC_MESSAGES/messages.po` | gettext | as Django |
| Rails | rails-i18n | `config/locales/<lang>.yml` | `one:`, `other:` | **YAML is not read by the checker** |
| Android | resources | `res/values-<lang>/strings.xml` | `<plurals>` + `quantity` | built in: enable `pseudoLocalesEnabled true`, then pick English (XA) or Arabic (XB) on the device |
| iOS, macOS | String Catalogs | `Localizable.xcstrings` (Xcode 15+), or `<lang>.lproj/Localizable.strings` | catalog variations | built in: scheme → Run → Options → App Language → Double-Length / Right-to-Left Pseudolanguage |
| Flutter | `gen-l10n` | `lib/l10n/app_<lang>.arb` | ICU | add `app_en_XA.arb`… or test with a long locale like `de` |
| Chrome extension | `chrome.i18n` | `_locales/<lang>/messages.json` | none: write separate keys | load the extension with a `_locales/en_XA` folder and a browser language override |
| Java, Spring | ResourceBundle | `messages_<lang>.properties` | ChoiceFormat or ICU4J | `Locale.forLanguageTag("en-XA")` |

## Setting up from nothing (React example)

```bash
npm install i18next react-i18next i18next-browser-languagedetector
```

```js
// src/i18n.js
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import en from "./locales/en/translation.json";
import de from "./locales/de/translation.json";

i18n.use(LanguageDetector).use(initReactI18next).init({
  resources: { en: { translation: en }, de: { translation: de } },
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React already escapes
});
export default i18n;
```

```jsx
const { t } = useTranslation();
<h1>{t("cart.title")}</h1>
<span>{t("cart.items", { count })}</span>                         {/* cart.items_one / _other */}
<Trans i18nKey="footer" components={{ 1: <a href="/returns" /> }} /> {/* "Prices include tax. <1>Return policy</1>" */}
```

Import `./i18n` once at the entry point. For many languages, load catalogs lazily
(`i18next-http-backend` or dynamic `import()`), so users only download their own language.

## Telling the app the language

Order of preference: the user's explicit choice (saved), then the URL (`/de/…`) for sites that
need to be indexed per language, then `navigator.languages` / the OS setting. Always set
`<html lang>` and, for RTL languages, `dir="rtl"`.
