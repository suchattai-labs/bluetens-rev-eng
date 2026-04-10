/**
 * Sidebar device panel — connection status, battery, intensity, navigation.
 */

const DevicePanel = {
  template: `
    <div class="pa-4">
      <!-- Connection indicator -->
      <div class="d-flex align-center mb-4">
        <v-icon :color="store.isConnected ? 'success' : 'error'" class="mr-2">
          mdi-{{ store.isConnected ? 'bluetooth-connect' : 'bluetooth-off' }}
        </v-icon>
        <div>
          <div class="text-subtitle-2">{{ store.isConnected ? 'Connected' : 'Disconnected' }}</div>
          <div class="text-caption text-medium-emphasis" v-if="store.address">{{ store.address }}</div>
        </div>
      </div>

      <v-divider class="mb-3"></v-divider>

      <!-- Device info (when connected) -->
      <template v-if="store.isConnected">
        <v-list density="compact" nav>
          <v-list-item prepend-icon="mdi-chip" :subtitle="store.firmware || '—'">
            <v-list-item-title>Firmware</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-battery" :subtitle="batteryText">
            <v-list-item-title>Battery</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-flash" :subtitle="String(store.intensity)">
            <v-list-item-title>Intensity</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-information" :subtitle="store.status || '—'">
            <v-list-item-title>Status</v-list-item-title>
          </v-list-item>
        </v-list>
      </template>

      <v-divider class="my-3"></v-divider>

      <!-- Navigation -->
      <v-list density="compact" nav mandatory v-model:selected="selectedNav">
        <v-list-item value="dashboard" prepend-icon="mdi-view-dashboard" title="Dashboard"></v-list-item>
        <v-list-item value="builder"   prepend-icon="mdi-pencil-ruler"   title="Builder"></v-list-item>
        <v-list-item value="files"     prepend-icon="mdi-folder"         title="Files"></v-list-item>
        <v-list-item value="shell"     prepend-icon="mdi-console-line"   title="Shell"></v-list-item>
      </v-list>
    </div>
  `,
  setup() {
    const selectedNav = Vue.computed({
      get: () => [store.activeView],
      set: (val) => { store.activeView = val[0]; },
    });

    const batteryText = Vue.computed(() => {
      if (!store.batteryLevel) return "—";
      return `${store.batteryLevel}% (${store.batteryMv} mV)`;
    });

    return { store, selectedNav, batteryText };
  },
};
