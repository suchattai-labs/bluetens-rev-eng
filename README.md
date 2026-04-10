# Bluetens BLE Protocol Reverse Engineering

Reverse engineering the Bluetooth Low Energy (BLE) protocol used by Bluetens TENS/EMS units, based on static analysis of the official Android app (Bluetens v7.0.59). Includes full protocol documentation, a Python BLE control library, and a web-based control interface.

---

**IMPORTANT: Please read [DISCLAIMER.md](DISCLAIMER.md) before using anything in this repository. This is not a medical project. Electrical stimulation devices can cause serious injury or death if misused. Use at your own risk.**

---

## Overview

The Bluetens app is a Cordova/Ionic hybrid. The Java layer is a generic BLE bridge (`cordova-plugin-ble-central`), and all protocol logic lives in a single webpack-bundled JavaScript file (`main.js`, ~33K lines). The protocol itself is a text-based shell interface over a BLE serial profile -- UTF-8 commands prefixed with `>`, responses delimited with `\r\n`, all through a single GATT characteristic (service `FFE0`, characteristic `FFE1`).

Key findings from the analysis:

- Simple text command/response protocol, straightforward to reimplement
- Intensity range: 1-60 (integer steps)
- Script files use a compact tokenized format with hex-encoded parameters
- OTA firmware updates use 20-byte packets with CRC16-CCITT
- No encryption, authentication, or pairing enforcement on the BLE layer
- Write-without-response mode preferred (27ms interval, ~5.9 kbps effective)

## Features

- **Full protocol documentation** -- every command, response format, notification type, file format token, and OTA packet structure
- **Python BLE control library** (`bleak`-based) -- scan, connect, send commands, upload scripts, interactive shell
- **Script file builder** -- programmatically create stimulation scripts with the device's tokenized file format
- **Pattern generator** -- pre-built generators for frequency sweeps, impulse sweeps, burst mode, alternating patterns, and custom parameter functions
- **Web UI** -- FastAPI + Vue 3/Vuetify browser interface with real-time WebSocket updates, visual script builder, 10 stimulation presets, device file management, raw shell access, and BLE event log

## Device Compatibility

| Device | BLE Names | Status |
|--------|-----------|--------|
| Bluetens Classic | `blt`, `bluetensx`, `bluetensq`, `bluetens`, `pkt` | Documented |
| Bluetens Classic V2 | `pkt`, `bluetens2` | Documented |
| Bluetens Sport | `bst` | Documented |
| Bluetens Sport V2 | `duosport2` | Documented |

All variants share the same protocol and BLE service (`FFE0`). V1 and V2 hardware differ only in battery voltage interpretation and filesystem format command.

## Project Structure

```
tens-re/
  apks/               # Original APK files (git-ignored)
  decompiled/          # Decompiled APK output from jadx and apktool (git-ignored)
  docs/                # Protocol documentation
  notes/               # Reverse engineering notes and detailed protocol report
  patches/             # Patches
  scripts/
    bluetens_control.py    # BLE control library and CLI
    webui/                 # FastAPI + Vue/Vuetify web UI
      main.py              #   FastAPI app setup, middleware, routers
      device_manager.py    #   WebSocket-aware BLE device manager
      ws.py                #   WebSocket connection manager
      routers/
        device.py          #   Device scan/connect/control endpoints
        files.py           #   Device filesystem management endpoints
        scripts.py         #   Script building, presets, upload endpoints
      static/
        index.html         #   SPA entry point
        css/app.css        #   Application styles
        js/
          app.js           #   Vue app setup and component registration
          store.js         #   Reactive state store
          api.js           #   REST API client
          ws.js            #   WebSocket client
          components/      #   Vue components (Dashboard, Builder, Shell, etc.)
  requirements.txt     # Python dependencies
  LICENSE              # GPL-3.0
  DISCLAIMER.md        # Safety and liability disclaimer
  README.md            # This file
```

## Setup

### Requirements

- Python 3.10+
- A Bluetooth Low Energy adapter
- Linux, macOS, or Windows (any platform supported by `bleak`)

### Installation

```bash
git clone https://github.com/suchattai-labs/tens-re.git
cd tens-re
pip install -r requirements.txt
```

