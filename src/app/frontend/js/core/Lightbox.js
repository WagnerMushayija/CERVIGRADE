import { el } from "./dom.js";

/* The full-size viewer: a dark overlay with a caption and any content. Closes with the X, a click outside, or Escape. */
export class Lightbox {
  static open(caption, content) {
    return new Lightbox(caption, content);
  }

  constructor(caption, content) {
    this._opener = document.activeElement;
    this._closeButton = el("button", { type: "button", class: "lb-x", "aria-label": "Close" }, "×");
    const box = el("div", { class: "lb-box" }, this._closeButton, caption ? el("p", { class: "lb-cap" }, caption) : null, content);
    this._wrap = el("div", { class: "lb", role: "dialog", "aria-modal": "true", "aria-label": caption || "Full photo" }, box);
    this._onKey = e => {
      if (e.key === "Escape") this.close();
      else if (e.key === "Tab") { e.preventDefault(); this._closeButton.focus(); }
    };
    this._wrap.addEventListener("click", e => { if (e.target === this._wrap) this.close(); });
    this._closeButton.addEventListener("click", () => this.close());
    document.addEventListener("keydown", this._onKey);
    document.body.style.overflow = "hidden";
    document.body.append(this._wrap);
    this._closeButton.focus();
  }

  close() {
    document.removeEventListener("keydown", this._onKey);
    this._wrap.remove();
    document.body.style.overflow = "";
    if (this._opener && this._opener.focus) this._opener.focus();
  }
}
