// A 60-line i18next-compatible runtime for the demo: nested JSON, {{vars}}, _one/_few/_other
// plural keys chosen with Intl.PluralRules, <1>…</1> rich text, and a fallback language.
// In a real app, use i18next, react-i18next, vue-i18n, next-intl or your platform's own system.
const RTL = new Set(["ar", "he", "fa", "ur"]);

async function load(base, lng) {
  const res = await fetch(`${base}/${lng}/translation.json`);
  if (!res.ok) throw new Error(`no catalog for ${lng}`);
  return res.json();
}

function lookup(obj, key) {
  return key.split(".").reduce((o, k) => (o && o[k] !== undefined ? o[k] : undefined), obj);
}

const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export async function createI18n(lng, { fallback = "en", base = "locales" } = {}) {
  const fb = await load(base, fallback);
  const res = lng === fallback ? fb : await load(base, lng).catch(() => fb);
  const rules = new Intl.PluralRules(lng);

  function raw(key, vars) {
    if (vars && typeof vars.count === "number") {
      const cat = rules.select(vars.count);
      for (const cat2 of [cat, "other"]) {
        const hit = lookup(res, `${key}_${cat2}`);
        if (hit !== undefined) return hit;
      }
      return lookup(fb, `${key}_${new Intl.PluralRules(fallback).select(vars.count)}`) ?? key;
    }
    return lookup(res, key) ?? lookup(fb, key) ?? key;
  }

  function interpolate(s, vars = {}) {
    return s.replace(/\{\{-?\s*([\w.]+)\s*\}\}/g, (_, name) => escapeHtml(vars[name] ?? ""));
  }

  const t = (key, vars) => interpolate(escapeHtml(raw(key, vars)), vars);
  // rich text: t.rich("footer", {}, { 1: (inner) => `<a href="#">${inner}</a>` })
  t.rich = (key, vars, parts = {}) =>
    interpolate(escapeHtml(raw(key, vars)), vars).replace(/&lt;(\d+)&gt;(.*?)&lt;\/\1&gt;/g, (_, n, inner) =>
      parts[n] ? parts[n](inner) : inner,
    );
  t.lng = lng;
  t.dir = RTL.has(lng.split("-")[0]) || lng.endsWith("-XB") ? "rtl" : "ltr";
  return t;
}
