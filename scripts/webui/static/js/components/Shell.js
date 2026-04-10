/**
 * Shell view — raw BLE command terminal.
 */

const ShellView = {
  template: `
    <div>
      <v-card>
        <v-card-title>BLE Shell</v-card-title>
        <v-card-subtitle>
          Commands: ver, bat, stat, str, ssta, osto, ls, cat, rm, md5, sdef, btnm, shdn, rst, fmt
        </v-card-subtitle>
        <v-card-text>
          <!-- Output area -->
          <div class="shell-output mb-4" ref="outputEl">
            <div v-for="(entry, i) in store.shellHistory" :key="i">
              <span :class="entry.type === 'tx' ? 'cmd-tx' : 'cmd-rx'">
                {{ entry.type === 'tx' ? '> ' : '< ' }}{{ entry.text }}
              </span>
            </div>
            <div v-if="!store.shellHistory.length" class="text-medium-emphasis">
              Type a command below and press Enter.
            </div>
          </div>

          <!-- Input -->
          <v-row>
            <v-col>
              <v-text-field
                v-model="command"
                label="Command"
                density="compact"
                hide-details
                :disabled="!store.isConnected"
                @keyup.enter="send"
                autofocus
              ></v-text-field>
            </v-col>
            <v-col cols="auto">
              <v-btn color="primary" @click="send" :disabled="!store.isConnected || !command">
                Send
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </div>
  `,
  setup() {
    const command = Vue.ref("");
    const outputEl = Vue.ref(null);

    async function send() {
      if (!command.value.trim()) return;
      const cmd = command.value.trim();
      store.shellHistory.push({ type: "tx", text: cmd, ts: new Date().toISOString() });
      command.value = "";
      try {
        await api.sendRaw(cmd);
      } catch (e) {
        store.shellHistory.push({ type: "rx", text: `Error: ${e.message}`, ts: new Date().toISOString() });
      }
      // Auto-scroll
      Vue.nextTick(() => {
        if (outputEl.value) outputEl.value.scrollTop = outputEl.value.scrollHeight;
      });
    }

    return { store, command, outputEl, send };
  },
};
