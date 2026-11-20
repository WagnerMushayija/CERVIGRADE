import { HOME } from "../core/config.js";
import { bigBtn, el } from "../core/dom.js";
import { Page } from "./Page.js";

/* The sign-in form. Only institution email addresses are accepted; the server enforces it and says why when it refuses. */
export class LoginPage extends Page {
  async render(view) {
    this.setTitle("Sign in");
    const { session, institution, router } = this.app;
    const msg = el("p", { class: "msg", role: "alert" });
    const email = el("input", { type: "email", id: "lu", autocomplete: "username", autocapitalize: "none", spellcheck: "false", placeholder: "you@" + institution.domain(), required: true });
    const password = el("input", { type: "password", id: "lp", autocomplete: "current-password", required: true });
    const agree = el("input", { type: "checkbox", id: "lc" });
    const consent = el("div", { class: "field" },
      el("label", { for: "lc", style: "display:flex;gap:10px;align-items:flex-start;font-weight:400" }, agree,
        el("span", {}, "I have read the ", el("a", { href: "#/privacy" }, "Privacy Policy"), " and I agree that the data I enter and the images I upload are used as it describes.")));
    const go = bigBtn("Sign in", { type: "submit" });
    const form = el("form", { class: "card form-card", novalidate: true },
      el("div", { class: "field" }, el("label", { for: "lu" }, "Institution email"), email),
      el("div", { class: "field" }, el("label", { for: "lp" }, "Password"), password),
      consent,
      msg,
      el("div", { class: "form-actions" }, go));

    form.addEventListener("submit", async e => {
      e.preventDefault();
      if (!email.value.trim() || !password.value) { msg.textContent = "Enter your institution email and password."; return; }
      if (!agree.checked) { msg.textContent = "Please tick the box to agree to the Privacy Policy."; return; }
      go.disabled = true;
      msg.textContent = "";
      try {
        const r = await this.api("/auth/login", { method: "POST", json: { username: email.value, password: password.value } });
        try { localStorage.setItem("cervigrade_consent_v1", new Date().toISOString()); } catch (e) { /* private mode: the tick is still required each time */ }
        session.signIn(r.token, r.user);
        location.hash = "#" + HOME[session.user.role];
        router.route();
      } catch (err) {
        msg.textContent = err.message;
        go.disabled = false;
        password.value = "";
        password.focus();
      }
    });

    const notice = session.takeNotice();
    view.replaceChildren(el("div", { class: "login-wrap" },
      el("h1", {}, "Sign in"),
      el("p", { class: "page-sub", style: "margin-bottom:28px" }, `Only people with an ${institution.label()} email address can sign in. Accounts are created by your administrator.`),
      notice ? el("div", { class: "notice", role: "status" }, notice) : null,
      form));
    email.focus();
  }
}
