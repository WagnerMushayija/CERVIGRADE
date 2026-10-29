import { ROLE_LABEL } from "../core/config.js";
import { bigBtn, el, plural, when } from "../core/dom.js";
import { DangerButton } from "../core/DangerButton.js";
import { Page } from "./Page.js";

/* A random password for a new account, with no look-alike characters (no 0/O or 1/l). */
function randomPassword() {
  const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const a = new Uint32Array(12);
  crypto.getRandomValues(a);
  return Array.from(a, n => chars[n % chars.length]).join("");
}

/* Admin only: see everyone, add people, edit, deactivate, delete. There is no public sign-up. */
export class UsersPage extends Page {
  async render(view, ctx) {
    this.setTitle("Users");
    this._ctx = ctx;
    this._list = el("div", { class: "list" });
    view.replaceChildren(
      el("div", { class: "page-head" }, el("div", {}, el("h1", { class: "page-title" }, "Users"),
        el("p", { class: "page-sub" }, "There is no public sign-up. Add the people who will use the system here, and remove or deactivate them when they leave."))),
      this._list,
      el("div", { class: "sec" }, el("h2", {}, "Add a user"), this._addForm()));
    await this._load();
  }

  async _load() {
    const users = await this.api("/users");
    if (!this._ctx.isCurrent()) return;
    this._list.replaceChildren(...users.map(u => this._userRow(u)));
  }

  _addForm() {
    const { institution } = this.app;
    const name = el("input", { type: "text", id: "nf", maxlength: "80", autocomplete: "off", required: true });
    const email = el("input", { type: "email", id: "nu", maxlength: "80", autocomplete: "off", autocapitalize: "none", spellcheck: "false", placeholder: "name@" + institution.domain(), required: true });
    const role = el("select", { class: "in", id: "nr" }, ...Object.entries(ROLE_LABEL).map(([v, l]) => el("option", { value: v }, l)));
    const password = el("input", { type: "text", id: "np", autocomplete: "off", spellcheck: "false", required: true });
    const generate = el("button", { type: "button", class: "linkbtn", onclick: () => { password.value = randomPassword(); } }, "Generate one");
    const msg = el("p", { class: "msg", role: "alert" });
    const add = bigBtn("Add user", { type: "submit" });
    const form = el("form", { class: "card form-card", novalidate: true },
      el("div", { class: "grid2" },
        el("div", { class: "field" }, el("label", { for: "nf" }, "Full name"), name),
        el("div", { class: "field" }, el("label", { for: "nu" }, "Email"), email, el("span", { class: "hint" }, `Must be an ${institution.label()} address.`)),
        el("div", { class: "field" }, el("label", { for: "nr" }, "Role"), role),
        el("div", { class: "field" }, el("label", { for: "np" }, "Starting password"), password,
          el("span", { class: "hint" }, "At least 8 characters. ", generate, ". Give it to them in person; they can change it under their account."))),
      msg, el("div", { class: "form-actions" }, add));
    form.addEventListener("submit", async e => {
      e.preventDefault();
      msg.textContent = "";
      msg.className = "msg";
      if (!name.value.trim() || !email.value.trim() || !password.value) { msg.textContent = "Fill in every field."; return; }
      add.disabled = true;
      try {
        const u = await this.api("/users", { method: "POST", json: { username: email.value, full_name: name.value, role: role.value, password: password.value } });
        this.toast(`Added ${u.full_name} (${ROLE_LABEL[u.role].toLowerCase()}).`);
        name.value = email.value = password.value = "";
        await this._load();
      } catch (err) { msg.textContent = err.message; }
      add.disabled = false;
    });
    return form;
  }

  _userRow(u) {
    const me = u.id === this.user.id;
    const box = el("article", { class: "card urow" });
    const edit = el("div", { class: "editbox", hidden: true });
    const top = el("div", { class: "urow-top" },
      el("div", {}, el("div", { class: "nm" }, u.full_name, me ? el("span", { class: "badge you" }, "You") : null), el("div", { class: "sm" }, u.username)),
      el("div", {}, el("span", { class: "badge" + (u.active ? "" : " off") }, u.active ? ROLE_LABEL[u.role] : ROLE_LABEL[u.role] + ", inactive")),
      el("div", { class: "sm" }, u.last_login ? `Last sign-in ${when(u.last_login)}` : "Never signed in", el("br"),
        u.role === "technician" ? `${plural(u.slides_uploaded, "slide")} uploaded` : u.role === "clinician" ? `${plural(u.reviews_made, "grade")} reviewed` : ""),
      el("div", { class: "acts" },
        el("button", { type: "button", class: "pill", onclick: () => { edit.hidden = !edit.hidden; } }, "Edit"),
        me ? null : el("button", { type: "button", class: "pill", onclick: () => this._toggleActive(u) }, u.active ? "Deactivate" : "Reactivate"),
        me ? null : new DangerButton(this.app.toast, "Delete", "Click again to delete", async () => {
          await this.api(`/users/${u.id}`, { method: "DELETE" });
          this.toast("User deleted.");
          await this._load();
        }).node));
    edit.append(...this._editFields(u, edit));
    box.append(top, edit);
    return box;
  }

  async _toggleActive(u) {
    try {
      await this.api(`/users/${u.id}`, { method: "PATCH", json: { active: !u.active } });
      this.toast(u.active ? "Account deactivated." : "Account reactivated.");
      await this._load();
    } catch (e) { this.toast(e.message, true); }
  }

  _editFields(u, edit) {
    const name = el("input", { type: "text", id: `en${u.id}`, value: u.full_name, maxlength: "80" });
    const role = el("select", { class: "in", id: `er${u.id}` }, ...Object.entries(ROLE_LABEL).map(([v, l]) => el("option", { value: v }, l)));
    role.value = u.role;
    const password = el("input", { type: "text", id: `ep${u.id}`, placeholder: "Leave empty to keep it", autocomplete: "off", spellcheck: "false" });
    const msg = el("p", { class: "msg", role: "alert" });
    const save = el("button", { type: "button", class: "btn", style: "padding:12px 24px" }, "Save changes");
    save.addEventListener("click", async () => {
      msg.textContent = "";
      save.disabled = true;
      const json = {};
      if (name.value.trim() && name.value.trim() !== u.full_name) json.full_name = name.value.trim();
      if (role.value !== u.role) json.role = role.value;
      if (password.value) json.password = password.value;
      if (!Object.keys(json).length) { edit.hidden = true; save.disabled = false; return; }
      try { await this.api(`/users/${u.id}`, { method: "PATCH", json }); this.toast("Saved."); await this._load(); }
      catch (e) { msg.textContent = e.message; save.disabled = false; }
    });
    return [
      el("div", { class: "grid3" },
        el("div", { class: "field" }, el("label", { for: `en${u.id}` }, "Full name"), name),
        el("div", { class: "field" }, el("label", { for: `er${u.id}` }, "Role"), role),
        el("div", { class: "field" }, el("label", { for: `ep${u.id}` }, "New password"), password)),
      msg,
      el("div", { class: "form-actions" }, save),
    ];
  }
}
