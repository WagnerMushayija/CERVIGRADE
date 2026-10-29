import { HOME } from "./config.js";
import { $, el, reduceMotion } from "./dom.js";

const PUBLIC_SECTIONS = ["how", "who", "grades", "keep"];

/* Looks at the address (#/slides/12) and draws the right page. Every page is a Page subclass, so the router
   only has to say render(). A page that is not allowed for the signed-in role sends the person home instead. */
export class Router {
  /* routes: [{ pattern, Page, roles?, open?, params? }], tried in order. `open` pages need no sign-in. */
  constructor(app, routes) {
    this._app = app;
    this._routes = routes;
    this._navId = 0;                  // grows with every navigation, so a slow page can tell it is out of date
    window.addEventListener("hashchange", () => this.route());
  }

  route() {
    const app = this._app, session = app.session, user = session.user;
    const mine = ++this._navId;
    const raw = location.hash.replace(/^#/, "") || "/";
    const [pathPart, queryPart] = raw.split("?");
    const parts = pathPart.split("/").filter(Boolean);
    const path = "/" + parts.join("/");
    const query = new URLSearchParams(queryPart || "");

    const isPublicPage = parts.length === 0 || (parts.length === 1 && PUBLIC_SECTIONS.includes(parts[0]));
    if (user && (isPublicPage || path === "/login")) { location.replace("#" + HOME[user.role]); return; }
    app.navbar.render(path);

    if (isPublicPage) { this._showPublic(parts); return; }

    $("public").hidden = true;
    $("app").hidden = false;
    window.scrollTo(0, 0);
    const view = $("view");
    const ctx = { query, params: {}, isCurrent: () => mine === this._navId };

    if (!user && path !== "/login") { session.notice = "Please sign in to continue."; location.replace("#/login"); return; }

    const match = this._match(path, user ? user.role : null);
    if (!match) { location.replace("#" + HOME[user.role]); return; }
    ctx.params = match.params;
    view.replaceChildren(el("p", { class: "count" }, "Loading…"));
    Promise.resolve(new match.route.Page(app).render(view, ctx)).catch(e => {
      if (ctx.isCurrent()) view.replaceChildren(el("div", { class: "empty" }, el("b", {}, "This page could not load."), e.message));
    });
  }

  _match(path, role) {
    for (const route of this._routes) {
      const m = route.pattern.exec(path);
      if (m && (route.open || !route.roles || route.roles.includes(role))) return { route, params: route.params ? route.params(m) : {} };
    }
    return null;
  }

  _showPublic(parts) {
    $("public").hidden = false;
    $("app").hidden = true;
    document.title = "CerviGrade";
    const target = parts.length ? $(parts[0]) : null;
    if (target) target.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "start" });
    else window.scrollTo(0, 0);
  }
}
