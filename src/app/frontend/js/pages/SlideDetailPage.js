import { GRADES, MEANING, SEVERITY, TIER_LABEL, TIER_OF, TIER_RANK } from "../core/config.js";
import { el, pct, plural, when } from "../core/dom.js";
import { DangerButton } from "../core/DangerButton.js";
import { Lightbox } from "../core/Lightbox.js";
import { okPred, tone } from "../core/results.js";
import { CamPanel } from "../components/CamPanel.js";
import { FieldViewer } from "../components/FieldViewer.js";
import { Page } from "./Page.js";

/* One slide: the overall result on top, then a card for every photo. A clinician can confirm or correct each grade here. */
export class SlideDetailPage extends Page {
  static openBars = new Set();       // photos whose "all six scores" panel is open, kept across redraws

  async render(view, ctx) {
    const slideId = ctx.params.id;
    const slide = await this.api(`/slides/${slideId}`).catch(e => { if (e.status === 404) return null; throw e; });
    if (!ctx.isCurrent()) return;
    if (!slide) {
      view.replaceChildren(el("div", { class: "empty" }, el("b", {}, "That slide was not found."), el("a", { href: "#/slides" }, "Back to the list")));
      return;
    }
    this.setTitle(slide.patient_code);
    this._canReview = this.user.role === "clinician";
    this._viewState = FieldViewer.newState();      // picked cells, hidden boxes, overlays: one set per visit to this page
    this._host = el("div");

    const head = el("div", { class: "page-head" },
      el("div", {},
        el("a", { class: "back", href: "#/slides" }, "← All slides"),
        el("h1", { class: "page-title" }, slide.patient_code),
        el("div", { class: "meta-line" },
          el("span", {}, when(slide.created_at)), el("span", {}, `Uploaded by ${slide.uploader_name}`), el("span", {}, plural(slide.image_count, "image")),
          slide.note ? el("span", {}, `Note: ${slide.note}`) : null)),
      this.user.role === "admin" ? new DangerButton(this.app.toast, "Delete slide", "Click again to delete", async () => {
        await this.api(`/slides/${slide.id}`, { method: "DELETE" });
        this.toast("Slide deleted.");
        location.hash = "#/slides";
      }).node : null);
    view.replaceChildren(head, this._host);
    this._draw(slide);
  }

  /* (Re)draw the result and the cards. Called again with the updated slide after every review action. */
  _draw(slide) {
    const cards = slide.images.slice().sort((a, b) => {
      const A = okPred(a), B = okPred(b);
      if (A !== B) return A ? -1 : 1;
      if (!A) return a.position - b.position;
      return (TIER_RANK[b.prediction.tier] - TIER_RANK[a.prediction.tier])
        || (SEVERITY[b.prediction.predicted_class] - SEVERITY[a.prediction.predicted_class])
        || (b.prediction.confidence - a.prediction.confidence);
    });
    this._host.replaceChildren(
      this._verdictBlock(slide),
      el("div", { class: "cards" }, cards.map(im => this._imageCard(slide, im))),
      el("p", { class: "fine" }, "A grade from this tool is a suggestion for a trained reader. It is not a diagnosis. The overall result is the most serious finding among the images, using the clinician's decision where there is one."));
  }

  _verdictBlock(slide) {
    const o = slide.overall, images = slide.images;
    const box = el("div", { class: "results flat" });
    if (!o.tier) {
      box.append(el("div", { class: "verdict" }, el("div", {}, el("div", { class: "eyebrow" }, "Overall result"), el("div", { class: "verdict-tier" }, "No result"),
        el("p", { class: "verdict-line" }, "None of the images could be read. Try JPG or PNG files."))));
      return box;
    }
    const t = o.tier, g = o.class;
    const eyebrow = o.images_reviewed === 0 ? "Overall result, from the model" : o.fully_reviewed ? "Overall result, confirmed by a clinician" : "Overall result, partly confirmed";
    const best = images.find(im => im.id === o.image_id);
    let small = t === "negative" ? "" : MEANING[g] + ".";
    if (best && best.feedback) small = "Based on a clinician's decision.";
    else if (best && okPred(best) && best.prediction.tier !== TIER_OF[best.prediction.predicted_class]) small = "The group score and the single most likely grade differ here, so check this one closely.";
    box.append(el("div", { class: "verdict" },
      el("div", {},
        el("div", { class: "eyebrow" }, eyebrow),
        el("div", { class: `verdict-tier tier-${t}` }, el("i", { class: tone(t) }), TIER_LABEL[t]),
        el("p", { class: "verdict-line" },
          t === "negative" ? `No abnormal cells found${o.images_read > 1 ? ` in ${o.images_read} images` : ""}.` : `Most serious finding: ${g}${o.images_read > 1 ? ` in image ${o.position}` : ""}.`,
          small ? el("small", {}, small) : null)),
      el("div", { class: "verdict-side" }, el("b", {}, `${o.images_reviewed} of ${o.images_read}`), "images reviewed")));
    const notes = [];
    if (o.mock) notes.push("This server is running a placeholder model, so these grades are not real.");
    if (o.low_confidence_images) notes.push(`${plural(o.low_confidence_images, "image has", "images have")} low confidence and ${o.low_confidence_images === 1 ? "is" : "are"} worth a closer look.`);
    const unread = o.images_total - o.images_read;
    if (unread) notes.push(`${plural(unread, "image")} could not be read.`);
    if (notes.length) box.append(el("div", { class: "warn" }, notes.join(" ")));
    return box;
  }

