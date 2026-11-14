// A small hand-written fake DOM for the page tests (a copy of the one in
// app.test.mjs, kept separate so that file stays as it was).
export class Node_ {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.attrs = {};
    this.listeners = {};
    this._text = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.className = "";
  }
  get firstChild() { return this.children[0] || null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  appendChild(c) { this.children.push(c); return c; }
  replaceChildren() {
    // Like a browser: removing the focused element moves the focus to the body.
    const active = this.doc && this.doc.activeElement;
    if (active && this.children.some((c) => c === active || c.find((n) => n === active).length)) {
      this.doc.activeElement = null;
    }
    this.children = [];
    this._text = "";
  }
  focus() { if (this.doc) this.doc.activeElement = this; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  fire(type) { for (const fn of this.listeners[type] || []) fn({ target: this }); }
  set textContent(v) { this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  find(pred, out = []) {
    if (pred(this)) out.push(this);
    for (const c of this.children) c.find(pred, out);
    return out;
  }
}

export function fakePage() {
  const ids = ["updated", "refresh", "notices", "headlines", "empty", "sources", "sources-section", "bottom-line"];
  const byId = {};
  const doc = new Node_("document");
  doc.hidden = false;
  doc.activeElement = null;
  doc.documentElement = new Node_("html");
  const make = (tag) => { const n = new Node_(tag); n.doc = doc; return n; };
  for (const id of ids) byId[id] = make("x");
  doc.getElementById = (id) => byId[id] || null;
  doc.createElement = make;
  return { doc, byId };
}

