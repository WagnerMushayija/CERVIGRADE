import { PublicChrome } from "./components/PublicChrome.js";
import { Navbar } from "./components/Navbar.js";
import { API_BASE } from "./core/config.js";
import { $ } from "./core/dom.js";
import { ApiClient } from "./core/ApiClient.js";
import { InstitutionInfo } from "./core/InstitutionInfo.js";
import { Router } from "./core/Router.js";
import { Session } from "./core/Session.js";
import { Store } from "./core/Store.js";
import { Toast } from "./core/Toast.js";
import { AccountPage } from "./pages/AccountPage.js";
import { LoginPage } from "./pages/LoginPage.js";
import { NewCheckPage } from "./pages/NewCheckPage.js";
import { RecordsPage } from "./pages/RecordsPage.js";
import { SlideDetailPage } from "./pages/SlideDetailPage.js";
import { SlideListPage } from "./pages/SlideListPage.js";
import { UsersPage } from "./pages/UsersPage.js";

/* Which page answers which address, and which roles may open it. */
const ROUTES = [
  { pattern: /^\/login$/, Page: LoginPage, open: true },
  { pattern: /^\/new$/, Page: NewCheckPage, roles: ["technician"] },
  { pattern: /^\/slides$/, Page: SlideListPage },
  { pattern: /^\/slides\/(\d+)$/, Page: SlideDetailPage, params: m => ({ id: Number(m[1]) }) },
  { pattern: /^\/users$/, Page: UsersPage, roles: ["admin"] },
  { pattern: /^\/records$/, Page: RecordsPage, roles: ["admin"] },
  { pattern: /^\/account$/, Page: AccountPage },
];

/* The whole page: builds the shared parts once and hands them to every screen. */
export class App {
  constructor() {
    this.store = new Store();
    this.session = new Session(this.store);
    this.api = new ApiClient(API_BASE, this.session, message => this._sessionEnded(message));
    this.toast = new Toast($("toast"));
    this.institution = new InstitutionInfo();
    this.state = { slideList: null };               // what a screen wants to remember between visits
    this.navbar = new Navbar(this.session, () => this.signOut());
    this.router = new Router(this, ROUTES);
  }

  async start() {
    new PublicChrome().init();
    this.institution.load(this.api);
    if (this.session.token) {
      try { this.session.user = await this.api.request("/auth/me"); }
      catch (e) { if (this.session.token) this.session.end(); }
    }
    this.router.route();
  }

  signOut() {
    this.session.end("");
    location.hash = "#/";
    this.router.route();
  }

  _sessionEnded(message) {
    this.session.end(message);
    location.hash = "#/login";
    this.router.route();
  }
}
