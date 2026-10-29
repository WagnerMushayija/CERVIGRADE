/* Who is signed in. Holds the login token, the user, and the one-time message shown on the sign-in page. */
export class Session {
  constructor(store) {
    this._store = store;
    this.token = store.get("cg_token");
    this.user = null;
    this.notice = "";            // shown once on the sign-in page
    this.imageUrls = new Map();  // photos already downloaded, so going back to a slide does not fetch them again
  }

  get signedIn() {
    return !!this.user;
  }

  signIn(token, user) {
    this.token = token;
    this.user = user;
    this._store.set("cg_token", token);
    this.notice = "";
  }

  /* Forget the user and everything downloaded for them. `message` is shown once on the sign-in page. */
  end(message) {
    this.token = null;
    this.user = null;
    this._store.del("cg_token");
    this.imageUrls.forEach(url => URL.revokeObjectURL(url));
    this.imageUrls.clear();
    this.notice = message || "";
  }

  /* The notice, once. */
  takeNotice() {
    const n = this.notice;
    this.notice = "";
    return n;
  }
}
