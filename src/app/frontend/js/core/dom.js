/* Small helpers for building the page without a framework. */

export const $ = id => document.getElementById(id);
export const pct = x => Math.round(x * 100) + "%";
export const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + "s")}`;
export const when = iso => {
  try { return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); } catch (e) { return iso || ""; }
};
export const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const SVGNS = "http://www.w3.org/2000/svg";

/* el("div", {class: "x"}, child, "text") builds one element. Attributes starting with "on" become event listeners. */
export function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) n.append(k.nodeType ? k : document.createTextNode(k));
  return n;
}

/* Replace everything inside a node, skipping empty values. */
export const fill = (n, ...kids) => n.replaceChildren(...kids.flat().filter(x => x != null && x !== false));

export function arrowIcon() {
  const s = document.createElementNS(SVGNS, "svg");
  s.setAttribute("viewBox", "0 0 14 14"); s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", "1.8"); s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round");
  const p = document.createElementNS(SVGNS, "path");
  p.setAttribute("d", "M3 11L11 3M5 3h6v6");
  s.append(p);
  return s;
}

/* The round pink call-to-action button. */
export const bigBtn = (label, attrs) =>
  el("button", { type: "button", class: "btn", ...attrs }, el("span", {}, label), el("span", { class: "dot" }, arrowIcon()));
