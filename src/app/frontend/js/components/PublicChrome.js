import { $ } from "../core/dom.js";

/* The small behaviours of the public pages: the bar's shadow when scrolled, sections fading in, and the grade tabs. */
export class PublicChrome {
  init() {
    this._stickyBar();
    this._revealOnScroll();
    this._gradeTabs();
  }

  _stickyBar() {
    const nav = $("nav");
    const on = () => nav.classList.toggle("scrolled", window.scrollY > 8);
    window.addEventListener("scroll", on, { passive: true });
    on();
  }

  _revealOnScroll() {
    const items = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window)) { items.forEach(i => i.classList.add("in")); return; }
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    }), { threshold: 0.12 });
    items.forEach((item, n) => { item.style.transitionDelay = ((n % 3) * 60) + "ms"; io.observe(item); });
  }

  _gradeTabs() {
    const tabs = [$("tab-three"), $("tab-six")], panels = [$("panel-three"), $("panel-six")];
    const show = i => tabs.forEach((t, k) => {
      t.setAttribute("aria-selected", k === i);
      t.tabIndex = k === i ? 0 : -1;
      panels[k].hidden = k !== i;
    });
    tabs.forEach((t, i) => {
      t.addEventListener("click", () => show(i));
      t.addEventListener("keydown", e => {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") { const j = (i + 1) % 2; show(j); tabs[j].focus(); }
      });
    });
  }
}
