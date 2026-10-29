import { HOME, LINKS, ROLE_LABEL } from "../core/config.js";
import { $, arrowIcon, el } from "../core/dom.js";

/* The top bar. Shows the public links before sign-in, and the links for the person's role after. */
export class Navbar {
  constructor(session, onSignOut) {
    this._session = session;
    this._onSignOut = onSignOut;
  }

  render(path) {
    const user = this._session.user, bar = $("navbar");
    $("nav").classList.toggle("app", !!user);
    $("brand").setAttribute("href", "#" + (user ? HOME[user.role] : "/"));
    if (!user) {
      bar.replaceChildren(
        el("a", { class: "l", href: "#/how" }, "How it works"),
        el("a", { class: "l", href: "#/grades" }, "The grades"),
        el("a", { class: "l", href: "#/keep" }, "Good to know"),
        el("a", { class: "btn small", href: "#/login" }, "Sign in", el("span", { class: "dot" }, arrowIcon())));
      return;
    }
    const first = "/" + path.split("/")[1];
    bar.replaceChildren(
      ...LINKS[user.role].map(([p, label]) => el("a", { class: "l", href: "#" + p, "aria-current": first === p ? "page" : null }, label)),
      el("a", { class: "who", href: "#/account", title: ROLE_LABEL[user.role] }, user.full_name),
      el("button", { type: "button", class: "out", onclick: this._onSignOut }, "Sign out"));
  }
}
