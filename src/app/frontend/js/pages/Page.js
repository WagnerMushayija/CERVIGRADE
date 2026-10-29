/* The rulebook every screen follows. A page gets the App (so it can reach the server, the toast, the signed-in user)
   and must say how to draw itself. The router only ever calls render(), so it never needs to know which page it has.

   render(view, ctx):
     view  the element to draw into
     ctx   { query, params, isCurrent() }  isCurrent() turns false once the person has gone to another page,
           so a slow answer from the server does not draw over the new page. */
export class Page {
  constructor(app) {
    this.app = app;
  }

  get user() { return this.app.session.user; }

  /* Short helpers so a page can write this.api(...) and this.toast(...) */
  api(path, opts) { return this.app.api.request(path, opts); }
  toast(text, isError) { this.app.toast.show(text, isError); }

  setTitle(text) { document.title = `${text} · CerviGrade`; }

  /* Draw the page into `view`. Subclasses must implement this. */
  async render(view, ctx) {
    throw new Error(`${this.constructor.name} must implement render()`);
  }
}
