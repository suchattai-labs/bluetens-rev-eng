/**
 * Main Vue application — registers components, creates Vuetify, mounts app.
 */

const app = Vue.createApp({
  setup() {
    Vue.onMounted(() => {
      wsClient.connect();
    });

    Vue.onUnmounted(() => {
      wsClient.disconnect();
    });

    return { store };
  },
});

// Vuetify
const vuetify = Vuetify.createVuetify({
  theme: {
    defaultTheme: "dark",
  },
});
app.use(vuetify);

// Register components
app.component("device-panel", DevicePanel);
app.component("dashboard-view", DashboardView);
app.component("builder-view", BuilderView);
app.component("files-view", FilesView);
app.component("shell-view", ShellView);
app.component("ble-log", BleLog);
app.component("timeline-widget", TimelineWidget);
app.component("section-editor", SectionEditor);
app.component("block-editor", BlockEditor);

// Mount
app.mount("#app");