The only runtime dependency is `bleak` (>= 0.21) for BLE communication. The web UI uses FastAPI with uvicorn, which are installed as transitive dependencies.

## Usage

### CLI Control Script

Scan for nearby Bluetens devices:

```bash
python scripts/bluetens_control.py scan
```

Connect to a device and display info (firmware version, battery, status):

```bash
python scripts/bluetens_control.py connect AA:BB:CC:DD:EE:FF
```

Open an interactive shell for sending raw commands:

```bash
python scripts/bluetens_control.py shell AA:BB:CC:DD:EE:FF
```

Control intensity and scripts:

```bash
python scripts/bluetens_control.py intensity AA:BB:CC:DD:EE:FF 20
python scripts/bluetens_control.py start AA:BB:CC:DD:EE:FF MyScript
python scripts/bluetens_control.py stop AA:BB:CC:DD:EE:FF
```

Generate and upload pre-built stimulation patterns:

```bash
# Generate a frequency sweep script and save to file
python scripts/bluetens_control.py generate freq-sweep --start 2 --end 150 --duration 60 -o sweep.txt

# Generate a burst pattern and upload directly to device
python scripts/bluetens_control.py generate burst --freq 80 --on 5 --off 3 --bursts 10 \
    --upload AA:BB:CC:DD:EE:FF --start-after
```

Available patterns: `freq-sweep`, `impulse-sweep`, `alternating`, `burst`.

Add `-v` for debug logging with full BLE traffic.

### Web UI

Start the web server:

```bash
python -m scripts.webui
```

Open `http://localhost:8000` in a browser. The interface provides:

- **Dashboard** -- scan for devices, connect, monitor battery/intensity/status in real time, control intensity with a slider, start/stop stimulation
- **Builder** -- visual script editor with section and block management, or load from 10 built-in presets (frequency sweep, burst, EMS strength training, pain gate TENS, endorphin release, anti-habituation, and more); preview raw token output, upload to device
- **Shell** -- send raw shell commands and see responses, useful for protocol exploration
- **Files** -- list, delete, and manage files on the device filesystem; set default file, format filesystem
- **BLE Log** -- real-time stream of all BLE events and device notifications via WebSocket

## Protocol Overview

All communication happens over a single BLE characteristic (`FFE1` on service `FFE0`). Commands are UTF-8 text prefixed with `>` and terminated with `\r\n`.

### Core Commands

| Command | Description |
|---------|-------------|
| `>ver` | Get firmware version |
| `>bat` | Get battery voltage (millivolts) |
| `>stat` | Get device status (tick, intensity, file MD5s) |
| `>str <1-60>` | Set stimulation intensity |
| `>ssta <file>` | Start a script file |
| `>osto` | Stop stimulation |
| `>ls` | List files on device |
| `>cat <file> -l=<len>` | Upload file content |
| `>rm <file>` | Delete a file |
| `>md5 <file>` | Get file MD5 hash |
| `>sdef <file>` | Set default script file |
| `>btnm <name>` | Set Bluetooth name |
| `>shdn` | Shut down device |
| `>rst` | Reboot device |
| `>ota -s=<size> -c=<crc>` | Initiate firmware update |

### Script File Format

Scripts use a compact tokenized text format. Tokens are single ASCII characters followed by values encoded in the specified digit base (hex by default). Example:

```
V1D16{|R1P64F64C1}
```

This defines version 1, hex encoding, one section with one block: repeat 1, pulse width 100us (0x64), frequency 100Hz (0x64), cluster 1.

For the complete protocol specification including connection sequence, transport layer, notification protocol, file upload protocol, OTA update protocol, and security analysis, see [`notes/protocol-report.md`](notes/protocol-report.md).

## Security Notes

The BLE protocol has no encryption, authentication, or pairing enforcement. Any BLE client within radio range can connect and send commands, including controlling stimulation intensity and flashing firmware. See section 12 of the protocol report for the full security analysis.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).

## Disclaimer

**This is not a medical project.** See [DISCLAIMER.md](DISCLAIMER.md) for full safety warnings, hazard information, and liability terms. Electrical stimulation devices can cause serious injury. Use this software entirely at your own risk.
