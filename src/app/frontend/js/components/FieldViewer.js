import { GRADES, TIER_COLOR } from "../core/config.js";
import { SVGNS, el, fill, pct, plural } from "../core/dom.js";
import { Lightbox } from "../core/Lightbox.js";
import { CamPanel } from "./CamPanel.js";

/* What a technician or clinician sees for one field photo: the photo with a box on every cell the detector found,
   a hover label, the picked cell's details, and its close-up. One FieldViewer per photo.

   `state` remembers choices across redraws of the slide page: which cell is picked, whether boxes are hidden,
   whether the unsure cells are shown, and which images have the Grad-CAM overlay on. */
export class FieldViewer {
  static newState() {
    return { pick: new Map(), aside: new Set(), hidden: new Set(), camOn: new Set() };
  }

  constructor(api, state, slideId, image, prediction, big = false) {
    this._api = api;
    this._state = state;
    this._slideId = slideId;
    this._image = image;
    this._p = prediction;
    this._big = big;
    this._D = prediction.detections;
    this._rects = [];
    this._hover = null;

    const D = this._D, [W, H] = D.image_size;
    this._wrap = el("div", { class: "field-wrap" });
    const photo = el("img", { alt: `Image ${image.position} with the cells the detector found` });
    api.loadSlideImage(photo, slideId, image.id);
    this._svg = document.createElementNS(SVGNS, "svg");
    this._svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    this._svg.setAttribute("preserveAspectRatio", "none");
    this._tip = el("div", { class: "tip", hidden: true });
    this._wrap.append(photo, this._svg, this._tip);

    this.info = el("div", { class: "cell-info", "aria-live": "polite" });
    this.cam = prediction.mock ? null : new CamPanel(api, state.camOn, image, prediction, true);
    this._tools = el("div", { class: "field-tools" });

    this._drawBoxes();
    if (state.pick.get(image.id) == null && D.decisive != null) state.pick.set(image.id, D.decisive);
    this._sync();
    if (this.cam) this.cam.show(this._picked());

    this.photo = el("div", { class: "fv-photo" }, this._wrap, this._tools);
    this.note = el("p", { class: "field-note" },
      `The detector found ${plural(D.found, "cell")}. ${D.counted} counted toward the result; ${D.set_aside} ${D.set_aside === 1 ? "was" : "were"} set aside as unsure. Boxes are suggestions for a trained reader.`);
  }

  get camNode() {
    return this.cam ? this.cam.node : null;
  }

  _picked() {
    const i = this._state.pick.get(this._image.id);
    return i != null ? i : null;
  }

  _pickCell(i) {
    this._state.pick.set(this._image.id, i);
    this._refresh();
  }

