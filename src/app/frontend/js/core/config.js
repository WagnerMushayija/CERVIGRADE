/* Settings and labels shared by every part of the page. Same grouping and order as the backend (model.py). */

/* Opened as a file: talk to the backend on this computer. Served by the backend (or any host): use the same address. */
export const API_BASE = window.CERVIGRADE_API || (location.protocol === "file:" ? "http://localhost:8000" : location.origin);

export const MAX_IMAGES = 40;
export const MAX_MB = 15;

export const GRADES = ["ASC-H", "ASC-US", "HSIL", "LSIL", "Negative", "SCC"];
export const TIER_OF = { "Negative": "negative", "ASC-US": "low", "LSIL": "low", "ASC-H": "high", "HSIL": "high", "SCC": "high" };
export const TIER_LABEL = { negative: "Negative", low: "Low-grade", high: "High-grade" };
export const TIER_RANK = { negative: 0, low: 1, high: 2 };
export const TIER_COLOR = { negative: "#5DBB85", low: "#E0A23C", high: "#EE6A5B" };
export const SEVERITY = { "SCC": 6, "HSIL": 5, "ASC-H": 4, "LSIL": 3, "ASC-US": 2, "Negative": 1 };
export const MEANING = {
  "Negative": "No abnormal cells", "ASC-US": "Uncertain mild changes", "LSIL": "Mild abnormal changes",
  "ASC-H": "Cannot exclude a high-grade lesion", "HSIL": "Significant abnormal changes", "SCC": "Squamous cell carcinoma",
};
export const ROLE_LABEL = { technician: "Lab technician", clinician: "Clinician", admin: "Administrator" };

/* Where each role lands after signing in, and which links its menu shows. */
export const HOME = { technician: "/new", clinician: "/slides", admin: "/records" };
export const LINKS = {
  technician: [["/new", "New check"], ["/slides", "My slides"]],
  clinician: [["/slides", "Review queue"]],
  admin: [["/records", "Records"], ["/slides", "Slides"], ["/users", "Users"]],
};
