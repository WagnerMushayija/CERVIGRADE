import { TIER_LABEL } from "../core/config.js";
import { arrowIcon, el, plural, when } from "../core/dom.js";
import { tone } from "../core/results.js";
import { Page } from "./Page.js";

/* The list of slides. What each role sees differs only in the title and the starting filter. */
export class SlideListPage extends Page {
  async render(view, ctx) {
    const role = this.user.role;
    const state = this._remember(role, ctx.query);
    this._role = role;
    this._ctx = ctx;
    this._state = state;
    this._seq = 0;
    const title = role === "technician" ? "My slides" : role === "clinician" ? "Review queue" : "Slides";
    const sub = role === "technician" ? "The slides you uploaded, with their results."
      : role === "clinician" ? "The most serious slides come first. Open one to confirm or correct each grade." : "Every slide in the system.";
    this.setTitle(title);

    const search = el("input", { type: "search", placeholder: "Search by patient code", "aria-label": "Search by patient code", value: state.q });
    const status = el("select", { class: "in", "aria-label": "Show" },
      el("option", { value: "all" }, "All slides"), el("option", { value: "needs_review" }, "Needs review"), el("option", { value: "reviewed" }, "Fully reviewed"));
    const sort = el("select", { class: "in", "aria-label": "Sort by" }, el("option", { value: "newest" }, "Newest first"), el("option", { value: "severity" }, "Most serious first"));
    status.value = state.status;
    sort.value = state.sort;
    this._count = el("span", { class: "count", role: "status" });
    this._list = el("div", { class: "list" });

    let timer;
    search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.q = search.value.trim(); this._load(); }, 250); });
    status.addEventListener("change", () => { state.status = status.value; this._load(); });
    sort.addEventListener("change", () => { state.sort = sort.value; this._load(); });

    view.replaceChildren(
      el("div", { class: "page-head" }, el("div", {}, el("h1", { class: "page-title" }, title), el("p", { class: "page-sub" }, sub)),
        role === "technician" ? el("a", { class: "btn", href: "#/new" }, "New check", el("span", { class: "dot" }, arrowIcon())) : null),
      el("div", { class: "toolbar" }, search, status, sort, this._count), this._list);
    await this._load();
  }

  /* The filters are remembered while the tab is open, so coming back to the list keeps them. */
  _remember(role, query) {
    const kept = this.app.state.slideList;
    const state = kept && kept.role === role ? kept
      : { role, q: "", status: role === "clinician" ? "needs_review" : "all", sort: role === "clinician" ? "severity" : "newest" };
    if (query.has("q")) { state.q = query.get("q"); state.status = "all"; }
    this.app.state.slideList = state;
    return state;
  }

  async _load() {
    const mine = ++this._seq, state = this._state;
    const qs = new URLSearchParams({ q: state.q, status: state.status, sort: state.sort });
    try {
      const rows = await this.api("/slides?" + qs);
      if (mine !== this._seq || !this._ctx.isCurrent()) return;
      this._count.textContent = plural(rows.length, "slide");
      this._list.replaceChildren(...(rows.length ? rows.map(s => this._row(s)) : [this._emptyMessage()]));
    } catch (e) {
      if (mine === this._seq) this._list.replaceChildren(el("div", { class: "empty" }, e.message));
    }
  }

  _emptyMessage() {
    const { q, status } = this._state, role = this._role;
    const filtered = q || status !== "all";
    const waitingEmpty = !q && status === "needs_review";
    return el("div", { class: "empty" },
      el("b", {}, waitingEmpty ? "Nothing is waiting for review." : filtered ? "No slides match." : role === "technician" ? "No slides yet." : "Nothing here yet."),
      role === "technician" && !filtered ? el("span", {}, "Start with ", el("a", { href: "#/new" }, "a new check"), ".")
        : waitingEmpty ? "New slides show up here once a technician uploads them."
        : filtered ? "Try a different search or filter." : "Slides appear here once a technician uploads them.");
  }

  _row(s) {
    const o = s.overall;
    const res = o.tier
      ? el("div", { class: `res tier-${o.tier}` }, el("i", { class: tone(o.tier) }),
          el("span", {}, TIER_LABEL[o.tier], o.class !== TIER_LABEL[o.tier] ? " " : null, o.class !== TIER_LABEL[o.tier] ? el("small", {}, o.class) : null))
      : el("div", { class: "res" }, "No result");
    const prog = !o.images_read ? el("div", { class: "prog" }, "Could not be read")
      : el("div", { class: "prog" },
          o.fully_reviewed ? el("b", {}, "Fully reviewed") : el("span", {}, el("b", {}, `${o.images_reviewed} of ${o.images_read}`), " reviewed"),
          el("span", { class: "sm" }, ` · ${plural(s.image_count, "image")}`),
          !o.fully_reviewed && o.low_confidence_images ? el("span", { class: "flag" }, `${plural(o.low_confidence_images, "image")} with low confidence`) : null);
    return el("a", { class: "card row", href: `#/slides/${s.id}` },
      el("div", {}, el("div", { class: "code" }, s.patient_code), el("div", { class: "sm" }, when(s.created_at) + (this._role === "technician" ? "" : ` · ${s.uploader_name}`))),
      res, prog, el("span", { class: "arrow", "aria-hidden": "true" }, "→"));
  }
}
