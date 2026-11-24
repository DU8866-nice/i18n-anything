# Contributing

## Report a bug

Open an issue with the smallest pair of catalogs that shows it (source and one translation),
what `i18n_check.py` said, and what you expected. If a plural rule looks wrong, include your
Node/ICU version: `node -p "process.versions.icu + ' ' + process.versions.cldr"`.

## Add a format or a check

1. Add a fixture under `tests/fixtures/` with a correct file and a broken one.
2. Change the scripts in `skills/i18n-anything/scripts/`. They stay standard-library only, so the
   skill works on any machine an agent runs on.
3. Add a test to `tests/test_i18n.py` and run `python3 -m unittest discover -s tests`.

## Regenerate the plural table

`PLURALS` in `catalogs.py` comes from `Intl.PluralRules`. The test
`test_plural_table_matches_this_machines_icu` shows any difference from the ICU on your machine;
update the table when a new CLDR release changes a language.
