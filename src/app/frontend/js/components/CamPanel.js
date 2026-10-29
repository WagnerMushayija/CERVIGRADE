import { el, fill } from "../core/dom.js";

/* "Where the model looked": a cell up close, with an optional Grad-CAM heat overlay and its explanation.
   For a field photo it follows whichever box is picked (show(cellNumber)); for a single-cell photo it shows cell 0. */
export class CamPanel {
  /* camOn: the set of image ids whose overlay is switched on (shared, so a redraw keeps the choice). */
  constructor(api, camOn, image, prediction, isField) {
    this._api = api;
    this._camOn = camOn;
    this._image = image;
    this._p = prediction;
    this._isField = isField;
    this._cell = null;
    this._seq = 0;          // each redraw gets a number, so a slow picture from an older draw is ignored
    this.node = el("div", { class: "cam", hidden: true });
  }

  /* Pick which cell to show (null hides the panel). */
  show(cell) {
    if (cell === this._cell) return;
    this._cell = cell;
    this._render();
  }

  _render() {
    const box = this.node, cell = this._cell, im = this._image, p = this._p;
    if (cell == null) { box.hidden = true; return; }
    box.hidden = false;
    const on = this._camOn.has(im.id), mine = ++this._seq;
    const grade = this._isField ? p.detections.cells[cell].cls : p.predicted_class;
    const kids = [];
    if (this._isField || on) {
      const frame = el("div", { class: "cam-frame loading" }, el("span", { class: "spin" }));
      const img = el("img", { class: "cam-img", alt: on ? `Where the model looked on this cell for ${grade}` : "The cell up close" });
      img.addEventListener("load", () => { if (mine === this._seq) frame.classList.remove("loading"); });
      frame.append(img);
      this._api.blobUrl(`/predictions/${p.id}/cam?cell=${cell}&overlay=${on}`)
        .then(url => { img.src = url; })
        .catch(err => { if (mine === this._seq) frame.replaceChildren(el("p", { class: "cam-err" }, err.message)); });
      if (this._isField) kids.push(el("div", { class: "cam-title" }, `Cell ${cell + 1} up close`));
      kids.push(frame);
    }
    kids.push(el("button", {
      type: "button", class: "pill" + (on ? " go" : ""), "aria-pressed": on ? "true" : "false",
      onclick: () => { on ? this._camOn.delete(im.id) : this._camOn.add(im.id); this._render(); },
    }, on ? "Hide where the model looked" : "Show where the model looked"));
    if (on) kids.push(
      el("div", { class: "cam-key" }, el("span", {}, "less"), el("i"), el("span", {}, "more")),
      el("p", { class: "cam-note" }, `Where the model looked when it chose ${grade}. This is a rough guide, not proof that the grade is right.`));
    fill(box, kids);
  }
}
