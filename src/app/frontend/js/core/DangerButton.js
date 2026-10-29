import { el } from "./dom.js";

/* A delete button that needs two clicks: the first arms it (and changes its label), the second does the action.
   It disarms itself after four seconds. */
export class DangerButton {
  constructor(toast, label, armedLabel, action, extraAttributes) {
    this._toast = toast;
    this._label = label;
    this._armedLabel = armedLabel;
    this._action = action;
    this._timer = null;
    this.node = el("button", { type: "button", class: "pill danger" }, label);
    if (extraAttributes) for (const [k, v] of Object.entries(extraAttributes)) this.node.setAttribute(k, v);
    this.node.addEventListener("click", () => this._onClick());
  }

  _reset() {
    delete this.node.dataset.armed;
    this.node.textContent = this._label;
    this.node.classList.remove("armed");
  }

  async _onClick() {
    if (this.node.dataset.armed) {
      clearTimeout(this._timer);
      this.node.disabled = true;
      try { await this._action(); } catch (e) { this._toast.show(e.message, true); this.node.disabled = false; this._reset(); }
      return;
    }
    this.node.dataset.armed = "1";
    this.node.textContent = this._armedLabel;
    this.node.classList.add("armed");
    this._timer = setTimeout(() => this._reset(), 4000);
  }
}
