import { el } from "../core/dom.js";
import { Page } from "./Page.js";

/* The Privacy Policy, in plain words. It is open to everyone (no sign-in) so people can read it before they agree to it.
   Every rule under "The short version" matches something the code really does; the comment after each one says where. */
const RULES = [
  ["Patients are only codes.",
   "The page asks for a patient code (3 to 32 letters, numbers, dashes or underscores) and refuses anything else. There is no field for a name, phone number or address. Please do not type a name in the note box either."],   // routers/slides.py, core/config.py CODE_RE
  ["Only people an administrator has added can sign in.",
   "There is no public sign-up, and only @alustudent.com addresses are accepted."],                                  // core/institution.py
  ["Each role sees only what it needs.",
   "A technician sees only the slides they uploaded. A clinician reviews. Only the administrator can delete records or accounts."],   // routers/slides.py, dependencies.py
  ["Passwords are never stored.",
   "The server keeps only a scrambled version (a salted PBKDF2 hash), so nobody, including the administrator, can read your password."],   // core/security.py
  ["A clinician decides, not the tool.",
   "The tool suggests a grade and shows how sure it is. A clinician confirms or corrects each one, and the correction is saved next to the original grade, which is kept."],   // models/prediction.py FeedbackEntry
  ["Records can be deleted.",
   "When an administrator deletes a patient code, that patient's slides, images, grades and clinician decisions are deleted with it."],   // routers/patients.py remove_patient
  ["We do not sell or share your data.",
   "There are no advertisements and no tracking tools. The one outside service is Google Fonts, which draws the lettering, so Google can see that your browser loaded the page."],   // index.html
  ["This is a prototype, so be careful what you upload.",
   "The connection is not yet encrypted (it uses http, not https) and there are no automatic backups. Until that is fixed, use only public dataset images or test data. It is a research tool, not a medical device."],
];

const COLLECTED = [
  ["Your account", "Your name, institution email, role, a scrambled password, when the account was made and when you last signed in."],
  ["Patient codes", "A code that stands in for a patient. The code is chosen by the clinic, not by us."],
  ["Slides and images", "The microscope photos you upload, their file names, and an optional short note."],
  ["Results", "What the model found in each photo: the grade, how sure it was, the boxes it drew, and which model made them."],
  ["Clinician decisions", "Whether a clinician confirmed or corrected a grade, the corrected grade, who decided, and when."],
];

const SECTIONS = [
  ["Why we keep this", "To grade the photos, to let a clinician review the result, and to keep a record of who decided what. We do not use it for anything else."],
  ["Where it is kept", "On one server, a Microsoft Azure virtual machine in South Africa North. The records are in a database file and the images are in a folder on that same server."],
  ["How long we keep it", "Until an administrator deletes it. There is no automatic expiry yet."],
  ["Your choices", "You can ask the administrator to show you what is held about you, to correct it, or to delete your account. You can withdraw your agreement at any time by asking for your account to be removed."],
  ["Questions and complaints", "Ask your administrator first. Questions about research ethics can go to the ALU Research Ethics Committee at researchethics@alueducation.com."],
];

export class PrivacyPage extends Page {
  async render(view) {
    this.setTitle("Privacy Policy");
    const card = (title, ...kids) => el("section", { class: "card", style: "max-width:820px;margin-bottom:16px;padding:22px 26px" }, el("h3", { style: "margin:0 0 10px" }, title), ...kids);

    view.replaceChildren(
      el("div", { class: "page-head" }, el("div", {},
        el("h1", { class: "page-title" }, "Privacy Policy"),
        el("p", { class: "page-sub" }, "How CerviGrade handles information. Last updated 20 November 2026. A research prototype built at ALU, not a medical device."))),

      card("The short version", el("ol", { style: "padding-left:20px;margin:0;display:grid;gap:12px" },
        RULES.map(([rule, why]) => el("li", {}, el("b", {}, rule + " "), why)))),

      card("What we collect", el("ul", { style: "padding-left:20px;margin:0;display:grid;gap:8px" },
        COLLECTED.map(([what, detail]) => el("li", {}, el("b", {}, what + ": "), detail)))),

      ...SECTIONS.map(([title, text]) => card(title, el("p", { style: "margin:0" }, text))),

      el("p", { class: "hint", style: "max-width:820px" }, "By ticking the box on the sign-in page you agree that the data you enter and the images you upload are used as described here."),
      el("p", {}, el("a", { href: "#/login" }, "Back to sign in")));
  }
}
