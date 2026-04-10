/**
 * Section editor — edits the currently selected section and its blocks.
 */

const SectionEditor = {
  template: `
    <v-card v-if="section">
      <v-card-title class="d-flex align-center">
        Section {{ store.selectedSection + 1 }}
        <v-spacer></v-spacer>
        <v-btn size="small" variant="text" color="error" prepend-icon="mdi-delete" @click="deleteSection">
          Delete
        </v-btn>
      </v-card-title>
      <v-card-text>
        <!-- Section-level params -->
        <v-row dense>
          <v-col cols="3">
            <v-text-field
              v-model.number="section.repeat"
              label="Repeat"
              type="number"
              min="1"
              density="compact"
              hide-details
            ></v-text-field>
          </v-col>
          <v-col cols="3">
            <v-text-field
              v-model.number="section.interval"
              label="Interval (ms)"
              type="number"
              min="0"
              density="compact"
              hide-details
            ></v-text-field>
          </v-col>
          <v-col cols="3">
            <v-checkbox
              :model-value="isLoop"
              label="Loop"
              density="compact"
              hide-details
              @update:model-value="toggleLoop"
            ></v-checkbox>
          </v-col>
        </v-row>

        <v-divider class="my-3"></v-divider>

        <!-- Blocks -->
        <div v-for="(blk, bi) in section.blocks" :key="bi" class="mb-3">
          <block-editor :section-index="store.selectedSection" :block-index="bi"></block-editor>
        </div>

        <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" @click="addBlock">
          Add Block
        </v-btn>
      </v-card-text>
    </v-card>
  `,
  setup() {
    const section = Vue.computed(() => store.script.sections[store.selectedSection]);

    const isLoop = Vue.computed(() => store.script.loopIndices.includes(store.selectedSection));

    function toggleLoop(val) {
      const idx = store.selectedSection;
      if (val) {
        if (!store.script.loopIndices.includes(idx)) store.script.loopIndices.push(idx);
      } else {
        store.script.loopIndices = store.script.loopIndices.filter(i => i !== idx);
      }
    }

    function deleteSection() {
      store.script.sections.splice(store.selectedSection, 1);
      store.script.loopIndices = store.script.loopIndices
        .filter(i => i !== store.selectedSection)
        .map(i => i > store.selectedSection ? i - 1 : i);
      store.selectedSection = Math.min(store.selectedSection, store.script.sections.length - 1);
    }

    function addBlock() {
      if (section.value) {
        section.value.blocks.push({ frequency: 100, impulse: 200, cluster: 1, repeat: 1, interval: 0 });
      }
    }

    return { store, section, isLoop, toggleLoop, deleteSection, addBlock };
  },
};
