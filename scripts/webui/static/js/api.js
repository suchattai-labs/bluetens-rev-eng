/**
 * REST API client for Bluetens Web UI.
 */

const api = {
  async _fetch(url, opts = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    if (!res.ok) {
      let msg = res.statusText;
      try {
        const body = await res.json();
        msg = body.error || msg;
      } catch { /* ignore parse errors */ }
      throw new Error(msg);
    }
    return res.json();
  },

  // Device
  getState()          { return this._fetch("/api/device/state"); },
  scan()              { return this._fetch("/api/device/scan", { method: "POST" }); },
  connect(address)    { return this._fetch("/api/device/connect", { method: "POST", body: JSON.stringify({ address }) }); },
  disconnect()        { return this._fetch("/api/device/disconnect", { method: "POST" }); },
  setIntensity(value) { return this._fetch("/api/device/intensity", { method: "POST", body: JSON.stringify({ value }) }); },
  stop()              { return this._fetch("/api/device/stop", { method: "POST" }); },
  startScript(name)   { return this._fetch(`/api/device/start/${encodeURIComponent(name)}`, { method: "POST" }); },
  refresh()           { return this._fetch("/api/device/refresh", { method: "POST" }); },
  shutdownDevice()    { return this._fetch("/api/device/shutdown", { method: "POST" }); },
  resetDevice()       { return this._fetch("/api/device/reset", { method: "POST" }); },
  sendRaw(command)    { return this._fetch("/api/device/raw", { method: "POST", body: JSON.stringify({ command }) }); },

  // Files
  listFiles()         { return this._fetch("/api/files/"); },
  removeFile(name)    { return this._fetch(`/api/files/${encodeURIComponent(name)}`, { method: "DELETE" }); },
  setDefault(name)    { return this._fetch("/api/files/default", { method: "POST", body: JSON.stringify({ filename: name }) }); },
  formatFs()          { return this._fetch("/api/files/format", { method: "POST" }); },

  // Scripts
  previewScript(script)          { return this._fetch("/api/scripts/preview", { method: "POST", body: JSON.stringify(script) }); },
  uploadScript(script, start)    { return this._fetch("/api/scripts/upload", { method: "POST", body: JSON.stringify({ script, start }) }); },
  getPresets()                   { return this._fetch("/api/scripts/presets"); },
  generatePreset(preset, params) { return this._fetch("/api/scripts/preset", { method: "POST", body: JSON.stringify({ preset, params }) }); },
  convertFunscript(data)         { return this._fetch("/api/scripts/funscript", { method: "POST", body: JSON.stringify(data) }); },
};
