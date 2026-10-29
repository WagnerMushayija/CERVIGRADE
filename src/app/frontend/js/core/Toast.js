/* The small message that slides in at the bottom of the page and goes away on its own. */
export class Toast {
  constructor(node) {
    this._node = node;
    this._timer = null;
  }

  show(text, isError = false) {
    this._node.textContent = text;
    this._node.className = "toast show" + (isError ? " err" : "");
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this._node.classList.remove("show"), isError ? 5000 : 3200);
  }
}
