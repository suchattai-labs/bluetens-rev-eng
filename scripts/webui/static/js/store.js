/**
 * Reactive state store for the Bluetens Web UI.
 * Uses Vue 3 reactive() — shared across all components.
 */

const store = Vue.reactive({
  // Connection state
  connection: "disconnected", // disconnected | scanning | connecting | connected
  address: "",
  firmware: "",
  batteryMv: 0,
  batteryLevel: 0,
  intensity: 0,
  status: "",

  // UI state
  activeView: "dashboard",
  bleLogVisible: false,
  bleLog: [],         // [{direction, data, ts}]
  notifications: [],  // [{type, params, ts}]
  scanResults: [],    // [{address, name, rssi}]
  files: [],          // [{name, size, default}]
  shellHistory: [],   // [{type: 'tx'|'rx', text, ts}]

  // Builder state
  script: {
    name: "script.txt",
    sections: [],
    loopIndices: [],
  },
  selectedSection: -1,

  // Snackbar
  snackbar: { show: false, text: "", color: "info" },

  // Methods
  get isConnected() {
    return this.connection === "connected";
  },

  notify(text, color = "info") {
    this.snackbar = { show: true, text, color };
  },

  toggleBleLog() {
    this.bleLogVisible = !this.bleLogVisible;
  },

  addBleLog(direction, data) {
    this.bleLog.push({ direction, data, ts: new Date().toISOString() });
    if (this.bleLog.length > 500) this.bleLog.shift();
  },

  addNotification(type, params) {
    this.notifications.unshift({ type, params, ts: new Date().toISOString() });
    if (this.notifications.length > 100) this.notifications.pop();
  },

  updateState(data) {
    this.connection = data.connection || this.connection;
    this.address = data.address ?? this.address;
    this.firmware = data.firmware ?? this.firmware;
    this.batteryMv = data.battery_mv ?? this.batteryMv;
    this.batteryLevel = data.battery_level ?? this.batteryLevel;
    this.intensity = data.intensity ?? this.intensity;
    this.status = data.status ?? this.status;
  },
});
