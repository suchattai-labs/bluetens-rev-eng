# Bluetens TENS Unit -- BLE Protocol Reverse Engineering Report

**APK**: Bluetens v7.0.59 (72 MB)  
**Architecture**: Cordova hybrid app (Java BLE plugin + JavaScript protocol logic)  
**Analysis date**: 2026-04-07  
**Source**: Decompiled with jadx (Java) and apktool (assets/resources)  
**Critical file**: `assets/www/build/main.js` (32,777 lines, webpack-bundled)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Device Identification](#2-device-identification)
3. [BLE GATT Service & Characteristic Table](#3-ble-gatt-service--characteristic-table)
4. [Connection Sequence](#4-connection-sequence)
5. [Transport Layer](#5-transport-layer)
6. [Command Protocol Specification](#6-command-protocol-specification)
7. [Response & Status Protocol](#7-response--status-protocol)
8. [Device Notification Protocol](#8-device-notification-protocol)
9. [File System & Script File Format](#9-file-system--script-file-format)
10. [File Upload (CAT) Protocol](#10-file-upload-cat-protocol)
11. [OTA Firmware Update Protocol](#11-ota-firmware-update-protocol)
12. [Security Analysis](#12-security-analysis)
13. [Raw Notes & Code References](#13-raw-notes--code-references)

---

## 1. Executive Summary

The Bluetens device uses a **text-based shell protocol over a BLE serial profile**, not a custom binary protocol. All communication flows through a single GATT characteristic (UUID FFE1 on service FFE0) using UTF-8 encoded text commands prefixed with `>`. Responses are line-delimited with `\r\n`. The protocol supports device control (intensity, programs), file management (upload, delete, list, MD5), OTA firmware updates, and device configuration.

The app is a Cordova/Ionic hybrid. The Java layer (`cordova-plugin-ble-central`) is a generic BLE bridge. **All protocol logic lives in the JavaScript layer** (`main.js`), making it straightforward to extract and reimplement.

Key findings:
- Simple text command/response protocol -- easy to reimplement
- Intensity range: 1-60 (integer steps)
- Script files use a compact tokenized format with hex-encoded parameters
- OTA uses 20-byte packets with CRC16 (polynomial 0x1021, seed 0)
- No encryption, authentication, or pairing enforcement on the BLE layer
- Write-without-response mode preferred for speed (27ms interval between writes)

---

## 2. Device Identification

### Device Variants

| Product | Class Name | BLE Advertising Names | Ad Name Regex |
|---------|------------|-----------------------|---------------|
| Bluetens Classic | `Bluetens` | `blt`, `bluetensx`, `bluetensq`, `bluetens`, `pkt` | `/(bluetens\|\.blt)/gi` |
| Bluetens Classic V2 | `Bluetens` | `pkt`, `bluetens2` | -- |
| Bluetens Sport | `Bluesport` | `bst` | `/(duo\|sport)/gi` |
| Bluetens Sport V2 | `Bluesport` | `duosport2` | -- |

Source: `main.js` lines 25267-25312.

### Manufacturer Advertising Data IDs

| ID | Hex | Purpose |
|----|-----|---------|
| `AD_MANUFACTORY_ID1` | `0xFFBC` | Primary manufacturer data |
| `AD_MANUFACTORY_ID2` | `0xFFBD` | Secondary |
| `AD_MANUFACTORY_ID3` | `0xFFBE` | Tertiary |

Source: `main.js` lines 6120-6144.

### Scan Filter

The app scans for devices advertising service UUID `FFE0`:
```javascript
this.Discover.Prepare({ ScanServices: ['FFE0'] })
```
Source: `main.js` line 21333.

---

## 3. BLE GATT Service & Characteristic Table

| Item | UUID | Notes |
|------|------|-------|
| **Service** | `0000FFE0-0000-1000-8000-00805f9b34fb` | Shell serial service |
| **Characteristic** | `0000FFE1-0000-1000-8000-00805f9b34fb` | Shell serial characteristic (read/write/notify) |
| **CCCD** | `00002902-0000-1000-8000-00805f9b34fb` | Client Characteristic Configuration Descriptor |

Short UUIDs are expanded using the standard Bluetooth base: `0000XXXX-0000-1000-8000-00805f9b34fb`.

The characteristic supports:
- **Read** (property bit 0x02)
- **Write** (property bit 0x08) -- used in "strict write" mode
- **WriteWithoutResponse** (property bit 0x04) -- preferred for speed
- **Notify** (property bit 0x10) -- for receiving device responses

---

## 4. Connection Sequence

```
Phone                                  Device
  |                                      |
  |--- BLE Scan (filter: FFE0) --------->|
  |<-- Advertising (name matches) -------|
  |                                      |
  |--- GATT Connect -------------------->|
  |<-- Connected ------------------------|
  |                                      |
  |--- Discover Services --------------->|
  |<-- Service FFE0, Char FFE1 ----------|
  |                                      |
  |--- Enable Notifications (CCCD) ----->|
  |<-- Notification Enabled -------------|
  |                                      |
  |--- Check WriteWithoutResponse ------>|  (from char properties)
  |                                      |
  |--- ">ver\r\n" ---------------------->|  Step 1: Version
  |<-- "v.X.Y.Z\r\n" -------------------|
  |                                      |
  |--- ">bat\r\n" ---------------------->|  Step 2: Battery
  |<-- "NNNN mv\r\n" -------------------|
  |                                      |
  |--- GetDefaultFile sequence --------->|  Step 3: Default file
  |<-- (file name) ----------------------|
  |                                      |
  |--- ">stat\r\n" -------------------->|  Step 4: Status
  |<-- "tick=X,str=X,dmd5=X,..." --------|
  |                                      |
  |            READY FOR USE             |
```

Source: `TShell.AfterConnected()`, `main.js` lines 8926-8938.

### Write Mode Selection

After connection, the app determines write mode:

1. If the characteristic does NOT support `WriteWithoutResponse` -> strict write
2. If `BLE_FORCE_STRICT_WRITE` is set -> strict write
3. After version check: if firmware version < 20000000 -> force strict write
4. Otherwise -> write-without-response (faster)

Source: `main.js` lines 8928-8933, 8862.

---

## 5. Transport Layer

### Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `MTU` | 20 bytes | Maximum BLE write size per packet |
| `MIN_WRITE_INTERVAL` | 27 ms | Minimum delay between write-without-response packets |
| `BLE_CONNECTION_TIMEOUT` | 240,000 ms | Connection timeout (4 minutes) |
| `REQUEST_TIMEOUT` | 120,000 ms | Command timeout (2 minutes) |
| `NOTIFICATION_IN_BUFFER` | 4,096 bytes | Incoming notification buffer |
| `LINE_BREAK` | `\r\n` | Line delimiter |
| `DEFAULT_CONNECTION_TIMEOUT` | 1,800 ms | Default connection setup timeout |

Source: `main.js` lines 9387-9399, 15225-15227.

### Framing

- Commands and responses are **UTF-8 text**, line-delimited with `\r\n`
- Commands are prefixed with `>` (0x3E)
- Large payloads are split into MTU-sized (20 byte) chunks
- In write-without-response mode, chunks are sent with a 27ms delay between them (targeting ~5926 bps effective throughput)
- In strict write mode, each chunk waits for a write acknowledgment before sending the next

### Write Flow

```
TShell.Execute(command)
  -> TCharacteristicStream.Write(data)
    -> if data.length > MTU: split into 20-byte chunks
    -> for each chunk:
       if StrictWrite:
         BLE WriteChar (write with response, wait for ack)
       else:
         BLE WriteCharNoResponse (fire and forget)
         wait MIN_WRITE_INTERVAL (27ms)
```

Source: `main.js` lines 10377-10396.

---

## 6. Command Protocol Specification

All commands are UTF-8 strings prefixed with `>`, terminated with `\r\n`.

### Command Table

| Command | Syntax | Response | Description |
|---------|--------|----------|-------------|
| **Version** | `>ver` | `v.X.Y.Z` or `ver=v.X.Y.Z` | Get firmware version |
| **Battery** | `>bat` | `NNNN mv` | Get battery voltage in millivolts |
| **Status** | `>stat` | `tick=X,str=X,dmd5=X,md5=X,lmd5=X` | Get device status |
| **Set Intensity** | `>str <1-60>` | `str=N` or just `N` | Set stimulation intensity |
| **Start Script** | `>ssta <filename>` | Status line (numeric:text) | Start running a script file |
| **Stop Output** | `>osto` | Status line | Stop current stimulation |
| **Set Default File** | `>sdef <filename>` | `sdef=<filename>` | Set the default script file |
| **File MD5** | `>md5 <filename>` | MD5 hex string | Get MD5 hash of a file |
| **Cat (Upload)** | `>cat <filename> -l=<byteLength>` | (binary data follows) | Upload file content |
| **Remove File** | `>rm <filename>` | Status line | Delete a file |
| **List Files** | `>ls` | File listing | List files on device |
| **Format FS (old)** | `>fmt BBFS` | Status line | Format filesystem (firmware < v3.x) |
| **Format FS (new)** | `>format . ultrafs` | Status line | Format filesystem (firmware >= v3.x) |
| **Set BT Name** | `>btnm <name>` | `AT+NAME<name>` or `btnm=<name>` | Set Bluetooth device name |
| **Shutdown** | `>shdn` | (device shuts down) | Power off device |
| **Reset** | `>rst` | (device resets) | Reboot device |
| **OTA** | `>ota -s=<size> -c=<crc>` | OTA protocol sequence | Initiate firmware update |

### Command Details

#### `>ver` -- Get Version

Request: `>ver\r\n`  
Response: `v.X.Y.Z\r\n` (e.g., `v.2.0.27`)

The version string is parsed into a numeric format:
```
numeric_version = (X * 1000 + Y) * 10000 + Z
Example: v.2.0.27 -> (2*1000 + 0)*10000 + 27 = 20000027
```

Firmware versions below 20000000 (i.e., v.1.x.x) force strict write mode.

Source: `main.js` lines 8849-8866.

#### `>bat` -- Get Battery

Request: `>bat\r\n`  
Response: `NNNN mv\r\n` (e.g., `4200 mv`)

Special case: if response is `32769:...`, battery is treated as 5000mv.

Battery level mapping (4 levels):

**V1 devices** (Classic original):
| Voltage (mv) | Level |
|---------------|-------|
| <= 3800 | 1 (low) |
| <= 4400 | 2 |
| <= 4700 | 3 |
| <= 10000 | 4 (full) |

**V2 devices**:
| Raw value | Level |
|-----------|-------|
| <= 1025 | 1 (low) |
| <= 2050 | 2 |
| <= 3075 | 3 |
| <= 4100 | 4 (full) |

Source: `main.js` lines 8770-8794, 8829-8847.

#### `>stat` -- Get Status

Request: `>stat\r\n`  
Response: `tick=X,str=X,dmd5=X,md5=X,lmd5=X\r\n`

Fields:
| Field | Description |
|-------|-------------|
| `tick` | Elapsed seconds since script start |
| `str` | Current intensity (1-60) |
| `dmd5` | MD5 hash of default file |
| `md5` / `lmd5` | MD5 hash of last/current file |

Source: `main.js` lines 8798-8827.

#### `>str <value>` -- Set Intensity

Request: `>str 25\r\n`  
Response: `str=25\r\n` or just `25\r\n`

Value range: 1-60 (integer). Values outside this range are silently rejected by the app before sending.

Source: `main.js` lines 8646-8684.

#### `>ssta <filename>` -- Start Script

Request: `>ssta MyScript\r\n`  
Response: A status return value line (format: `N:text`)

After successful start, intensity is set to 1 and the tick timer begins.

Source: `main.js` lines 8623-8637.

#### `>osto` -- Stop Output

Request: `>osto\r\n`  
Response: Status return value line

Resets intensity to 0 and clears tick counters.

Source: `main.js` lines 8638-8645.

### Response Format: Status Return Value

Many commands return a "status return value" line in the format:
```
<numeric_status>:<message>
```

The app checks `IsStatusRetVal(Line)` which verifies the line contains `:` and the part before `:` is a valid integer.

- Status `0` = success (in OTA context)
- Status `3` = end of cat file upload
- Status with bit 0x8000 set = error (in OTA context)

Source: `main.js` lines 8879-8886.

---

## 7. Response & Status Protocol

### General Response Handling

The device sends responses as text lines terminated with `\r\n`. The shell processes incoming data from BLE notifications, buffering bytes until a complete line is received.

Lines starting with `NOTIFY ` are routed to the device notification handler (see section 8). All other lines are passed to the active command's response handler.

### Command Execution Model

Commands use an `Execute()` pattern:
```
Execute(command, timeout, matchFunction) -> Promise<Line>
```

The `matchFunction` is called for each received line until it returns `true`, at which point the matching line is returned as the command's result. If no match within `timeout` ms, the command fails.

Source: `main.js` lines 8944-8949 (OnRead), various Execute calls throughout TShell.

---

## 8. Device Notification Protocol

The device can send unsolicited notifications at any time. These are lines prefixed with `NOTIFY `:

```
NOTIFY <event> [params]
```

### Notification Events

| Event String | Enum Value | Action | Description |
|-------------|------------|--------|-------------|
| `disconnect` | 1 | Detach | Device disconnecting |
| `shutdown` | 0 | Detach | Device shutting down |
| `low` | 7 | Detach | Low battery |
| `error` | 6 | Detach | Hardware error |
| `noload` | 2 | (none) | No load detected (electrodes not connected) |
| `stop` | 3 | (none) | Stimulation stopped |
| `strength <N>` | 4 | Update intensity | Intensity changed (e.g., by button press) |
| `insufficient space` | 8 | (none) | File system full |

Notes:
- Events `disconnect`, `shutdown`, `low`, and `error` all cause the shell to detach (close the connection)
- `noload` and `stop` are informational only
- `strength` includes the new intensity value as a parameter

Source: `main.js` lines 8888-8922.

### TShellNotify Enum

```
Shutdown       = 0
Disconnected   = 1
NoLoad         = 2
Stopped        = 3
Intensity      = 4
Battery        = 5
HardwareError  = 6
LowBattery     = 7
FullSpace      = 8
```

Source: `main.js` lines 8550-8561.

---

## 9. File System & Script File Format

### File System Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `FILE_CLEAR_EXCLUDES` | `['DefaultFile', 'BLE_Name']` | Files excluded from bulk clear |
| `FILE_CLEAR_SIZE_LESS_THAN` | 2096 bytes | Only clear files smaller than this |
| `FILE_SYSTEM_FORMAT_SIZE` | 61,440 bytes (60 KB) | Total filesystem capacity |

Source: `main.js` lines 15411-15413.

### Script File Token Format

Script files are stored as compact tokenized text. Each token is a single ASCII character (the token type) followed by a value string. Values are encoded in the current digit base (default hex, base 16).

#### Token Types

| Token | ASCII Code | Char | Value Format | Description |
|-------|------------|------|-------------|-------------|
| `Version` | 86 | `V` | Decimal integer | File format version (always base 10) |
| `DigitBase` | 68 | `D` | Decimal integer | Digit base: 10 or 16 (always base 10) |
| `SectionStart` | 123 | `{` | (none) | Start of a section |
| `SectionEnd` | 125 | `}` | (none) | End of a section |
| `Block` | 124 | `\|` | (none) | Block separator |
| `LoopStart` | 60 | `<` | (none) | Start of loop definition |
| `LoopEnd` | 62 | `>` | (none) | End of loop definition |
| `LoopSection` | 83 | `S` | Decimal integer | Section index to loop (1-based, always base 10) |
| `Repeat` | 82 | `R` | In digit base | Repeat count |
| `Interval` | 73 | `I` | In digit base | Interval in milliseconds |
| `Freq` | 70 | `F` | In digit base | Frequency in Hz (integer) |
| `FreqT` | 84 | `T` | In digit base | Frequency * 10 (for decimal freqs, e.g., 5.5 Hz = 55) |
| `Impulse` | 80 | `P` | In digit base | Impulse width in microseconds |
| `Cluster` | 67 | `C` | In digit base | Cluster count (pulses per burst) |

Source: `main.js` lines 8070-8087.

#### File Structure

```
V<version>D<digitBase>{<section1>}{<section2>}...<S1S2...>
```

A file contains:
1. **Version header**: `V1` (version 1, always decimal)
2. **Digit base**: `D16` (hex) or `D10` (decimal)
3. **Sections**: Each wrapped in `{...}`
4. **Loop definition** (optional): `<S1S2>` references sections by 1-based index

Each section contains:
- Optional `R<repeat>` (default 1)
- Optional `I<interval>` (default 0)
- One or more blocks separated by `|`

Each block contains:
- `R<repeat>` -- repetition count
- `I<interval>` -- pause between repetitions (ms)
- `P<impulse>` -- impulse/pulse width (microseconds, range 20-400)
- `F<freq>` or `T<freqT>` -- frequency (Hz or Hz*10)
- `C<cluster>` -- cluster/burst count

#### Defaults

| Parameter | Default Value |
|-----------|---------------|
| Freq | 54 Hz |
| Impulse | 100 us |
| Cluster | 1 |
| Repeat | 1 |
| Interval | 0 ms |

#### Limits

| Parameter | Min | Max |
|-----------|-----|-----|
| Frequency | >0 | 1200 Hz |
| Impulse | 20 us | 400 us |

Source: `main.js` lines 7482-7488.

#### Delta Encoding

When serializing blocks, only parameters that differ from the previous block are emitted. The first block in a section always writes all parameters. This provides compression for scripts with similar consecutive blocks.

Source: `main.js` lines 7812-7843.

#### Example Script File

A simple 100Hz, 200us pulse width program running for 10 repetitions:
```
V1D16{|R1P64F64C1}
```
Breakdown:
- `V1` = version 1
- `D16` = hex digit base
- `{` = section start
- `|` = block separator
- `R1` = repeat 1 (0x1)
- `P64` = impulse 100us (0x64 = 100)
- `F64` = frequency 100Hz (0x64 = 100)
- `C1` = cluster 1
- `}` = section end

#### Time Estimation

Block duration (ms): `(1000 / Freq * Cluster + Interval) * Repeat`  
Section duration: `(sum_of_block_durations + section_interval) * section_repeat`  
File duration: `sum_of_section_durations + sum_of_looped_section_durations`

Source: `main.js` lines 7765-7772 (TBlock.TimeEst), 7697-7699 (TSection.TimeEst).

---

## 10. File Upload (CAT) Protocol

The `>cat` command uploads file content to the device.

### Sequence

```
Phone                                  Device
  |                                      |
  |--- ">md5 <filename>\r\n" ----------->|  1. Check if file exists
  |<-- "<md5_hash>\r\n" -----------------|
  |                                      |
  |    [If MD5 matches, skip upload]     |
  |                                      |
  |--- ">cat <fn> -l=<len>\r\n" -------->|  2. Send cat command with byte length
  |<-- (ready) --------------------------|
  |                                      |
  |--- <binary file content> ----------->|  3. Stream file bytes (MTU-chunked)
  |    (split into 20-byte chunks)       |
  |                                      |
  |<-- "3: end of cat\r\n" -------------|  4. Upload complete
  |                                      |
```

Key details:
- Before uploading, the app checks the file's MD5 on the device. If it matches, the upload is skipped entirely (ECatAbort).
- The file content is sent as raw bytes after the `>cat` command, split into 20-byte MTU chunks.
- Upload completion is signaled by the device responding with `3: end of cat`.

Source: `main.js` lines 15534-15590.

---

## 11. OTA Firmware Update Protocol

### Overview

OTA updates send firmware binary data in 20-byte packets with per-packet CRC16 validation and an overall firmware CRC16.

### Constants

| Constant | Value |
|----------|-------|
| `OTA_SPLIT_PACKET_SIZE` | 16 bytes |
| `OTA_PACKET_SIZE` | 20 bytes (16 data + 4 header) |
| CRC16 Polynomial | `0x1021` (CRC-CCITT) |
| CRC16 Seed | `0` |

### OTA Packet Format (20 bytes)

```
Offset  Size    Type      Description
0       2       uint16    Byte offset in firmware (little-endian)
2       2       uint16    CRC16 of this packet's 16-byte data payload
4       16      uint8[]   Firmware data (zero-padded if last packet is short)
```

### OTA Sequence

```
Phone                                  Device
  |                                      |
  |  [Split firmware into 16-byte chunks]|
  |  [Calculate per-packet CRC16]        |
  |  [Calculate overall firmware CRC16]  |
  |                                      |
  |--- ">ota -s=<size> -c=<crc>\r\n" -->|  1. Initiate OTA
  |<-- "0:<msg>\r\n" -------------------|  2. Device ready (status 0)
  |                                      |
  |--- [20-byte packet 0] ------------->|  3. Send packets sequentially
  |--- [20-byte packet 1] ------------->|
  |--- [20-byte packet N] ------------->|
  |    ...                               |
  |                                      |
  |<-- "0:<msg>\r\n" -------------------|  4. OTA complete (status 0)
  |                                      |
```

### Error Handling

- Response `crc error` = CRC validation failed, OTA aborted
- Response with status bit `0x8000` set = OTA failure
- During OTA, strict write mode is forced (write-with-response)

### CRC16 Algorithm (CRC-CCITT)

```python
def crc16(data: bytes, seed: int = 0) -> int:
    crc = seed
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
```

Source: `main.js` lines 15596-15717 (OTA), 15752-15842 (CRC16).

---

## 12. Security Analysis

### Findings

1. **No BLE pairing/bonding required**: The device accepts connections from any BLE client without authentication.

2. **No encryption on BLE layer**: Commands and responses are sent in plaintext over the BLE characteristic. No encryption is applied at the application level.

3. **No command authentication**: There is no token, challenge-response, or shared secret mechanism. Any connected client can send any command.

4. **OTA has no firmware signing**: The OTA protocol uses CRC16 for data integrity, but there is no cryptographic signature verification. Any firmware image with a valid CRC16 could potentially be flashed.

5. **No replay protection**: Commands can be captured and replayed.

6. **Physical proximity required**: BLE range provides some inherent protection (typical ~10m range, though extendable with antennas).

### Risk Assessment

The lack of authentication means that any BLE-capable device within range could:
- Connect to the Bluetens unit
- Control stimulation intensity (up to level 60)
- Upload arbitrary script files
- Flash arbitrary firmware (if OTA format is correct)
- Shut down or reset the device

This is somewhat mitigated by BLE's short range and the fact that the device likely only accepts one connection at a time. However, for a medical/therapeutic device, the absence of any authentication is notable.

---

## 13. Raw Notes & Code References

### App Architecture Stack

```
Ionic/Angular UI
  -> TBluetensPeripheral (product-specific logic)
    -> TShell (shell command protocol)
      -> TAbstractShell / BLE TShell (command queue, request/response)
        -> TGapConnection (BLE GAP connection management)
          -> TCharacteristicStream (byte-level BLE read/write)
            -> cordova-plugin-ble-central (Cordova BLE plugin)
              -> Android BluetoothGatt (native Android BLE)
```

### Key Source Locations in main.js

| Component | Lines | Description |
|-----------|-------|-------------|
| BLE constants | 9387-9399, 15225-15227 | MTU, timeouts, UUIDs |
| TShellNotify enum | 8550-8561 | Notification types |
| TShell class | 8562-8971 | All shell commands |
| TShell.AfterConnected | 8926-8938 | Connection sequence |
| TShell._DeviceNotification | 8888-8922 | Notification parsing |
| TShell.VersionRequest | 8849-8866 | Version parsing |
| TShell.BatteryRequest | 8829-8847 | Battery parsing |
| TShell.StatusRequest | 8798-8827 | Status parsing |
| TShell.SetIntensity | 8646-8684 | Intensity control |
| TTokenType enum | 8070-8087 | Script file token types |
| TToken parser | 8089-8219 | Token parser |
| TFile | 7492-7672 | Script file class |
| TSection | 7674-7735 | Script section |
| TBlock | 7737-7849 | Script block |
| File constants | 7482-7490 | MAX_FREQ, MAX_IMPULSE, defaults |
| TCatRequest | 15534-15590 | File upload protocol |
| TOTARequest | 15622-15717 | OTA update protocol |
| THashCrc16 | 15752-15842 | CRC16 implementation |
| TCharacteristicStream | 10377-10396 | BLE write chunking |
| Device identification | 25267-25312 | Product names, ad names |
| Manufacturer data | 6120-6144 | Advertising data IDs |
| File system constants | 15411-15413 | FS limits |

### Key Source Locations in Java (Generic BLE Plugin)

| File | Description |
|------|-------------|
| `BLECentralPlugin.java` | Cordova plugin entry, routes JS calls to Android BLE |
| `Peripheral.java` | GATT connection wrapper, callback handling, command queue |
| `Helper.java` | GATT property/permission decoder |
| `UUIDHelper.java` | Short-to-full UUID expansion |

### Connection Timeout Behavior

When the connection timeout fires, the app queues a battery request (`>bat`) as a keepalive. Multiple timeouts are queued and processed serially with a 3-second delay between them.

Source: `main.js` lines 8951-8966.

### Version 2 Detection

The app distinguishes V1 and V2 hardware via `App.IsVersion2`, which affects battery level interpretation. V2 devices use a different voltage scale (0-4100 range vs 0-10000 mV range).

### Filesystem Format Detection

The format command changes based on firmware version:
- Version >= 30000000 (v.3.x.x): `>format . ultrafs`
- Version < 30000000: `>fmt BBFS`

Source: `main.js` lines 8720-8729.
