import { MAX_IMAGES, MAX_MB } from "../core/config.js";
import { bigBtn, el, plural } from "../core/dom.js";
import { GradingProgress } from "../components/GradingProgress.js";
import { Page } from "./Page.js";

const CODE_PATTERN = /^[A-Za-z0-9_-]{3,32}$/;     // same rule as the backend: a code, never a name
const GIVE_UP_AFTER_MS = 10 * 60 * 1000;

/* Technician: enter a patient code, add the microscope photos from one slide, and send them to be graded. */
export class NewCheckPage extends Page {
  async render(view, ctx) {
    this.setTitle("New check");
    this._picked = [];
    this._nextId = 1;
    this._buildForm();
    this.api("/patients")
      .then(ps => { if (ctx.isCurrent()) this._codes.replaceChildren(...ps.map(p => el("option", { value: p.code }))); })
      .catch(() => {});

    view.replaceChildren(
      el("div", { class: "page-head" }, el("div", {}, el("h1", { class: "page-title" }, "New check"),
        el("p", { class: "page-sub" }, "Enter the patient's code and add the microscope photos from one slide. The tool finds the cells in each photo and grades them, then a clinician reviews the result."))),
      el("div", { class: "card form-card" },
        el("div", { class: "grid2" },
          el("div", { class: "field" }, el("label", { for: "pc" }, "Patient code"), this._code, this._codes, el("span", { class: "hint" }, "A code only, such as RW-0142. Never the patient's name.")),
          el("div", { class: "field" }, el("label", { for: "pn" }, "Note (optional)"), this._note, el("span", { class: "hint" }, "For example, which slide of the visit this is."))),
        this._drop, this._fileInput, this._pickedBox, this._msg, this._work,
        el("div", { class: "form-actions", style: "margin-top:24px" }, this._go, this._clear, this._count)));
    this._renderPicked();
  }

  _buildForm() {
    this._code = el("input", { type: "text", id: "pc", autocomplete: "off", autocapitalize: "none", spellcheck: "false", maxlength: "32", list: "codes", required: true });
    this._codes = el("datalist", { id: "codes" });
    this._note = el("input", { type: "text", id: "pn", maxlength: "500", autocomplete: "off" });
    this._drop = el("button", { type: "button", class: "drop", id: "drop" },
      el("b", {}, "Drop photos here, or choose files"), el("span", {}, `JPG or PNG, up to ${MAX_IMAGES} images, ${MAX_MB} MB each`));
    this._fileInput = el("input", { type: "file", accept: "image/*", multiple: true, id: "file" });
    this._pickedBox = el("div", { class: "picked", "aria-label": "Chosen images" });
    this._msg = el("p", { class: "msg", role: "alert" });
    this._work = el("div");
    this._go = bigBtn("Grade and save", { disabled: true, id: "go" });
    this._goText = this._go.firstChild;
    this._clear = el("button", { type: "button", class: "btn quiet", hidden: true }, "Start over");
    this._count = el("span", { class: "count" });

    this._drop.addEventListener("click", () => this._fileInput.click());
    ["dragenter", "dragover"].forEach(ev => this._drop.addEventListener(ev, e => { e.preventDefault(); this._drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => this._drop.addEventListener(ev, e => { e.preventDefault(); this._drop.classList.remove("over"); }));
    this._drop.addEventListener("drop", e => this._addFiles(e.dataTransfer.files));
    this._fileInput.addEventListener("change", () => { this._addFiles(this._fileInput.files); this._fileInput.value = ""; });
    this._clear.addEventListener("click", () => { this._picked.forEach(p => URL.revokeObjectURL(p.url)); this._picked = []; this._msg.textContent = ""; this._renderPicked(); });
    this._go.addEventListener("click", () => this._submit());
  }

  _renderPicked() {
    this._pickedBox.replaceChildren(...this._picked.map((p, i) => el("div", { class: "thumb" },
      el("img", { src: p.url, alt: `Image ${i + 1}: ${p.file.name}` }),
      el("button", { type: "button", "aria-label": `Remove ${p.file.name}`, onclick: () => { this._picked = this._picked.filter(x => x.id !== p.id); URL.revokeObjectURL(p.url); this._renderPicked(); } }, "×"))));
    const n = this._picked.length;
    this._go.disabled = n === 0;
    this._goText.textContent = n > 1 ? `Grade and save ${n} images` : "Grade and save";
    this._clear.hidden = n === 0;
    this._count.textContent = n ? `${plural(n, "image")} chosen` : "";
  }

  _addFiles(files) {
    const problems = [];
    for (const f of files) {
      if (!f.type.startsWith("image/")) { problems.push(`${f.name} is not an image.`); continue; }
      if (f.size > MAX_MB * 1024 * 1024) { problems.push(`${f.name} is larger than ${MAX_MB} MB.`); continue; }
      if (this._picked.length >= MAX_IMAGES) { problems.push(`Only ${MAX_IMAGES} images fit in one slide.`); break; }
      this._picked.push({ id: this._nextId++, file: f, url: URL.createObjectURL(f) });
    }
    this._msg.textContent = problems.join(" ");
    this._renderPicked();
  }

  async _submit() {
    const code = this._code.value.trim();
    if (!CODE_PATTERN.test(code)) {
      this._msg.textContent = "Enter the patient's code: 3 to 32 letters, numbers, dashes or underscores, with no spaces. Never a name.";
      this._code.focus();
      return;
    }
    if (!this._picked.length) return;
    this._go.disabled = true;
    this._goText.textContent = "Grading…";
    this._msg.textContent = "";
    const dot = this._go.querySelector(".dot"), arrow = dot.firstChild;
    dot.replaceChildren(el("span", { class: "spin" }));

    const form = new FormData();
    form.append("patient_code", code);
    if (this._note.value.trim()) form.append("note", this._note.value.trim());
    this._picked.forEach(p => form.append("files", p.file, p.file.name));

    const progress = new GradingProgress(this.app.api, this._picked.length);
    this._work.replaceChildren(progress.node);
    progress.start();
    const abort = new AbortController(), cutOff = setTimeout(() => abort.abort(), GIVE_UP_AFTER_MS);
    try {
      const slide = await this.api("/slides", { method: "POST", body: form, signal: abort.signal });
      this._picked.forEach(p => URL.revokeObjectURL(p.url));
      this.toast(`Saved. ${plural(slide.image_count, "photo")} graded.`);
      location.hash = `#/slides/${slide.id}`;
    } catch (e) {
      this._msg.textContent = e.message;
      this._renderPicked();
      dot.replaceChildren(arrow);
    } finally {
      progress.stop();
      clearTimeout(cutOff);
      this._work.replaceChildren();
    }
  }
}
