# PDU-Only Mode

This document describes the PDU-only mode feature for Basic Station, which allows the LNS to receive raw LoRaWAN frames instead of parsed fields.

## Executive Summary

**Feature:** PDU-only mode sends raw uplink frames to the LNS without parsing into individual LoRaWAN fields.

**Configuration:** LNS sets `"pdu_only": true` in `router_config`

**Message Format:**
```json
{
  "msgtype": "updf",
  "pdu": "40AABBCCDD00010001A1B2C3D4E5F6",
  "DR": 0,
  "Freq": 902300000,
  "RefTime": 1234567890.123,
  "upinfo": { ... }
}
```

**Feature Flag:** Station advertises `pdu-only` in the `features` field of the `version` message.

## Table of Contents

- [Motivation](#motivation)
- [Configuration](#configuration)
- [Message Format](#message-format)
- [Implementation Details](#implementation-details)
- [Use Cases](#use-cases)
- [Backward Compatibility](#backward-compatibility)

## Motivation

By default, Basic Station parses uplink LoRaWAN frames and extracts individual fields:

- MHdr, DevAddr, FCtrl, FCnt, FOpts, FPort, FRMPayload, MIC (for data frames)
- MHdr, JoinEUI, DevEUI, DevNonce, MIC (for join requests)

This parsing provides convenience for simple LNS implementations but has limitations:

1. **LNS Flexibility:** Some LNS implementations prefer to do their own parsing
2. **Unknown Frame Types:** Station may not understand all frame types (e.g., proprietary extensions)
3. **Processing Overhead:** Parsing adds CPU overhead on constrained gateways
4. **Forward Compatibility:** New LoRaWAN versions may introduce frame formats the station doesn't recognize

PDU-only mode addresses these by forwarding the raw frame while preserving essential metadata.

## Configuration

### Router Config

The LNS enables PDU-only mode by including `pdu_only` in the `router_config` message:

```json
{
  "msgtype": "router_config",
  "region": "US915",
  "pdu_only": true,
  ...
}
```

### Feature Discovery

The station advertises support for PDU-only mode in the `version` message:

```json
{
  "msgtype": "version",
  "station": "2.0.6(linux/std)",
  "features": "rmtsh pdu-only",
  ...
}
```

The LNS should check for the `pdu-only` feature before enabling this mode.

## Message Format

### Standard Mode (pdu_only: false)

Data frames are parsed into individual fields:

```json
{
  "msgtype": "updf",
  "MHdr": 64,
  "DevAddr": -1430532899,
  "FCtrl": 0,
  "FCnt": 1,
  "FOpts": "",
  "FPort": 1,
  "FRMPayload": "A1B2C3D4E5F6",
  "MIC": -123456789,
  "DR": 0,
  "Freq": 902300000,
  "RefTime": 1234567890.123,
  "upinfo": {
    "rctx": 0,
    "xtime": 12345678901234,
    "gpstime": 1234567890000000,
    "fts": -1,
    "rssi": -50,
    "snr": 9.5,
    "rxtime": 1234567890.456
  }
}
```

### PDU-Only Mode (pdu_only: true)

The raw frame is sent without field parsing:

```json
{
  "msgtype": "updf",
  "pdu": "40AABBCCDD00010001A1B2C3D4E5F6AABBCCDD",
  "DR": 0,
  "Freq": 902300000,
  "RefTime": 1234567890.123,
  "upinfo": {
    "rctx": 0,
    "xtime": 12345678901234,
    "gpstime": 1234567890000000,
    "fts": -1,
    "rssi": -50,
    "snr": 9.5,
    "rxtime": 1234567890.456
  }
}
```

### Field Description

| Field | Type | Description |
|-------|------|-------------|
| `msgtype` | string | Always `"updf"` for uplink data frames |
| `pdu` | string | Raw frame as hexadecimal string |
| `DR` | integer | Datarate index |
| `Freq` | integer | Frequency in Hz |
| `RefTime` | number | Reference time (MuxTime + offset) |
| `upinfo` | object | Reception metadata |

### Upinfo Fields

| Field | Type | Description |
|-------|------|-------------|
| `rctx` | integer | Radio context for TX response |
| `xtime` | integer | Concentrator timestamp (µs) |
| `gpstime` | integer | GPS time if available |
| `fts` | integer | Fine timestamp (-1 if unavailable) |
| `rssi` | integer | Received signal strength (dBm) |
| `snr` | number | Signal-to-noise ratio (dB) |
| `rxtime` | number | Host UTC time at reception |

## Implementation Details

### Source Files

- `src/s2e.h` - Declares `s2e_pduOnly` global flag
- `src/s2e.c` - Implements flag, config parsing, and uplink handling
- `src/kwlist.txt` - Defines `pdu_only` keyword for JSON parsing
- `src-linux/sys_linux.c` - Advertises `pdu-only` feature

### Code Flow

1. **Startup:** Station sends `version` message with `pdu-only` in features
2. **Configuration:** LNS sends `router_config` with `pdu_only: true`
3. **Parsing:** Station sets `s2e_pduOnly = 1` and logs mode change
4. **Uplink:** When frame received:
   - If `s2e_pduOnly`: Add `pdu` field with hex-encoded frame
   - Otherwise: Call `s2e_parse_lora_frame()` to extract fields
5. **Metadata:** DR, Freq, RefTime, upinfo added regardless of mode

### Filter Behavior

In PDU-only mode:

- **No filtering** is applied (JoinEUI filter, NetID filter)
- **All frames** are forwarded, including malformed ones
- **LNS responsibility** to validate and filter frames

This differs from standard mode where invalid frames are dropped.

## Use Cases

### 1. LNS with Custom Parsing

LNS implementations that have their own optimized LoRaWAN parser can avoid double-parsing by requesting raw PDUs.

### 2. Protocol Development

When developing or testing new LoRaWAN features, PDU-only mode allows forwarding frames that the station doesn't understand.

### 3. Proprietary Extensions

Networks using proprietary frame types (FRMTYPE_PROP) can receive the complete frame for custom processing.

### 4. Debugging and Logging

Raw PDUs are useful for debugging frame-level issues and maintaining complete packet captures.

### 5. Constrained Gateways

On resource-limited gateways, skipping frame parsing reduces CPU usage.

## Backward Compatibility

- **Default behavior unchanged:** Without `pdu_only: true`, frames are parsed as before
- **Feature detection:** LNS can check for `pdu-only` in features before enabling
- **Old stations:** Will ignore unknown `pdu_only` field in router_config
- **Old LNS:** Will not send `pdu_only`, so station uses standard parsing

## Security Considerations

PDU-only mode forwards all received frames without validation. The LNS must:

1. Validate frame structure before processing
2. Apply appropriate filtering (NetID, JoinEUI, etc.)
3. Handle malformed frames gracefully

This is the same security model as packet forwarders that send raw frames.
