// The cart as it looked before i18n-anything: every string typed straight into the JSX.
import { useState } from "react";
import { formatPrice } from "./money";

export function Cart({ user, items, onCheckout }) {
  const [code, setCode] = useState("");
  const count = items.reduce((n, i) => n + i.qty, 0);

  function applyPromo() {
    if (!code) return alert("Enter a promo code first");
    toast.success("Promo code applied");
  }

  return (
    <section className="cart">
      <p className="hello">Welcome back, {user.firstName}</p>
      <div className="row head">
        <h1>Your cart</h1>
        <span className="count">{count} {count === 1 ? "item" : "items"}</span>
      </div>
      {items.map((item) => (
        <div className="row item" key={item.id}>
          <img src={item.image} alt="Product photo" />
          <span className="name">
            {item.name}
            <small>
              Qty {item.qty} · <button onClick={() => item.remove()}>Remove</button>
            </small>
          </span>
          <span className="price">{formatPrice(item.qty * item.price)}</span>
        </div>
      ))}
      <div className="promo">
        <input placeholder="Promo code" value={code} onChange={(e) => setCode(e.target.value)} />
        <button className="ghost" onClick={applyPromo}>Apply</button>
      </div>
      <div className="row total">
        <span>Total</span>
        <span>{formatPrice(items.reduce((n, i) => n + i.qty * i.price, 0))}</span>
      </div>
      <p className="eta">Arrives in {3} days</p>
      <button className="primary" onClick={onCheckout} aria-label="Check out now">
        Check out
      </button>
      <footer>
        Prices include tax. <a href="/returns">Return policy</a>
      </footer>
    </section>
  );
}
