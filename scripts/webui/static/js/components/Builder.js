/**
 * Builder view — script timeline editor with sections and blocks.
 */

const BuilderView = {
  template: `
    <div>
      <!-- Script header -->
      <v-card class="mb-4">
        <v-card-text>
          <v-row align="center">
            <v-col cols="4">
              <v-text-field
                v-model="store.script.name"
                label="Script name"
                density="compact"
                hide-details
              ></v-text-field>
            </v-col>
            <v-col cols="auto">
              <v-chip size="small" class="mr-2">{{ store.script.sections.length }} sections</v-chip>
              <v-chip size="small">{{ totalDuration }}</v-chip>
            </v-col>
            <v-spacer></v-spacer>
            <v-col cols="auto">
              <v-btn
                color="secondary"
                variant="outlined"
                prepend-icon="mdi-lightning-bolt"
                @click="openPresetPicker"
                class="mr-2"
              >
                Presets
              </v-btn>
              <v-btn
                color="secondary"
                variant="outlined"
                prepend-icon="mdi-file-import"
                @click="showFunscript = true"
              >
                Funscript
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- Timeline -->
      <v-card class="mb-4">
        <v-card-title class="d-flex align-center">
          Timeline
          <v-spacer></v-spacer>
          <v-btn size="small" variant="text" prepend-icon="mdi-plus" @click="addSection">
            Add Section
          </v-btn>
        </v-card-title>
        <v-card-text>
          <timeline-widget></timeline-widget>
        </v-card-text>
      </v-card>

      <!-- Section editor -->
      <section-editor v-if="store.selectedSection >= 0"></section-editor>

      <!-- Actions -->
      <v-card class="mt-4">
        <v-card-text>
          <v-btn-group variant="outlined" density="compact">
            <v-btn prepend-icon="mdi-eye" @click="preview">Preview Raw</v-btn>
            <v-btn prepend-icon="mdi-upload" @click="upload(false)" :disabled="!store.isConnected">
              Upload
            </v-btn>
            <v-btn prepend-icon="mdi-play-circle" color="primary" @click="upload(true)" :disabled="!store.isConnected">
              Upload + Start
            </v-btn>
          </v-btn-group>
        </v-card-text>
      </v-card>

      <!-- Raw preview dialog -->
      <v-dialog v-model="showPreview" max-width="600">
        <v-card>
          <v-card-title>Raw Script Preview</v-card-title>
          <v-card-text>
            <pre class="shell-output">{{ previewText }}</pre>
            <div class="mt-2 text-caption">{{ previewSize }} bytes</div>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn @click="showPreview = false">Close</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Funscript import dialog -->
      <v-dialog v-model="showFunscript" max-width="550">
        <v-card>
          <v-card-title>Import Funscript</v-card-title>
          <v-card-text>
            <v-file-input
              accept=".funscript,.json"
              label="Select .funscript file"
              density="compact"
              hide-details
              class="mb-4"
              @update:modelValue="onFunscriptFile"
            ></v-file-input>

            <div v-if="funscriptInfo" class="text-caption text-medium-emphasis mb-4">
              {{ funscriptInfo }}
            </div>

            <v-row dense>
              <v-col cols="6">
                <div class="text-subtitle-2 mb-2">Low intensity (slow movement)</div>
                <v-text-field
                  v-model.number="fsParams.freq_high"
                  label="Frequency (Hz)"
                  hint="Higher freq = gentle"
                  type="number"
                  density="compact"
                  persistent-hint
                  class="mb-2"
                ></v-text-field>
                <v-text-field
                  v-model.number="fsParams.impulse_low"
                  label="Impulse (us)"
                  hint="Lower impulse = gentle"
                  type="number"
                  density="compact"
                  persistent-hint
                ></v-text-field>
              </v-col>
              <v-col cols="6">
                <div class="text-subtitle-2 mb-2">High intensity (fast movement)</div>
                <v-text-field
                  v-model.number="fsParams.freq_low"
                  label="Frequency (Hz)"
                  hint="Lower freq = strong"
                  type="number"
                  density="compact"
                  persistent-hint
                  class="mb-2"
                ></v-text-field>
                <v-text-field
                  v-model.number="fsParams.impulse_high"
                  label="Impulse (us)"
                  hint="Higher impulse = strong"
                  type="number"
                  density="compact"
                  persistent-hint
                ></v-text-field>
              </v-col>
            </v-row>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn @click="showFunscript = false">Cancel</v-btn>
            <v-btn
              color="primary"
              variant="flat"
              :loading="fsLoading"
              :disabled="!funscriptActions"
              @click="convertFunscript"
            >
              Convert
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Preset picker dialog -->
      <v-dialog v-model="showPresetPicker" max-width="550">
        <v-card>
          <v-card-title>Pattern Presets</v-card-title>
          <v-card-text>
            <v-select
              v-model="selectedPreset"
              :items="presetList"
              item-title="name"
              item-value="id"
              label="Select preset"
              density="compact"
              hide-details
              class="mb-3"
            ></v-select>

            <div v-if="selectedPresetDesc" class="text-caption text-medium-emphasis mb-4">
              {{ selectedPresetDesc }}
            </div>

            <template v-if="presetFields.length">
              <v-row dense v-for="field in presetFields" :key="field.key">
                <v-col>
                  <v-text-field
                    v-model="presetParams[field.key]"
                    :label="field.label"
                    :hint="field.hint"
                    type="number"
                    density="compact"
                    persistent-hint
                  ></v-text-field>
                </v-col>
              </v-row>
            </template>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn @click="showPresetPicker = false">Cancel</v-btn>
            <v-btn
              color="primary"
              variant="flat"
              :loading="presetLoading"
              @click="generatePreset"
            >
              Generate
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </div>
  `,
  setup() {
    const showPreview = Vue.ref(false);
    const previewText = Vue.ref("");
    const previewSize = Vue.ref(0);

    // Funscript state
    const showFunscript = Vue.ref(false);
    const funscriptActions = Vue.ref(null);
    const funscriptInfo = Vue.ref("");
    const fsLoading = Vue.ref(false);
    const fsParams = Vue.ref({
      freq_low: 2,
      freq_high: 150,
      impulse_low: 50,
      impulse_high: 300,
    });

    function onFunscriptFile(files) {
      const file = Array.isArray(files) ? files[0] : files;
      if (!file) { funscriptActions.value = null; funscriptInfo.value = ""; return; }
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = JSON.parse(e.target.result);
          const actions = data.actions || [];
          if (actions.length < 2) throw new Error("Need at least 2 actions");
          funscriptActions.value = actions;
          const dur = (actions[actions.length - 1].at - actions[0].at) / 1000;
          funscriptInfo.value = `${actions.length} actions, ~${Math.round(dur)}s duration`;
        } catch (err) {
          funscriptActions.value = null;
          funscriptInfo.value = "Error: " + err.message;
        }
      };
      reader.readAsText(file);
    }

    async function convertFunscript() {
      if (!funscriptActions.value) return;
      fsLoading.value = true;
      try {
        const res = await api.convertFunscript({
          actions: funscriptActions.value,
          ...fsParams.value,
        });
        store.script.sections = res.sections;
        store.script.loopIndices = res.loop_indices || [];
        store.selectedSection = res.sections.length ? 0 : -1;
        showFunscript.value = false;
        const info = res.block_count ? ` (${res.block_count} blocks)` : "";
        store.notify("Funscript converted" + info, "success");
      } catch (e) {
        store.notify(e.message, "error");
      } finally {
        fsLoading.value = false;
      }
    }

    // Preset state
    const showPresetPicker = Vue.ref(false);
    const presetList = Vue.ref([]);
    const presetDefaults = Vue.ref({});
    const presetFieldDefs = Vue.ref({});
    const selectedPreset = Vue.ref("");
    const presetParams = Vue.ref({});
    const presetLoading = Vue.ref(false);

    const selectedPresetDesc = Vue.computed(() => {
      const p = presetList.value.find(x => x.id === selectedPreset.value);
      return p ? p.desc : "";
    });

    const presetFields = Vue.computed(() => {
      return presetFieldDefs.value[selectedPreset.value] || [];
    });

    // When preset selection changes, reset params to defaults
    Vue.watch(selectedPreset, (id) => {
      if (id && presetDefaults.value[id]) {
        presetParams.value = { ...presetDefaults.value[id] };
      }
    });

    const totalDuration = Vue.computed(() => {
      let ms = 0;
      for (const sec of store.script.sections) {
        let secMs = 0;
        for (const blk of (sec.blocks || [])) {
          const cycleDur = (1000 / (blk.frequency || 100)) * (blk.cluster || 1) + (blk.interval || 0);
          secMs += cycleDur * (blk.repeat || 1);
        }
        ms += secMs * (sec.repeat || 1);
      }
      const secs = Math.round(ms / 1000);
      if (secs < 60) return `${secs}s`;
      return `${Math.floor(secs / 60)}m ${secs % 60}s`;
    });

    function addSection() {
      store.script.sections.push({
        blocks: [{ frequency: 100, impulse: 200, cluster: 1, repeat: 1, interval: 0 }],
        repeat: 1,
        interval: 0,
      });
      store.selectedSection = store.script.sections.length - 1;
    }

    function buildScriptPayload() {
      return {
        name: store.script.name,
        sections: store.script.sections,
        loop_indices: store.script.loopIndices,
      };
    }

    async function preview() {
      try {
        const res = await api.previewScript(buildScriptPayload());
        previewText.value = res.raw;
        previewSize.value = res.byte_size;
        showPreview.value = true;
      } catch (e) { store.notify(e.message, "error"); }
    }

    async function upload(start) {
      try {
        await api.uploadScript(buildScriptPayload(), start);
        store.notify(start ? "Uploaded & started!" : "Uploaded!", "success");
      } catch (e) { store.notify(e.message, "error"); }
    }

    async function openPresetPicker() {
      // Fetch presets metadata if not loaded yet
      if (!presetList.value.length) {
        try {
          const res = await api.getPresets();
          presetList.value = res.presets;
          presetDefaults.value = res.defaults;
          presetFieldDefs.value = res.fields;
        } catch (e) {
          store.notify(e.message, "error");
          return;
        }
      }
      // Select first preset if none selected
      if (!selectedPreset.value && presetList.value.length) {
        selectedPreset.value = presetList.value[0].id;
        presetParams.value = { ...presetDefaults.value[selectedPreset.value] };
      }
      showPresetPicker.value = true;
    }

    async function generatePreset() {
      presetLoading.value = true;
      try {
        const res = await api.generatePreset(selectedPreset.value, presetParams.value);
        // Load generated script into the builder
        store.script.sections = res.sections;
        store.script.loopIndices = res.loop_indices || [];
        store.selectedSection = res.sections.length ? 0 : -1;
        showPresetPicker.value = false;
        store.notify("Preset loaded into builder", "success");
      } catch (e) {
        store.notify(e.message, "error");
      } finally {
        presetLoading.value = false;
      }
    }

    return {
      store, showPreview, previewText, previewSize, totalDuration,
      addSection, preview, upload,
      showFunscript, funscriptActions, funscriptInfo, fsLoading, fsParams,
      onFunscriptFile, convertFunscript,
      showPresetPicker, presetList, selectedPreset, presetParams,
      presetFields, selectedPresetDesc, presetLoading,
      openPresetPicker, generatePreset,
    };
  },
};
