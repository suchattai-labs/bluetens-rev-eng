/**
 * Block editor — edits a single stimulation block within a section.
 */

const BlockEditor = {
  props: {
    sectionIndex: { type: Number, required: true },
    blockIndex: { type: Number, required: true },
  },
  template: `
    <v-sheet rounded border class="pa-3">
      <div class="d-flex align-center mb-2">
        <span class="text-subtitle-2">Block {{ blockIndex + 1 }}</span>
        <v-spacer></v-spacer>
        <v-btn size="x-small" variant="text" icon @click="duplicate">
          <v-icon>mdi-content-copy</v-icon>
          <v-tooltip activator="parent" location="top">Duplicate</v-tooltip>
        </v-btn>
        <v-btn size="x-small" variant="text" icon color="error" @click="remove" :disabled="isOnlyBlock">
          <v-icon>mdi-delete</v-icon>
          <v-tooltip activator="parent" location="top">Delete</v-tooltip>
        </v-btn>
      </div>
      <v-row dense>
        <v-col cols="4" sm="2">
          <v-text-field
            v-model.number="block.frequency"
            label="Freq (Hz)"
            type="number"
            min="0.1"
            max="1200"
            step="0.1"
            density="compact"
            hide-details
          ></v-text-field>
        </v-col>
        <v-col cols="4" sm="2">
          <v-text-field
            v-model.number="block.impulse"
            label="Impulse (µs)"
            type="number"
            min="20"
            max="400"
            density="compact"
            hide-details
          ></v-text-field>
        </v-col>
        <v-col cols="4" sm="2">
          <v-text-field
            v-model.number="block.cluster"
            label="Cluster"
            type="number"
            min="1"
            density="compact"
            hide-details
          ></v-text-field>
        </v-col>
        <v-col cols="4" sm="2">
          <v-text-field
            v-model.number="block.repeat"
            label="Repeat"
            type="number"
            min="1"
            density="compact"
            hide-details
          ></v-text-field>
        </v-col>
        <v-col cols="4" sm="2">
          <v-text-field
            v-model.number="block.interval"
            label="Interval (ms)"
            type="number"
            min="0"
            density="compact"
            hide-details
          ></v-text-field>
        </v-col>
        <v-col cols="4" sm="2" class="d-flex align-center">
          <v-chip size="small" variant="tonal">{{ durationText }}</v-chip>
        </v-col>
      </v-row>
    </v-sheet>
  `,
  setup(props) {
    const block = Vue.computed(() => {
      const sec = store.script.sections[props.sectionIndex];
      return sec ? sec.blocks[props.blockIndex] : null;
    });

    const isOnlyBlock = Vue.computed(() => {
      const sec = store.script.sections[props.sectionIndex];
      return sec ? sec.blocks.length <= 1 : true;
    });

    const durationText = Vue.computed(() => {
      if (!block.value) return "—";
      const b = block.value;
      const cycleDur = (1000 / (b.frequency || 100)) * (b.cluster || 1) + (b.interval || 0);
      const totalMs = cycleDur * (b.repeat || 1);
      if (totalMs < 1000) return `${Math.round(totalMs)}ms`;
      const s = totalMs / 1000;
      if (s < 60) return `${s.toFixed(1)}s`;
      return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
    });

    function duplicate() {
      const sec = store.script.sections[props.sectionIndex];
      if (sec) {
        const copy = { ...sec.blocks[props.blockIndex] };
        sec.blocks.splice(props.blockIndex + 1, 0, copy);
      }
    }

    function remove() {
      const sec = store.script.sections[props.sectionIndex];
      if (sec && sec.blocks.length > 1) {
        sec.blocks.splice(props.blockIndex, 1);
      }
    }

    return { block, isOnlyBlock, durationText, duplicate, remove };
  },
};
