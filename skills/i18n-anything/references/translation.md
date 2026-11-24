# Translating

## Before the first string

1. **Register.** Pick one per language and write it down at the top of your work:

   | Language | Usual choice for consumer apps | Notes |
   |---|---|---|
   | German | *du* | *Sie* for banking, insurance, government, B2B |
   | French | *vous* | *tu* only for very casual brands |
   | Spanish | *tú* | *usted* in formal contexts; Latin American and Spain Spanish differ in vocabulary |
   | Portuguese | Brazil: *você* | Portugal (pt-PT) differs in vocabulary and spelling; don't reuse pt-BR |
   | Japanese | polite です/ます | buttons are short noun or verb forms: 保存, 削除する |
   | Korean | 해요체 | 합니다체 for formal or enterprise products |
   | Chinese | neutral, no 您 unless the brand is formal | zh-CN (Simplified) and zh-TW/zh-HK (Traditional) differ in characters *and* vocabulary |
   | Russian | *вы* | lower-case *вы* in UI text |

2. **Glossary.** List the product's own terms and how each language renders them, and keep them
   identical everywhere. Brand and product names usually stay in Latin script; put them in
   `.i18n-allow` so the checker doesn't flag them.

3. **Read the source for meaning, not words.** Button labels are commands; headings are
   descriptions. "Back" on a button is "Zurück", not "Rücken".

## While translating

- **Placeholders**: copy `{{name}}`, `{name}`, `%s`, `%1$s`, `%(name)s`, `$COUNT$`, `$t(key)`
  exactly. Move them to wherever the grammar needs them. Positional printf arguments
  (`%1$s`, `%2$s`) may be reordered.
- **Tags**: keep `<1>…</1>`, `<b>…</b>`, `<a>…</a>` around the matching words.
- **Plurals**: write every form `i18n_check.py` lists for the language. Arabic needs six, Russian,
  Ukrainian and Polish three for whole numbers, Chinese, Japanese, Korean, Vietnamese and Thai
  one. Remove forms the language never uses.
- **Gender and select**: if a sentence depends on the user's gender or another variable, use the
  library's select (`{gender, select, …}`, i18next `_context`) instead of guessing.
- **Length**: aim for the same length as the source in buttons and tabs. Short labels grow the
  most in translation (a one-word English label can double); sentences usually grow by a third
  in German, French or Finnish. Chinese and Japanese are shorter but need a larger font size to
  stay readable.
- **Punctuation and typography**:
  - Chinese and Japanese: full-width `，。：；！？（）` and「」quotes in Japanese, “” in Chinese.
    No spaces between characters; a space between a number and a CJK word is optional (be consistent).
  - French: a non-breaking space before `: ; ! ?` and inside « guillemets ».
  - Spanish: `¿…?` and `¡…!`.
  - German: „…“ quotes; nouns are capitalised.
  - Arabic and Hebrew: Arabic comma `،` and question mark `؟` in Arabic.
- **Don't translate**: code, file names, URLs, keyboard keys shown in code style, user content.

## After translating

Run `i18n_check.py`. Then read each language's catalog top to bottom once: inconsistent terms
and a register that drifts between *du* and *Sie* are things no checker sees.

Machine translation, including yours, is a first draft. Say so, and ask for a native speaker's
review of anything legal, financial, medical or marketing-critical.
