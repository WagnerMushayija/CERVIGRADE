import { el, plural } from "../core/dom.js";

/* The panel shown while photos are being graded: a spinner, a running clock, and a check that the server is still alive.
   Grading can take a while, and without this a crash on the server would look the same as "still working". */
export class GradingProgress {
  constructor(api, photoCount) {
    this._api = api;
    this._misses = 0;           // answers missed in a row; three in a row means the server stopped responding
    this._startedAt = 0;
    this._timers = [];
    this._title = el("b", {}, "Finding and grading the cells");
    this._why = el("span", { class: "why" }, `${plural(photoCount, "photo")}. A full photo can take a few minutes on a laptop. Please keep this page open.`);
    this._time = el("span", { class: "time" }, "0:00");
    this._spin = el("span", { class: "spin" });
    this.node = el("div", { class: "working", role: "status" }, this._spin, el("div", {}, this._title, this._why), this._time, el("span", { class: "bar" }));
  }

  start() {
    this._startedAt = Date.now();
    this._timers.push(setInterval(() => this._tick(), 1000));
    this._timers.push(setInterval(() => this._ping(), 5000));
  }

  stop() {
    this._timers.forEach(clearInterval);
    this._timers = [];
  }

  _tick() {
    const sec = Math.round((Date.now() - this._startedAt) / 1000);
    this._time.textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
    if (this._misses < 3 && sec >= 75) {
      this.node.classList.add("slow");
      this._title.textContent = "Still working";
      this._why.textContent = "Big photos can take a few minutes on a laptop CPU. The server is still answering, so this is not frozen.";
    }
  }

  async _ping() {
    if (await this._api.isAlive()) {
      if (this._misses >= 3) {
        this.node.classList.remove("bad");
        this._spin.hidden = false;
        this._title.textContent = "Finding and grading the cells";
        this._why.textContent = "The server is answering again.";
      }
      this._misses = 0;
    } else if (++this._misses >= 3) {
      this.node.classList.remove("slow");
      this.node.classList.add("bad");
      this._spin.hidden = true;
      this._title.textContent = "The server stopped responding";
      this._why.textContent = "Look at the terminal where the backend is running. If it crashed, start it again and re-upload. Nothing is saved until grading finishes.";
    }
  }
}
