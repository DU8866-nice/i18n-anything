// Run the app in the pseudo-locale (en-XA), then run this in the page: paste it into the
// browser console, or inject it with Playwright / Puppeteer / a browser tool.
//
// Every translated string arrives wrapped in ⟦ ⟧ with accented letters. Any plain ASCII text left
// on screen outside those brackets never went through the translation function: it is
// hardcoded. Each one gets a red outline, and the list is returned (and logged) for the agent.
//
//   const found = highlightUntranslated();        // [{ text, where }]
//   highlightUntranslated({ outline: false });    // just report
//
// Mark text that should stay as it is (brand names, user content) with data-i18n-ignore.

const IGNORE = "[data-i18n-ignore], script, style, code, pre, noscript, svg, textarea";
const ATTRS = ["placeholder", "title", "aria-label", "alt"];

function describe(el) {
  const parts = [];
  for (let n = el; n && n.nodeType === 1 && parts.length < 4; n = n.parentElement) {
    let s = n.tagName.toLowerCase();
    if (n.id) s += `#${n.id}`;
    else if (n.classList.length) s += `.${[...n.classList].slice(0, 2).join(".")}`;
    parts.unshift(s);
  }
  return parts.join(" > ");
}

function visible(el) {
  const style = getComputedStyle(el);
  return style.display !== "none" && style.visibility !== "hidden" && el.getClientRects().length > 0;
}

export function highlightUntranslated({ root = document.body, outline = true } = {}) {
  const found = [];
  const flag = (el, text, how) => {
    found.push({ text: text.trim().slice(0, 120), where: describe(el), how });
    if (outline) {
      el.style.outline = "2px solid #e5484d";
      el.style.outlineOffset = "2px";
      el.style.backgroundColor = "rgba(229, 72, 77, 0.10)";
      el.title = "Hardcoded: this text skipped extraction";
    }
  };

  // Text nodes in document order. A translated string can span several nodes
  // (⟦Click <b>here</b>⟧), so keep track of whether we are inside a bracket.
  let depth = 0;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const el = node.parentElement;
    const text = node.nodeValue;
    let outside = "";
    for (const ch of text) {
      if (ch === "⟦") depth++;
      else if (ch === "⟧") depth = Math.max(0, depth - 1);
      else if (depth === 0) outside += ch;
    }
    if (!el || el.closest(IGNORE) || !visible(el)) continue;
    if (/[A-Za-z]{2,}/.test(outside)) flag(el, text, "text");
  }

  for (const el of root.querySelectorAll(ATTRS.map((a) => `[${a}]`).join(","))) {
    if (el.closest(IGNORE)) continue;
    for (const a of ATTRS) {
      const v = el.getAttribute(a);
      if (v && /[A-Za-z]{2,}/.test(v) && !v.includes("⟦")) flag(el, v, `attr:${a}`);
    }
  }

  if (found.length) console.table(found);
  else console.log("pseudo-highlight: every visible string went through translation");
  return found;
}

if (typeof window !== "undefined") window.highlightUntranslated = highlightUntranslated;
