/* Every call to the backend goes through here: it adds the login token, turns failures into readable messages,
   and sends the user back to the sign-in page when the session has ended. */
export class ApiClient {
  constructor(baseUrl, session, onSessionEnded) {
    this.baseUrl = baseUrl;
    this._session = session;
    this._onSessionEnded = onSessionEnded;
  }

  /* opts: method, json (an object to send), body (FormData), signal, blob (true to get the bytes back) */
  async request(path, opts = {}) {
    const headers = {};
    if (this._session.token) headers.Authorization = "Bearer " + this._session.token;
    let body = opts.body;
    if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
    let r;
    try {
      r = await fetch(this.baseUrl + path, { method: opts.method || "GET", headers, body, signal: opts.signal });
    } catch (e) {
      if (e && e.name === "AbortError") throw new Error("This is taking too long, so it was stopped. Check the terminal where the backend runs, then try again.");
      throw new Error(`Could not reach the server at ${this.baseUrl}. Is the backend running?`);
    }
    if (r.status === 401 && this._session.token) {
      this._onSessionEnded("Your session ended. Please sign in again.");
      throw new Error("Your session ended.");
    }
    if (!r.ok) throw await this._errorFrom(r);
    if (r.status === 204) return null;
    return opts.blob ? r.blob() : r.json();
  }

  async _errorFrom(r) {
    let message = "Something went wrong. Please try again.";
    try {
      const j = await r.json();
      if (typeof j.detail === "string") message = j.detail;
      else if (Array.isArray(j.detail) && j.detail.length) {
        const f = j.detail[0];
        const where = (f.loc || []).slice(1).join(" ");
        message = (where ? where.replace(/_/g, " ") + ": " : "") + (f.msg || message);
      }
    } catch (e) { /* keep the generic message */ }
    const err = new Error(message);
    err.status = r.status;
    return err;
  }

  /* A picture the backend only gives to signed-in users: fetch it with the token, hand back a local address for <img>. */
  async blobUrl(path) {
    let url = this._session.imageUrls.get(path);
    if (!url) {
      url = URL.createObjectURL(await this.request(path, { blob: true }));
      this._session.imageUrls.set(path, url);
    }
    return url;
  }

  /* Put a slide photo into an <img>. A photo that fails to load is left as an empty frame. */
  async loadSlideImage(img, slideId, imageId) {
    try { img.src = await this.blobUrl(`/slides/${slideId}/images/${imageId}`); } catch (e) { /* leave the frame empty */ }
  }

  /* Is the backend answering? Used while a long grading job runs. */
  async isAlive(timeoutMs = 4000) {
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), timeoutMs);
    try {
      const r = await fetch(this.baseUrl + "/health", { signal: ac.signal });
      return r.ok;
    } catch (e) {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  /* The public status page (no sign-in needed), or null when the server cannot be reached. */
  async health() {
    try { return await (await fetch(this.baseUrl + "/health")).json(); } catch (e) { return null; }
  }
}
