import { createI18n } from "./i18n.js";

const params = new URLSearchParams(location.search);
const lng = params.get("lang") || "en";
const t = await createI18n(lng);

document.documentElement.lang = lng;
document.documentElement.dir = t.dir;

const money = new Intl.NumberFormat(lng.endsWith("-XA") || lng.endsWith("-XB") ? "en" : lng, {
  style: "currency",
  currency: "EUR",
});
const items = [
  { key: "mug", price: 18, qty: 2, hue: 24 },
  { key: "tote", price: 32, qty: 1, hue: 140 },
  { key: "notebook", price: 12.5, qty: 1, hue: 220 },
];
const count = items.reduce((n, i) => n + i.qty, 0);
const subtotal = items.reduce((n, i) => n + i.qty * i.price, 0);

// ?missed=1 adds one string that skipped extraction, to show what the pseudo-locale catches.
const missed = params.get("missed") ? `<p class="badge">Free returns within 30 days</p>` : "";

document.querySelector("#app").innerHTML = `
  <header>
    <strong class="brand" data-i18n-ignore>Lumen</strong>
    <nav><a>${t("nav.shop")}</a><a>${t("nav.orders")}</a><a>${t("nav.help")}</a></nav>
  </header>
  <p class="hello">${t("greeting", { name: "Mei" })}</p>
  <section class="cart">
    <div class="row head"><h1>${t("cart.title")}</h1><span class="count">${t("cart.items", { count })}</span></div>
    ${items
      .map(
        (i) => `
      <div class="row item">
        <span class="swatch" style="--h:${i.hue}"></span>
        <span class="name">${t(`product.${i.key}`)}<small>${t("cart.qty")} ${i.qty} · <a>${t("cart.remove")}</a></small></span>
        <span class="price">${money.format(i.qty * i.price)}</span>
      </div>`,
      )
      .join("")}
    <div class="promo"><input placeholder="${t("promo.placeholder")}" /><button class="ghost">${t("promo.apply")}</button></div>
    <div class="row"><span>${t("summary.subtotal")}</span><span>${money.format(subtotal)}</span></div>
    <div class="row"><span>${t("summary.shipping")}</span><span>${t("summary.free")}</span></div>
    <div class="row total"><span>${t("summary.total")}</span><span>${money.format(subtotal)}</span></div>
    <p class="eta">${t("summary.arrives", { count: 3 })}</p>
    ${missed}
    <button class="primary">${t("checkout")}</button>
  </section>
  <footer>${t.rich("footer", {}, { 1: (inner) => `<a>${inner}</a>` })}</footer>
`;

if (params.get("highlight")) {
  const { highlightUntranslated } = await import("../../skills/i18n-anything/assets/pseudo-highlight.js");
  highlightUntranslated();
}
document.body.dataset.ready = "1";
