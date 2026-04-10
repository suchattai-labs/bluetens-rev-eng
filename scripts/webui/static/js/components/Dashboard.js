/**
 * Dashboard view — device scanning, connection, intensity control, notifications.
 */

const DashboardView = {
  template: `
    <div>
      <!-- Disconnected: scan & connect -->
      <template v-if="!store.isConnected">
        <v-card class="mb-4">
          <v-card-title>Connect to Device</v-card-title>
          <v-card-text>
            <v-row align="center">
              <v-col cols="auto">
                <v-btn
                  color="primary"
                  :loading="store.connection === 'scanning'"
                  @click="scan"
                  prepend-icon="mdi-magnify"
                >
                  Scan for Devices
                </v-btn>
              </v-col>
            </v-row>

            <!-- Scan results -->
            <v-table v-if="store.scanResults.length" density="compact" class="mt-4">
              <thead>
                <tr><th>Address</th><th>Name</th><th>RSSI</th><th></th></tr>
              </thead>
              <tbody>
                <tr v-for="d in store.scanResults" :key="d.address">
                  <td class="text-caption">{{ d.address }}</td>
                  <td>{{ d.name || '—' }}</td>
                  <td>{{ d.rssi }} dBm</td>
                  <td>
                    <v-btn size="small" variant="text" @click="connect(d.address)">Connect</v-btn>
                  </td>
                </tr>
              </tbody>
            </v-table>

            <!-- Manual address -->
            <v-row class="mt-4" align="center">
              <v-col cols="8">
                <v-text-field
                  v-model="manualAddress"
                  label="Manual address (AA:BB:CC:DD:EE:FF)"
                  density="compact"
                  hide-details
                ></v-text-field>
              </v-col>
              <v-col cols="auto">
                <v-btn
                  color="primary"
                  variant="outlined"
                  :loading="store.connection === 'connecting'"
                  @click="connect(manualAddress)"
                >
                  Connect
                </v-btn>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>
      </template>

      <!-- Connected: controls -->
      <template v-if="store.isConnected">
        <!-- Intensity control -->
        <v-card class="mb-4">
          <v-card-title>Intensity Control</v-card-title>
          <v-card-text>
            <div class="d-flex align-center mb-2">
              <span class="text-h4 mr-4">{{ store.intensity }}</span>
              <v-progress-linear
                :model-value="store.intensity"
                max="60"
                height="24"
                color="primary"
                rounded
                class="flex-grow-1"
              >
                <template #default>{{ store.intensity }} / 60</template>
              </v-progress-linear>
            </div>
            <v-btn-group density="compact" variant="outlined">
              <v-btn @click="adjustIntensity(-5)">-5</v-btn>
              <v-btn @click="adjustIntensity(-1)">-1</v-btn>
              <v-btn color="error" @click="stopStim">STOP</v-btn>
              <v-btn @click="adjustIntensity(1)">+1</v-btn>
              <v-btn @click="adjustIntensity(5)">+5</v-btn>
            </v-btn-group>
          </v-card-text>
        </v-card>

        <!-- Script control -->
        <v-card class="mb-4">
          <v-card-title>Script Control</v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="auto">
                <v-btn color="primary" prepend-icon="mdi-play" @click="openFilePicker">
                  Start Script
                </v-btn>
              </v-col>
              <v-col cols="auto">
                <v-btn variant="outlined" prepend-icon="mdi-stop" @click="stopStim">Stop</v-btn>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>

        <!-- Quick actions -->
        <v-card class="mb-4">
          <v-card-title>Quick Actions</v-card-title>
          <v-card-text>
            <v-btn-group variant="outlined" density="compact">
              <v-btn prepend-icon="mdi-refresh" @click="refresh">Refresh</v-btn>
              <v-btn prepend-icon="mdi-power" @click="shutdownDevice">Shutdown</v-btn>
              <v-btn prepend-icon="mdi-restart" @click="resetDevice">Reset</v-btn>
              <v-btn prepend-icon="mdi-link-off" color="error" @click="disconnectDevice">Disconnect</v-btn>
            </v-btn-group>
          </v-card-text>
        </v-card>

        <!-- Notifications -->
        <v-card>
          <v-card-title>Notifications</v-card-title>
          <v-card-text class="notification-log">
            <v-list density="compact" v-if="store.notifications.length">
              <v-list-item v-for="(n, i) in store.notifications" :key="i">
                <template #prepend>
                  <v-icon size="small" :color="notifColor(n.type)">mdi-circle</v-icon>
                </template>
                <v-list-item-title class="text-caption">
                  {{ formatTime(n.ts) }} — {{ n.type }}
                </v-list-item-title>
                <v-list-item-subtitle class="text-caption" v-if="n.params">
                  {{ JSON.stringify(n.params) }}
                </v-list-item-subtitle>
              </v-list-item>
            </v-list>
            <div v-else class="text-medium-emphasis">No notifications yet.</div>
          </v-card-text>
        </v-card>
      </template>

      <!-- File picker dialog -->
      <v-dialog v-model="showFilePicker" max-width="400">
        <v-card>
          <v-card-title>Select Script</v-card-title>
          <v-card-text>
            <v-list density="compact">
              <v-list-item
                v-for="f in store.files"
                :key="f.name"
                :title="f.name"
                :subtitle="f.size + ' bytes'"
                @click="startScript(f.name)"
              ></v-list-item>
            </v-list>
            <div v-if="!store.files.length" class="text-medium-emphasis">
              No files on device. Upload a script first.
            </div>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn @click="showFilePicker = false">Cancel</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </div>
  `,
  setup() {
    const manualAddress = Vue.ref("");
    const showFilePicker = Vue.ref(false);

    async function scan() {
      try { await api.scan(); }
      catch (e) { store.notify(e.message, "error"); }
    }

    async function connect(addr) {
      try {
        await api.connect(addr);
        store.notify("Connected!", "success");
        // Load files for script picker
        const res = await api.listFiles();
        store.files = res.files || [];
      } catch (e) { store.notify(e.message, "error"); }
    }

    async function adjustIntensity(delta) {
      const val = Math.max(1, Math.min(60, store.intensity + delta));
      if (val === store.intensity && delta < 0) return; // already at minimum
      try { await api.setIntensity(val); }
      catch (e) { store.notify(e.message, "error"); }
    }

    async function stopStim() {
      try { await api.stop(); }
      catch (e) { store.notify(e.message, "error"); }
    }

    async function openFilePicker() {
      // Always refresh file list when opening picker
      try {
        const res = await api.listFiles();
        store.files = res.files || [];
      } catch (e) { /* ignore, show whatever we have */ }
      showFilePicker.value = true;
    }

    async function startScript(name) {
      showFilePicker.value = false;
      try { await api.startScript(name); store.notify(`Started: ${name}`, "success"); }
      catch (e) { store.notify(e.message, "error"); }
    }

    async function refresh() {
      try { await api.refresh(); }
      catch (e) { store.notify(e.message, "error"); }
    }

    async function shutdownDevice() {
      try { await api.shutdownDevice(); }
      catch (e) { store.notify(e.message, "error"); }
    }

    async function resetDevice() {
      try { await api.resetDevice(); }
      catch (e) { store.notify(e.message, "error"); }
    }

    async function disconnectDevice() {
      try { await api.disconnect(); }
      catch (e) { store.notify(e.message, "error"); }
    }

    function notifColor(type) {
      const map = { CONNECTED: "success", DISCONNECTED: "error", LOW_BATTERY: "warning", STOPPED: "info" };
      return map[type] || "grey";
    }

    function formatTime(ts) {
      return new Date(ts).toLocaleTimeString();
    }

    return {
      store, manualAddress, showFilePicker,
      scan, connect, adjustIntensity, stopStim, openFilePicker, startScript,
      refresh, shutdownDevice, resetDevice, disconnectDevice,
      notifColor, formatTime,
    };
  },
};