  /* Run a review action, then redraw with the updated slide it returns. */
  async _send(call) {
    try { this._draw(await call()); } catch (e) { this.toast(e.message, true); }
  }

  _thumbnail(slide, im) {
    const img = el("img", { alt: `Image ${im.position}: ${im.filename}` });
    this.app.api.loadSlideImage(img, slide.id, im.id);
    const thumb = el("button", { type: "button", class: "thumbbtn", title: "View the full photo", "aria-label": `View the full photo of image ${im.position}` }, img);
    thumb.addEventListener("click", () => {
      const big = el("img", { class: "lb-img", alt: `Image ${im.position}: ${im.filename}` });
      this.app.api.loadSlideImage(big, slide.id, im.id);
      Lightbox.open(`Image ${im.position} · ${im.filename}`, big);
    });
    return thumb;
  }

  _imageCard(slide, im) {
    const thumb = this._thumbnail(slide, im);
    const meta = el("div", { class: "ic-meta" }, el("span", {}, `Image ${im.position}`), el("span", { title: im.filename }, im.filename));
    if (!okPred(im)) {
      const body = el("div", {}, meta, el("p", { class: "ic-err" }, im.prediction ? im.prediction.error : "No result for this image."));
      return el("article", { class: "card ic" }, el("div", { class: "ic-top" }, thumb, body));
    }
    const p = im.prediction, fb = im.feedback, t = im.final_tier, g = im.final_class;
    const isField = p.mode === "field" && p.detections;
    const likely = isField
      ? (p.predicted_class === "Negative" ? "No cell was clearly abnormal" : `Most serious sure cell: ${p.predicted_class}, ${pct(p.confidence)}`)
      : `Most likely ${p.predicted_class}, ${pct(p.confidence)}`;
    const line = fb ? `${fb.action === "corrected" ? "Corrected to" : "Confirmed as"} ${g}` : likely;
    const body = el("div", {}, meta,
      el("div", { class: `ic-tier tier-${t}` }, el("i", { class: tone(t) }), TIER_LABEL[t]),
      el("div", { class: "ic-grade" }, line),
      !fb && p.low_confidence ? el("div", { class: "ic-flag" }, isField ? "Some cells were unsure, worth a closer look" : p.mode === "whole" ? "Graded as one cell without the detector, not reliable" : "Low confidence, worth a closer look") : null);
    const card = el("article", { class: "card ic" }, el("div", { class: "ic-top" }, thumb, body));
    const viewer = isField ? new FieldViewer(this.app.api, this._viewState, slide.id, im, p) : null;

    card.append(this._scoresPanel(im, p, isField));
    if (!isField && !p.mock) {
      const cam = new CamPanel(this.app.api, this._viewState.camOn, im, p, false);
      cam.show(0);
      card.append(cam.node);
    }
    card.append(this._reviewRow(im, p, fb));

    if (viewer) {            /* photo on the left, grade and review on the right */
      const rest = Array.from(card.children).slice(1);
      card.replaceChildren(el("div", { class: "fv-grid" }, viewer.photo, el("div", { class: "fv-side" }, card.firstChild || "", viewer.info, viewer.camNode, viewer.note, ...rest)));
      card.classList.add("is-field");
    }
    return card;
  }

  _scoresPanel(im, p, isField) {
    const entries = Object.entries(p.probabilities).sort((a, b) => b[1] - a[1]);
    const d = el("details", {}, el("summary", {}, isField ? "Scores of the deciding cell" : "See all six scores"),
      el("div", { class: "bars" }, entries.map(([k, v]) => el("div", { class: "bar" }, el("span", {}, k),
        el("div", { class: "track" }, el("div", { class: `fill ${tone(TIER_OF[k])}`, style: `width:${(v * 100).toFixed(1)}%` })), el("span", { class: "v" }, pct(v))))));
    if (SlideDetailPage.openBars.has(im.id)) d.open = true;
    d.addEventListener("toggle", () => { d.open ? SlideDetailPage.openBars.add(im.id) : SlideDetailPage.openBars.delete(im.id); });
    return d;
  }

  /* The bottom row of a card: the clinician's decision, buttons to make one, or a note that it is waiting. */
  _reviewRow(im, p, fb) {
    const feedbackUrl = `/predictions/${p.id}/feedback`;
    if (fb) {
      const text = fb.action === "corrected" ? `Changed from ${p.predicted_class} to ${fb.corrected_class}` : "Confirmed";
      const row = el("div", { class: "review" }, el("span", { class: "done" }, text, el("span", { class: "by" }, `by ${fb.clinician_name}`)));
      if (this._canReview) row.firstChild.append(el("button", { type: "button", class: "linkbtn", onclick: () => this._send(() => this.api(feedbackUrl, { method: "DELETE" })) }, "Undo"));
      return row;
    }
    if (!this._canReview) return el("p", { class: "waiting" }, "Waiting for a clinician to review.");
    const select = el("select", { class: "pill", "aria-label": `Change the grade of image ${im.position}` },
      el("option", { value: "" }, "Change grade"),
      ...GRADES.slice().sort((a, b) => SEVERITY[b] - SEVERITY[a]).filter(k => k !== p.predicted_class).map(k => el("option", { value: k }, k)));
    select.addEventListener("change", () => {
      if (select.value) this._send(() => this.api(feedbackUrl, { method: "PUT", json: { action: "corrected", corrected_class: select.value } }));
    });
    return el("div", { class: "review" },
      el("button", { type: "button", class: "pill go", onclick: () => this._send(() => this.api(feedbackUrl, { method: "PUT", json: { action: "confirmed" } })) }, `Agree with ${p.predicted_class}`),
      select);
  }
}
