"""Tests for the i18n-anything scripts. Run: python3 -m unittest discover -s tests"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "i18n-anything", "scripts")
sys.path.insert(0, SCRIPTS)

import catalogs as C  # noqa: E402
import find_strings as F  # noqa: E402
import i18n_check as K  # noqa: E402
import pseudo as P  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
EX = os.path.join(ROOT, "examples")


def issues_for(root, **kw):
    _cats, _groups, issues, _notes = K.run(root, **kw)
    return {(i.locale, i.key, i.code) for i in issues}, issues


class Locales(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(C.normalize_locale("zh_CN"), "zh-CN")
        self.assertEqual(C.normalize_locale("pt-br"), "pt-BR")
        self.assertEqual(C.normalize_locale("zh-hans"), "zh-Hans")
        self.assertEqual(C.normalize_locale("sr-Latn-RS"), "sr-Latn-RS")
        self.assertIsNone(C.normalize_locale("translation"))
        self.assertIsNone(C.normalize_locale("xx"))

    def test_android_folders(self):
        self.assertEqual(C.android_locale("values"), "")
        self.assertEqual(C.android_locale("values-zh-rCN"), "zh-CN")
        self.assertEqual(C.android_locale("values-b+sr+Latn"), "sr-Latn")
        self.assertIsNone(C.android_locale("values-night"))
        self.assertIsNone(C.android_locale("values-v21"))

    def test_locale_in_path(self):
        cases = {
            "locales/de/translation.json": ("de", "locales/{lang}/translation.json"),
            "messages/zh-CN.json": ("zh-CN", "messages/{lang}.json"),
            "lib/l10n/app_pt_BR.arb": ("pt-BR", "lib/l10n/app_{lang}.arb"),
            "lib/l10n/my_app_de.arb": ("de", "lib/l10n/my_app_{lang}.arb"),
            "ios/zh-Hans.lproj/Localizable.strings": ("zh-Hans", "ios/{lang}.lproj/Localizable.strings"),
            "ios/Base.lproj/Main.strings": ("", "ios/{lang}.lproj/Main.strings"),
            "locale/fr/LC_MESSAGES/django.po": ("fr", "locale/{lang}/LC_MESSAGES/django.po"),
            "src/config/settings.json": (None, None),
        }
        for path, want in cases.items():
            self.assertEqual(C._locale_in_path(path), want, path)

    def test_plural_rules(self):
        self.assertEqual(C.plural_rules("ru-RU"), (("one", "few", "many"), (), ("other",)))
        self.assertEqual(C.plural_rules("fr"), (("one", "other"), ("many",), ()))
        self.assertEqual(C.plural_rules("zh-Hant"), (("other",), (), ()))
        self.assertEqual(len(C.plural_rules("ar")[0]), 6)
        self.assertIsNone(C.plural_rules("tlh"))

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_plural_table_matches_this_machines_icu(self):
        js = (
            "const out={};for(const l of %s){const pr=new Intl.PluralRules(l);const s=new Set();"
            "for(let n=0;n<=1000;n++)s.add(pr.select(n));out[l]=[...s];}console.log(JSON.stringify(out))"
            % json.dumps(sorted(C.PLURALS))
        )
        res = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
        live = json.loads(res.stdout)
        drift = {l: (sorted(C.plural_rules(l)[0]), sorted(v)) for l, v in live.items()
                 if sorted(C.plural_rules(l)[0]) != sorted(v)}
        # Node's bundled CLDR can be older than the table; only a handful of languages ever change.
        self.assertLessEqual(len(drift), 3, drift)


class Placeholders(unittest.TestCase):
    def same(self, a, b):
        return C.placeholders(a) == C.placeholders(b)

    def test_equivalent_forms(self):
        self.assertTrue(self.same("Hi %s, you have %d", "Hallo %1$s, du hast %2$d"))
        self.assertTrue(self.same("%2$s by %1$s", "%1$s의 %2$s"))
        self.assertTrue(self.same("Hi {{name}}", "Hallo {{ name }}"))
        self.assertTrue(self.same("Open $COUNT$ tabs", "Abrir $count$ pestañas"))
        self.assertTrue(self.same("100%% done", "100%% fertig"))
        # Go's explicit argument index, as in SiYuan's kernel messages
        self.assertTrue(self.same("[%d/%d] Created [%d] indexes [%s]", "[%[1]d/%[2]d] [%[4]s] के [%[3]d] इंडेक्स"))

    def test_percent_signs_are_not_printf(self):
        # Found as false alarms in Plane, AFFiNE and SiYuan: a percentage followed by a word
        for src, tgt in [
            ("Get 80% of your admin time back.", "Gewinnen Sie 80% Ihrer Zeit zurück."),
            ("{{amount}}% off", "{{amount}}% de descuento"),
            ("Saving {{discount}}%", "{{discount}}% sparen"),
            ("reduce the file size by about 30%", "réduire la taille d'environ 30 % et de 50 %"),
            ("up to 50% of history", "jusqu'à 50 % d'historique"),
            ("such as %date:yyyy-MM-dd% or %Empty Latent Image.width% to include values",
             "wie %date:yyyy-MM-dd% oder %Empty Latent Image.width% enthalten"),
            ("90% line", "90%-Linie"),
            ("Used {{percent}}% of this window", "Bu pencerenin {{percent}}%'i kullanıldı"),
        ]:
            self.assertTrue(self.same(src, tgt), (src, tgt))
        self.assertEqual(C.placeholders("Get 80% of it"), C.placeholders("Get it"))
        # a real space-flag token still counts
        self.assertFalse(self.same("Total: % d", "Total:"))

    def test_differences(self):
        self.assertFalse(self.same("Hi {{name}}", "Hallo {{nom}}"))
        self.assertFalse(self.same("Read <b>this</b>", "Lies das"))
        self.assertFalse(self.same("Hi %(name)s", "Hallo"))
        self.assertFalse(self.same("Hi {0}", "Hallo {1}"))

    def test_icu(self):
        args, branches, parg = C.parse_icu("{count, plural, =0 {none} one {# item} other {# items}} for {name}")
        self.assertEqual(args, {"count", "name"})
        self.assertEqual(set(branches), {"=0", "one", "other"})
        self.assertEqual(parg, "count")
        nested = "{g, select, female {{n, plural, one {She has # cat} other {She has # cats}}} other {{n} cats}}"
        self.assertEqual(C.parse_icu(nested)[0], {"g", "n"})


class Checker(unittest.TestCase):
    def test_formats_fixture(self):
        got, _ = issues_for(os.path.join(FIX, "formats"))
        expected = {
            ("ru", "items", "plural"), ("ru", "terms", "markup"),                       # Android
            ("de", "save", "untranslated"),                                            # .strings
            ("de", "Log out", "missing"), ("de", "Settings", "fuzzy"),                 # gettext
            ("ru", "(header)", "plural"), ("ru", "Hello, %(name)s", "placeholder"),
            ("pl", "inboxCount", "plural"),                                            # ARB ICU
            ("pl", "cart.count", "plural"),                                            # FormatJS ICU
            ("fr", "Share", "missing"),                                                # xcstrings
            ("es", "openAll", "placeholder"),                                          # Chrome
        }
        self.assertTrue(expected <= got, sorted(expected - got))
        # %1$s vs %s, values-night/, translatable="false", and the .properties pair are all fine
        self.assertNotIn(("ru", "welcome", "placeholder"), got)
        self.assertFalse([g for g in got if g[1] == "app_name"])
        self.assertFalse([g for g in got if g[0] == "de" and g[1] in ("greeting", "farewell", "multi")])

    def test_shop_is_clean_and_first_pass_is_not(self):
        got, issues = issues_for(os.path.join(EX, "shop"), allow=["Lumen", "de: Shop", "fr: Total"])
        self.assertEqual(issues, [], [i.as_dict() for i in issues])
        got, _ = issues_for(os.path.join(EX, "first-pass"), allow=["Lumen", "de: Shop", "fr: Total"])
        self.assertEqual(
            {g for g in got if g[2] not in ("plural-large",)},
            {
                ("ar", "cart.items", "plural"), ("ru", "cart.items", "plural"),
                ("de", "greeting", "placeholder"), ("de", "footer", "markup"),
                ("zh-CN", "greeting", "placeholder"), ("zh-CN", "promo.apply", "missing"),
                ("ja", "checkout", "untranslated"), ("ja", "cart.items", "plural-unused"),
                ("fr", "nav.help", "missing"), ("fr", "nav.halp", "extra"),
            },
        )

    def test_wrong_script_and_allow_list(self):
        tmp = tempfile.mkdtemp()
        try:
            for loc, data in {"en": {"a": "Save changes", "b": "GitHub"}, "ja": {"a": "Save changes now", "b": "GitHub"}}.items():
                os.makedirs(os.path.join(tmp, loc))
                with open(os.path.join(tmp, loc, "app.json"), "w", encoding="utf-8") as fh:
                    json.dump(data, fh)
            got, _ = issues_for(tmp)
            self.assertIn(("ja", "a", "wrong-script"), got)
            self.assertIn(("ja", "b", "untranslated"), got)
            got, _ = issues_for(tmp, allow=["ja: GitHub"])
            self.assertNotIn(("ja", "b", "untranslated"), got)
        finally:
            shutil.rmtree(tmp)

    def test_icu_needs_other(self):
        tmp = tempfile.mkdtemp()
        try:
            cat = {"en": "{n, plural, one {# day} other {# days}}", "de": "{n, plural, one {# Tag}}"}
            for loc, msg in cat.items():
                with open(os.path.join(tmp, f"{loc}.json"), "w", encoding="utf-8") as fh:
                    json.dump({"days": msg}, fh)
            _, issues = issues_for(tmp)
            self.assertTrue(any("no 'other'" in i.message for i in issues), [i.message for i in issues])
        finally:
            shutil.rmtree(tmp)

    def test_cli_exit_codes(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        run = lambda *a: subprocess.run([sys.executable, os.path.join(SCRIPTS, "i18n_check.py"), *a],  # noqa: E731
                                        capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(run(os.path.join(EX, "shop")).returncode, 0)
        self.assertEqual(run(os.path.join(EX, "first-pass")).returncode, 1)
        empty = tempfile.mkdtemp()
        try:
            self.assertEqual(run(empty).returncode, 2)
        finally:
            shutil.rmtree(empty)
        out = run(os.path.join(EX, "first-pass"), "--json")
        data = json.loads(out.stdout)
        self.assertEqual(len(data["catalogs"]), 7)
        self.assertTrue(any(i["code"] == "plural" for i in data["issues"]))


class Pseudo(unittest.TestCase):
    SAMPLES = [
        "Welcome back, {{name}}",
        "{count, plural, =0 {No items} one {# item} other {# items}} in {place}",
        "Hello %1$s, you have %d new %(kind)s",
        "Read the <1>terms</1> and <b>privacy</b> policy",
        "Open $t(app.name) with $COUNT$ tabs",
        "Visit https://example.com/help for more",
    ]

    def test_tokens_survive(self):
        for s in self.SAMPLES:
            for rtl in (False, True):
                out = P.pseudo(s, rtl=rtl)
                self.assertEqual(C.placeholders(out), C.placeholders(s), (s, out))
                self.assertNotRegex(C.strip_markup(out).replace("https://example.com/help", ""), r"[a-z]{2}", out)
        self.assertTrue(P.pseudo("Save", rtl=True).startswith("‮"))
        icu = P.pseudo(self.SAMPLES[1])
        self.assertEqual(set(C.parse_icu(icu)[1]), {"=0", "one", "other"})

    def test_formats_roundtrip_through_the_checker(self):
        tmp = tempfile.mkdtemp()
        try:
            src = os.path.join(FIX, "formats")
            dst = os.path.join(tmp, "formats")
            shutil.copytree(src, dst)
            made = [
                P.default_out(os.path.join(dst, "android/res/values/strings.xml"), "en-XA"),
                P.default_out(os.path.join(dst, "apple/en.lproj/Localizable.strings"), "en-XA"),
                P.default_out(os.path.join(dst, "java/messages.properties"), "en-XA"),
                P.default_out(os.path.join(dst, "flutter/lib/l10n/app_en.arb"), "en-XA"),
                P.default_out(os.path.join(dst, "formatjs/messages/en.json"), "en-XA"),
                P.default_out(os.path.join(dst, "chrome/_locales/en/messages.json"), "en-XA"),
            ]
            sources = ["android/res/values/strings.xml", "apple/en.lproj/Localizable.strings", "java/messages.properties",
                       "flutter/lib/l10n/app_en.arb", "formatjs/messages/en.json", "chrome/_locales/en/messages.json"]
            for s, out in zip(sources, made):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(P.main([os.path.join(dst, s)]), 0)
                self.assertTrue(os.path.exists(out), out)
            _, issues = issues_for(dst, only={"en-XA"})
            bad = [i.as_dict() for i in issues if i.locale == "en-XA" and i.code not in ("plural-large",)]
            self.assertEqual(bad, [])
            self.assertTrue(made[0].endswith("values-en-rXA/strings.xml"), made[0])
            self.assertTrue(made[2].endswith("messages_en_XA.properties"), made[2])
        finally:
            shutil.rmtree(tmp)

    def test_po(self):
        with open(os.path.join(FIX, "formats/gettext/locale/de/LC_MESSAGES/app.po"), encoding="utf-8") as fh:
            out = P.convert_po(fh.read(), P.pseudo, "en-XA")
        msgs, _, n = C.parse_po("", out)
        self.assertEqual(n, 2)
        self.assertIn("%(name)s", msgs["Hello, %(name)s"].text)
        self.assertEqual(set(msgs["%(count)d file"].plurals), {"0", "1"})


class FindStrings(unittest.TestCase):
    def test_before_component(self):
        hits = F.scan(os.path.join(EX, "before"))
        texts = {h["text"] for h in hits}
        for want in ("Your cart", "Remove", "days", "Check out", "Prices include tax.", "Return policy",
                     "Promo code", "Check out now", "Product photo", "Enter a promo code first", "Promo code applied"):
            self.assertIn(want, texts)
        for not_text in ("cart", "row head", "primary", "/returns"):
            self.assertNotIn(not_text, texts)

    def test_runtime_demo(self):
        texts = {h["text"] for h in F.scan(os.path.join(EX, "shop"))}
        self.assertIn("Free returns within 30 days", texts)
        self.assertNotIn("Your cart", texts)  # goes through t()

    def test_false_alarms_stay_out(self):
        samples = {
            "a.tsx": '<p>{t("cart.title")}</p>\n<Trans i18nKey="x" />\n<div className="flex gap-2">{count}</div>\n'
                     '<button onClick={() => go(1)}>{t("go")}</button>\n',
            "b.ts": "const xs: Array<string> = load(); if (a < b && c > d) { run() }\n",
            "c.vue": '<template><p>{{ $t("hello") }}</p><input :placeholder="$t(\'x\')"/></template>\n'
                     "<script>export default { data: () => ({ label: 'not template' }) }</script>",
            "d.jsx": "<code>npm install</code><p data-i18n-ignore>Lumen</p>\n",
        }
        hits = []
        for name, text in samples.items():
            hits += F.scan_text(name, text)
        self.assertEqual(hits, [])

    def test_other_platforms(self):
        self.assertEqual([h["text"] for h in F.scan_text("res/layout/main.xml",
                         '<Button android:text="Sign in" android:hint="@string/x"/>')], ["Sign in"])
        self.assertEqual([h["text"] for h in F.scan_text("Main.kt", 'Text("Hello there")\nText(stringResource(R.string.x))')],
                         ["Hello there"])
        self.assertEqual([h["text"] for h in F.scan_text("main.dart", "Text('Sign in')\nText(l10n.signIn)")], ["Sign in"])
        self.assertEqual([h["text"] for h in F.scan_text("View.swift", 'label.text = "Sign in"\nText("Auto key")')], ["Sign in"])


class Packaging(unittest.TestCase):
    def test_scripts_run_standalone(self):
        for script in ("i18n_check.py", "pseudo.py", "find_strings.py"):
            res = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), "--help"], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
