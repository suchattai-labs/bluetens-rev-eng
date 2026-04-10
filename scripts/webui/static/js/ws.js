/**
 * WebSocket client for real-time BLE events.
 */

const wsClient = {
  _ws: null,
  _reconnectTimer: null,

  connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/ws`;
    this._ws = new WebSocket(url);

    this._ws.onopen = () => {
      console.log("[WS] Connected");
      // Request current state on connect
      this._ws.send(JSON.stringify({ action: "get_state" }));
    };

    this._ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      this._handleEvent(msg);
    };

    this._ws.onclose = () => {
      console.log("[WS] Disconnected, reconnecting in 2s...");
      this._reconnectTimer = setTimeout(() => this.connect(), 2000);
    };

    this._ws.onerror = (err) => {
      console.error("[WS] Error:", err);
    };
  },

  _handleEvent(msg) {
    switch (msg.event) {
      case "state":
        store.updateState(msg);
        break;
      case "notification":
        store.addNotification(msg.type, msg.params);
        break;
      case "ble_traffic":
        store.addBleLog(msg.direction, msg.data);
        break;
      case "scan_results":
        store.scanResults = msg.devices || [];
        break;
      case "command_response":
        store.shellHistory.push({
          type: "rx",
          text: (msg.lines || []).join("\n"),
          ts: new Date().toISOString(),
        });
        break;
      case "upload_progress":
        if (msg.done) store.notify(`Upload complete: ${msg.filename}`, "success");
        break;
      default:
        console.log("[WS] Unknown event:", msg);
    }
  },

  disconnect() {
    clearTimeout(this._reconnectTimer);
    if (this._ws) this._ws.close();
  },
};
