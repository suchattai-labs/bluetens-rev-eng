/**
 * Files view — device filesystem management.
 */

const FilesView = {
  template: `
    <div>
      <template v-if="!store.isConnected">
        <v-alert type="info" variant="tonal">
          Connect to a device to manage files.
        </v-alert>
      </template>

      <template v-else>
        <!-- Usage bar -->
        <v-card class="mb-4">
          <v-card-text>
            <div class="text-subtitle-2 mb-1">Filesystem Usage</div>
            <v-progress-linear
              :model-value="usedBytes"
              :max="61440"
              height="20"
              color="primary"
              rounded
            >
              <template #default>{{ usedBytes }} / 61,440 bytes</template>
            </v-progress-linear>
          </v-card-text>
        </v-card>

        <!-- File table -->
        <v-card class="mb-4">
          <v-card-title class="d-flex align-center">
            Files
            <v-spacer></v-spacer>
            <v-btn size="small" variant="text" prepend-icon="mdi-refresh" @click="loadFiles">
              Refresh
            </v-btn>
          </v-card-title>
          <v-table density="compact">
            <thead>
              <tr>
                <th>Name</th>
                <th>Size</th>
                <th>Default</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in store.files" :key="f.name">
                <td>{{ f.name }}</td>
                <td>{{ f.size }} bytes</td>
                <td>
                  <v-icon v-if="f.default" color="success" size="small">mdi-check-circle</v-icon>
                </td>
                <td>
                  <v-btn size="x-small" variant="text" icon @click="startFile(f.name)">
                    <v-icon>mdi-play</v-icon>
                  </v-btn>
                  <v-btn size="x-small" variant="text" icon @click="setDefault(f.name)">
                    <v-icon>mdi-star</v-icon>
                  </v-btn>
                  <v-btn size="x-small" variant="text" icon color="error" @click="removeFile(f.name)">
                    <v-icon>mdi-delete</v-icon>
                  </v-btn>
                </td>
              </tr>
              <tr v-if="!store.files.length">
                <td colspan="4" class="text-center text-medium-emphasis">No files on device.</td>
              </tr>
            </tbody>
          </v-table>
        </v-card>

        <!-- Dangerous actions -->
        <v-card>
          <v-card-text>
            <v-btn color="error" variant="outlined" prepend-icon="mdi-delete-forever" @click="confirmFormat = true">
              Format Filesystem
            </v-btn>
          </v-card-text>
        </v-card>

        <!-- Format confirmation -->
        <v-dialog v-model="confirmFormat" max-width="350">
          <v-card>
            <v-card-title>Format Filesystem?</v-card-title>
            <v-card-text>This will delete ALL files on the device. This cannot be undone.</v-card-text>
            <v-card-actions>
              <v-spacer></v-spacer>
              <v-btn @click="confirmFormat = false">Cancel</v-btn>
              <v-btn color="error" @click="formatFs">Format</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </template>
    </div>
  `,
  setup() {
    const confirmFormat = Vue.ref(false);

    const usedBytes = Vue.computed(() => {
      return store.files.reduce((sum, f) => sum + (f.size || 0), 0);
    });

    async function loadFiles() {
      try {
        const res = await api.listFiles();
        store.files = res.files || [];
      } catch (e) { store.notify(e.message, "error"); }
    }

    async function startFile(name) {
      try { await api.startScript(name); store.notify(`Started: ${name}`, "success"); }
      catch (e) { store.notify(e.message, "error"); }
    }

    async function setDefault(name) {
      try { await api.setDefault(name); store.notify(`Default set: ${name}`, "success"); await loadFiles(); }
      catch (e) { store.notify(e.message, "error"); }
    }

    async function removeFile(name) {
      try { await api.removeFile(name); store.notify(`Deleted: ${name}`, "success"); await loadFiles(); }
      catch (e) { store.notify(e.message, "error"); }
    }

    async function formatFs() {
      confirmFormat.value = false;
      try { await api.formatFs(); store.notify("Filesystem formatted", "success"); await loadFiles(); }
      catch (e) { store.notify(e.message, "error"); }
    }

    return { store, confirmFormat, usedBytes, loadFiles, startFile, setDefault, removeFile, formatFs };
  },
};
