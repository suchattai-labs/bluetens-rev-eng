/**
 * Timeline widget — horizontal visualization of script sections.
 */

const TimelineWidget = {
  template: `
    <div class="timeline-container" v-if="store.script.sections.length">
      <div
        v-for="(sec, i) in store.script.sections"
        :key="i"
        class="timeline-section"
        :class="{ selected: store.selectedSection === i }"
        :style="sectionStyle(sec, i)"
        @click="store.selectedSection = i"
      >
        <div class="text-caption font-weight-bold">S{{ i + 1 }}</div>
        <div class="text-caption">{{ sectionSummary(sec) }}</div>
        <div class="text-caption" v-if="isLoop(i)">🔁</div>
      </div>
    </div>
    <div v-else class="text-medium-emphasis pa-4 text-center">
      No sections yet. Click "Add Section" to start building.
    </div>
  `,
  setup() {
    const sectionColors = [
      "#1565C0", "#2E7D32", "#E65100", "#6A1B9A",
      "#00838F", "#AD1457", "#F9A825", "#4527A0",
    ];

    function sectionStyle(sec, i) {
      const color = sectionColors[i % sectionColors.length];
      return {
        backgroundColor: color,
        flexGrow: Math.max(1, (sec.blocks || []).length),
      };
    }

    function sectionSummary(sec) {
      const blocks = sec.blocks || [];
      if (!blocks.length) return "empty";
      const b = blocks[0];
      let s = `${b.frequency}Hz`;
      if (blocks.length > 1) s += ` +${blocks.length - 1}`;
      if (sec.repeat > 1) s += ` ×${sec.repeat}`;
      return s;
    }

    function isLoop(i) {
      return store.script.loopIndices.includes(i);
    }

    return { store, sectionStyle, sectionSummary, isLoop };
  },
};
