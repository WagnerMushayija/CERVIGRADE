import { ROLE_LABEL } from "../core/config.js";
import { bigBtn, el } from "../core/dom.js";
import { Page } from "./Page.js";

/* Change your own password. */
export class AccountPage extends Page {
  async render(view) {
    this.setTitle("Account");
    const user = this.user;
    const current = el("input", { type: "password", id: "ac", autocomplete: "current-password" });
    const next = el("input", { type: "password", id: "an", autocomplete: "new-password" });
    const again = el("input", { type: "password", id: "an2", autocomplete: "new-password" });
    const msg = el("p", { class: "msg", role: "alert" });
    const go = bigBtn("Change password", { type: "submit" });
    const form = el("form", { class: "card form-card", novalidate: true, style: "max-width:520px" },
      el("div", { class: "field" }, el("label", { for: "ac" }, "Current password"), current),
      el("div", { class: "field" }, el("label", { for: "an" }, "New password"), next, el("span", { class: "hint" }, "At least 8 characters.")),
      el("div", { class: "field" }, el("label", { for: "an2" }, "New password again"), again),
      msg, el("div", { class: "form-actions" }, go));

    form.addEventListener("submit", async e => {
      e.preventDefault();
      msg.className = "msg";
      msg.textContent = "";
      if (next.value.length < 8) { msg.textContent = "The new password needs at least 8 characters."; return; }
      if (next.value !== again.value) { msg.textContent = "The two new passwords do not match."; return; }
      go.disabled = true;
      try {
        await this.api("/auth/change-password", { method: "POST", json: { current_password: current.value, new_password: next.value } });
        current.value = next.value = again.value = "";
        this.toast("Password changed.");
      } catch (err) { msg.textContent = err.message; }
      go.disabled = false;
    });

    view.replaceChildren(
      el("div", { class: "page-head" }, el("div", {}, el("h1", { class: "page-title" }, "Account"),
        el("p", { class: "page-sub" }, `${user.full_name}, ${ROLE_LABEL[user.role].toLowerCase()}. Signed in as ${user.username}.`))),
      form);
  }
}
