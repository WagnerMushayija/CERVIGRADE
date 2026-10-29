/* Which email domains the server accepts. It tells the page (in /health) so the wording here never goes out of date. */
export class InstitutionInfo {
  constructor() {
    this._domains = ["alustudent.com"];       // used until the server answers
  }

  async load(api) {
    const health = await api.health();
    if (health && Array.isArray(health.email_domains) && health.email_domains.length) this._domains = health.email_domains;
  }

  domain() {
    return this._domains[0];
  }

  label() {
    return this._domains.map(d => "@" + d).join(" or ");
  }
}