  _drawBoxes() {
    const D = this._D;
    const area = c => (c.box[2] - c.box[0]) * (c.box[3] - c.box[1]);
    /* small boxes are drawn last, so they stay hoverable */
    const order = D.cells.map((c, i) => i).sort((x, y) => area(D.cells[y]) - area(D.cells[x]));
    order.forEach(i => {
      const c = D.cells[i], [x1, y1, x2, y2] = c.box;
      const r = document.createElementNS(SVGNS, "rect");
      r.setAttribute("x", x1); r.setAttribute("y", y1); r.setAttribute("width", x2 - x1); r.setAttribute("height", y2 - y1);
      r.setAttribute("class", `b-${c.tier}${c.counted ? "" : " aside"}${i === D.decisive ? " decisive" : ""}`);
      r.setAttribute("tabindex", "0"); r.setAttribute("role", "button");
      r.setAttribute("aria-label", `Cell ${i + 1}: ${c.cls}, ${pct(c.conf)}${c.counted ? "" : ", set aside"}`);
      r.addEventListener("click", () => this._pickCell(i));
      r.addEventListener("mouseenter", ev => { this._hover = i; this._showTip(i, ev); this._refresh(); });
      r.addEventListener("mousemove", ev => this._moveTip(ev, i));
      r.addEventListener("mouseleave", () => this._leave());
      r.addEventListener("focus", () => { this._hover = i; this._showTip(i, null); this._refresh(); });
      r.addEventListener("blur", () => this._leave());
      r.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this._pickCell(i); } });
      this._svg.append(r);
      this._rects[i] = r;
    });
  }

  _showTip(i, ev) {
    const c = this._D.cells[i], tip = this._tip;
    fill(tip, el("i", { style: `background:${TIER_COLOR[c.tier]}` }), `${c.cls} ${pct(c.conf)}`);
    if (!c.counted) tip.append(el("small", {}, "unsure"));
    tip.hidden = false;
    this._moveTip(ev, i);
  }

  _moveTip(ev, i) {
    const tip = this._tip, r = this._wrap.getBoundingClientRect();
    let x, y;
    if (ev && ev.clientX != null && (ev.clientX || ev.clientY)) { x = ev.clientX - r.left + 14; y = ev.clientY - r.top + 16; }
    else { const q = this._rects[i].getBoundingClientRect(); x = q.left - r.left + q.width / 2; y = q.top - r.top - 34; }
    if (x + tip.offsetWidth > r.width - 6) x = Math.max(6, x - tip.offsetWidth - 28);
    if (y + tip.offsetHeight > r.height - 6) y = Math.max(6, y - tip.offsetHeight - 36);
    tip.style.left = Math.max(6, x) + "px";
    tip.style.top = Math.max(6, y) + "px";
  }

  _leave() {
    this._hover = null;
    this._tip.hidden = true;
    this._refresh();
  }

  _isVisible(c) {
    return c.counted || this._state.aside.has(this._image.id);
  }

  /* Redraw what depends on the picked and hovered cell: the boxes, the close-up and the details.
     The buttons are not touched here. Rebuilding them while the pointer moves would swallow a click:
     clicking a button takes focus from the box, which would rebuild the button between mouse-down and mouse-up. */
  _refresh() {
    const D = this._D, id = this._image.id, state = this._state;
    const hidden = state.hidden.has(id);
    D.cells.forEach((c, i) => {
      this._rects[i].style.display = hidden || !this._isVisible(c) ? "none" : "";
      this._rects[i].classList.toggle("sel", state.pick.get(id) === i);
    });
    if (this.cam) this.cam.show(this._picked());
    this._drawInfo(hidden);
  }

  /* Redraw everything, buttons included. Used when a show/hide switch changes. */
  _sync() {
    this._refresh();
    this._drawTools(this._state.hidden.has(this._image.id));
  }

  _drawInfo(hidden) {
    const D = this._D, id = this._image.id;
    const i = this._hover != null ? this._hover : this._state.pick.get(id);
    if (i == null || !D.cells[i]) {
      fill(this.info, el("div", { class: "sub" }, hidden ? "Boxes are hidden." : "Hover over a box to see its grade. Click one to keep it here."));
      return;
    }
    const c = D.cells[i];
    const top = GRADES.map((g, k) => [g, c.p[k]]).sort((a, b) => b[1] - a[1]).slice(1, 3);
    fill(this.info,
      el("div", {}, el("b", { class: `tier-${c.tier}` }, `${c.cls}, ${pct(c.conf)}`), i === D.decisive ? el("span", { class: "sub" }, "  decides the photo's result") : null),
      el("div", { class: "sub" }, (c.counted ? "Counts toward the result." : `Set aside: the model is not sure enough (needs ${pct(D.settings.cnn_sure)}).`) + ` Detector score ${c.det.toFixed(2)}.`),
      el("div", { class: "sub" }, "Next most likely: " + top.map(([g, v]) => `${g} ${pct(v)}`).join(", ")),
      this._hover != null && this._state.pick.get(id) !== i ? el("div", { class: "sub" }, "Click to keep this cell here.") : null);
  }

  _drawTools(hidden) {
    const D = this._D, id = this._image.id, state = this._state;
    fill(this._tools,
      this._big ? null : el("button", { type: "button", class: "pill", onclick: () => this._enlarge() }, "Enlarge"),
      el("button", {
        type: "button", class: "pill",
        onclick: () => { hidden ? state.hidden.delete(id) : state.hidden.add(id); this._tip.hidden = true; this._hover = null; this._sync(); },
      }, hidden ? "Show boxes" : "Hide boxes"),
      D.set_aside ? el("button", {
        type: "button", class: "pill",
        onclick: () => { state.aside.has(id) ? state.aside.delete(id) : state.aside.add(id); this._sync(); },
      }, state.aside.has(id) ? "Hide unsure cells" : `Show ${plural(D.set_aside, "unsure cell")}`) : null,
      el("span", { class: "keyl" },
        el("span", { class: "tier-negative" }, el("i"), "Negative"),
        el("span", { class: "tier-low" }, el("i"), "Low-grade"),
        el("span", { class: "tier-high" }, el("i"), "High-grade")));
  }

  _enlarge() {
    const v = new FieldViewer(this._api, this._state, this._slideId, this._image, this._p, true);
    Lightbox.open(`Image ${this._image.position} · ${this._image.filename}`,
      el("div", { class: "fv-grid" }, v.photo, el("div", { class: "fv-side" }, v.info, v.camNode, v.note)));
  }
}
