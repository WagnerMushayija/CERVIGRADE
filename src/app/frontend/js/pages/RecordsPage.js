import { el, plural, when } from "../core/dom.js";
import { DangerButton } from "../core/DangerButton.js";
import { Page } from "./Page.js";

/* Admin only: a summary of the system, how often clinicians agreed with the tool, and every patient code. */
export class RecordsPage extends Page {
  /* "efficientnetb0_cric_retrained.keras" -> "EfficientNetB0" */
  static prettyModel(name) {
    return /efficientnet/i.test(name) ? "EfficientNetB0" : String(name).replace(/\.(keras|h5|pt)$/i, "");
  }

  async render(view, ctx) {
    this.setTitle("Records");
    this._view = view;
    this._ctx = ctx;
    const [health, patients, slides, users, review] = await Promise.all([
      this.app.api.health(), this.api("/patients"), this.api("/slides?limit=500"), this.api("/users"),
      this.api("/stats/review").catch(() => null)]);
    if (!ctx.isCurrent()) return;
    view.replaceChildren(
      el("div", { class: "page-head" }, el("div", {}, el("h1", { class: "page-title" }, "Records"),
        el("p", { class: "page-sub" }, "Patient codes and their slides. Deleting a patient removes all of its slides, images, grades and reviews, and cannot be undone."))),
      this._systemBox(health, patients, slides, users),
      review ? this._agreementCard(review) : null,
      el("div", { class: "sec" }, el("h2", {}, "Patients"), this._patientList(patients)));
  }

  async _reload() {
    this._view.replaceChildren(el("p", { class: "count" }, "Loading…"));
    await this.render(this._view, this._ctx);
  }

  _systemBox(health, patients, slides, users) {
    const reviewedSlides = slides.filter(s => s.overall.fully_reviewed).length;
    return el("div", { class: "card sysbox" },
      el("div", {}, "Model", el("b", {}, health ? (health.using_real_model ? RecordsPage.prettyModel(health.model_name) : "Placeholder (no checkpoint found)") : "Server not reachable")),
      el("div", {}, "Patients", el("b", {}, String(patients.length))),
      el("div", {}, "Slides", el("b", {}, `${slides.length} (${reviewedSlides} fully reviewed)`)),
      el("div", {}, "Active users", el("b", {}, String(users.filter(u => u.active).length))));
  }

  _agreementCard(rs) {
    const share = rs.reviewed ? Math.round(100 * rs.confirmed / rs.reviewed) : 0;
    const fixes = rs.corrections.map(c => `${c.model} to ${c.clinician}${c.n > 1 ? ` (${c.n})` : ""}`).join(", ");
    return el("div", { class: "card agree" },
      el("div", { class: "agree-top" },
        el("div", {}, el("div", { class: "agree-lab" }, "Clinician agreement"),
          rs.reviewed
            ? el("div", { class: "agree-big" }, el("b", {}, `${rs.confirmed} of ${rs.reviewed}`), ` reviewed ${rs.reviewed === 1 ? "photo was" : "photos were"} confirmed`)
            : el("div", { class: "agree-big" }, "No photos reviewed yet")),
        rs.reviewed ? el("div", { class: "agree-pct" }, `${share}%`) : null),
      rs.reviewed ? el("div", { class: "agree-bar", role: "img", "aria-label": `${share} percent confirmed` }, el("i", { style: `width:${share}%` })) : null,
      el("p", { class: "agree-sub" },
        rs.reviewed ? `${rs.corrected} corrected${rs.corrected ? `, ${rs.group_changed} of them moved the photo to a different group` : ""}. ` : "",
        `${plural(rs.waiting, "photo")} still waiting for a clinician.`, fixes ? ` Corrections: ${fixes}.` : ""),
      el("p", { class: "agree-note" }, "This is how often clinicians agreed with the tool. It is not accuracy: it counts photos, and only those a clinician has opened."));
  }

  _patientList(patients) {
    const host = el("div", { class: "list" });
    host.replaceChildren(...(patients.length ? patients.map(p => this._patientRow(p)) : [
      el("div", { class: "empty" }, el("b", {}, "No patients yet."), "A patient code appears here when a technician uploads the first slide for it.")]));
    return host;
  }

  _patientRow(p) {
    const label = el("div", { class: "nm" }, p.code);
    const box = el("article", { class: "card urow" });
    const rename = el("button", { type: "button", class: "pill" }, "Rename");
    rename.addEventListener("click", () => this._startRename(p, label));
    const acts = el("div", { class: "acts" },
      p.slide_count ? el("a", { class: "pill", href: `#/slides?q=${encodeURIComponent(p.code)}`, style: "text-decoration:none" }, "View slides") : null,
      rename,
      new DangerButton(this.app.toast, "Delete", p.slide_count ? `Delete with ${plural(p.slide_count, "slide")}` : "Click again to delete", async () => {
        await this.api(`/patients/${p.id}`, { method: "DELETE" });
        this.toast("Patient and records deleted.");
        await this._reload();
      }).node);
    box.append(el("div", { class: "urow-top" },
      el("div", {}, label, el("div", { class: "sm" }, `Added ${when(p.created_at)}`)),
      el("div", {}, el("span", { class: "badge" + (p.slide_count ? "" : " off") }, plural(p.slide_count, "slide"))),
      el("div", { class: "sm" }, p.last_slide_at ? `Latest slide ${when(p.last_slide_at)}` : "No slides"),
      acts));
    return box;
  }

  _startRename(p, label) {
    const input = el("input", { type: "text", value: p.code, maxlength: "32", "aria-label": "New patient code", spellcheck: "false" });
    const saveB = el("button", { type: "button", class: "pill go" }, "Save");
    const cancelB = el("button", { type: "button", class: "pill" }, "Cancel");
    const msg = el("p", { class: "msg", role: "alert" });
    label.replaceChildren(el("div", { class: "inline-edit" }, input, saveB, cancelB), msg);
    input.focus();
    input.select();
    cancelB.addEventListener("click", () => label.replaceChildren(p.code));
    const doSave = async () => {
      try {
        await this.api(`/patients/${p.id}`, { method: "PATCH", json: { code: input.value } });
        this.toast("Code changed.");
        await this._reload();
      } catch (e) { msg.textContent = e.message; }
    };
    saveB.addEventListener("click", doSave);
    input.addEventListener("keydown", e => { if (e.key === "Enter") doSave(); if (e.key === "Escape") cancelB.click(); });
  }
}
