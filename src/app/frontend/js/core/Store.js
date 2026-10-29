/* Remembers a few values for the length of the browser tab. Falls back to memory when the browser blocks storage. */
export class Store {
  constructor() {
    this._memory = {};
  }

  get(key) {
    try { return sessionStorage.getItem(key); } catch (e) { return this._memory[key] || null; }
  }

  set(key, value) {
    try { sessionStorage.setItem(key, value); } catch (e) { this._memory[key] = value; }
  }

  del(key) {
    try { sessionStorage.removeItem(key); } catch (e) { delete this._memory[key]; }
  }
}
