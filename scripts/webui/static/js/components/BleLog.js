/**
 * BLE Log panel — collapsible bottom panel showing TX/RX traffic.
 */

const BleLog = {
  template: `
    <v-sheet class="ble-log-panel pa-2">
      <div class="d-flex align-center mb-1">
        <v-icon size="small" class="mr-2">mdi-console</v-icon>
        <span class="text-subtitle-2">BLE Traffic Log</span>
        <v-spacer></v-spacer>
        <v-btn size="x-small" variant="text" @click="store.bleLog = []">Clear</v-btn>
        <v-btn size="x-small" variant="text" icon @click="store.bleLogVisible = false">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </div>
      <div ref="logEl" style="max-height: 200px; overflow-y: auto;">
        <div v-for="(entry, i) in store.bleLog" :key="i" :class="entry.direction === 'tx' ? 'log-tx' : 'log-rx'">
          {{ formatTime(entry.ts) }} [{{ entry.direction.toUpperCase() }}] {{ entry.data }}
        </div>
        <div v-if="!store.bleLog.length" class="text-medium-emphasis">No traffic yet.</div>
      </div>
    </v-sheet>
  `,
  setup() {
    const logEl = Vue.ref(null);

    function formatTime(ts) {
      return new Date(ts).toLocaleTimeString();
    }

    return { store, logEl, formatTime };
  },
};
