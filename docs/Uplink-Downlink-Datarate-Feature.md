# Uplink/Downlink Datarate Feature (updn-dr)

This document describes the separate uplink/downlink datarate support introduced for LoRaWAN Regional Parameters RP002-1.0.5.

## Executive Summary

**Problem:** Prior to RP002-1.0.5, all regions used a single `DRs` array for both uplink and downlink. US915 and AU915 in RP002-1.0.5 now define different datarate tables for uplink vs downlink.

**Solution:** New `DRs_up` and `DRs_dn` fields in `router_config` for separate uplink/downlink datarate definitions.

**Feature Flag:** `updn-dr` - Indicates station supports separate uplink/downlink datarate tables.

**New Protocol Fields:**
- `DRs_up` - Uplink datarate definitions (16 entries)
- `DRs_dn` - Downlink datarate definitions (16 entries)

**Backward Compatible:** Legacy `DRs` field continues to work for symmetric regions.

## Table of Contents

- [Background](#background)
- [Protocol Changes](#protocol-changes)
- [Regional Configurations](#regional-configurations)
- [Implementation Details](#implementation-details)
- [Backward Compatibility](#backward-compatibility)
- [Feature Detection](#feature-detection)

## Background

### RP002-1.0.5 Changes

LoRaWAN Regional Parameters version 1.0.5 introduced:

1. **Asymmetric Datarates**: US915 and AU915 now have different DR definitions for uplink vs downlink
2. **SF5/SF6 Support**: New spreading factors at higher DR indices
3. **Extended DR Range**: DR7/DR8 for uplink, DR0/DR14 for downlink in US915

### Why Separate Tables?

In US915/AU915:
- **Uplink**: 125kHz channels use SF10-SF5 (DR0-DR4, DR7-DR8)
- **Downlink**: 500kHz channels use SF12-SF6 (DR8-DR14, DR0)

The same DR index maps to different modulation parameters depending on direction.

### Affected Regions

| Region | Datarate Type | Notes |
|--------|---------------|-------|
| US915 | Asymmetric | Different uplink/downlink tables |
| AU915 | Asymmetric | Different uplink/downlink tables |
| EU868 | Symmetric | Same table, but SF5/SF6 added at DR12/DR13 |
| AS923 | Symmetric | No changes |
| Other | Symmetric | No changes |

## Protocol Changes

### New Fields in `router_config`

| Field | Type | Description |
|-------|------|-------------|
| `DRs_up` | Array[16] | Uplink datarate definitions |
| `DRs_dn` | Array[16] | Downlink datarate definitions |

### DR Entry Format

Each DR entry is a 3-element array: `[SF, BW, dnonly]`

| Element | Value | Meaning |
|---------|-------|---------|
| SF | 5-12 | Spreading factor |
| SF | 0 | FSK modulation |
| SF | -1 | Reserved/Undefined (RFU) |
| SF | -2 | LR-FHSS (not supported) |
| BW | 125/250/500 | Bandwidth in kHz |
| dnonly | 0/1 | 1 = downlink only (legacy, ignored with DRs_up/DRs_dn) |

### Field Precedence

| Configuration | Behavior |
|--------------|----------|
| Only `DRs` | Symmetric datarates (legacy) |
| `DRs_up` and `DRs_dn` | Asymmetric datarates |
| All three | `DRs_up`/`DRs_dn` take precedence |

**Important:** When using asymmetric DRs, both `DRs_up` AND `DRs_dn` must be provided.

## Regional Configurations

### US915 RP002-1.0.5

**Uplink Datarates (`DRs_up`):**

| DR | Modulation | Bit Rate | Notes |
|----|------------|----------|-------|
| 0 | SF10/125kHz | 980 bps | |
| 1 | SF9/125kHz | 1760 bps | |
| 2 | SF8/125kHz | 3125 bps | |
| 3 | SF7/125kHz | 5470 bps | |
| 4 | SF8/500kHz | 12500 bps | |
| 5-6 | LR-FHSS | - | Not supported |
| 7 | SF6/125kHz | 9375 bps | **New in RP002-1.0.5** |
| 8 | SF5/125kHz | 15625 bps | **New in RP002-1.0.5** |
| 9-15 | RFU | - | |

**Downlink Datarates (`DRs_dn`):**

| DR | Modulation | Bit Rate | Notes |
|----|------------|----------|-------|
| 0 | SF5/500kHz | 62500 bps | **New in RP002-1.0.5** |
| 1-7 | RFU | - | |
| 8 | SF12/500kHz | 980 bps | |
| 9 | SF11/500kHz | 1760 bps | |
| 10 | SF10/500kHz | 3900 bps | |
| 11 | SF9/500kHz | 7000 bps | |
| 12 | SF8/500kHz | 12500 bps | |
| 13 | SF7/500kHz | 21900 bps | |
| 14 | SF6/500kHz | 37500 bps | **New in RP002-1.0.5** |
| 15 | RFU | - | |

**Example Configuration:**

```json
{
  "msgtype": "router_config",
  "region": "US915",
  "DRs_up": [
    [10, 125, 0], [9, 125, 0], [8, 125, 0], [7, 125, 0],
    [8, 500, 0], [-2, 0, 0], [-2, 0, 0], [6, 125, 0],
    [5, 125, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0],
    [-1, 0, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0]
  ],
  "DRs_dn": [
    [5, 500, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0],
    [-1, 0, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0],
    [12, 500, 0], [11, 500, 0], [10, 500, 0], [9, 500, 0],
    [8, 500, 0], [7, 500, 0], [6, 500, 0], [-1, 0, 0]
  ],
  "upchannels": [
    [902300000, 0, 8], [902500000, 0, 8], [902700000, 0, 8],
    [902900000, 0, 8], [903100000, 0, 8], [903300000, 0, 8],
    [903500000, 0, 8], [903700000, 0, 8]
  ]
}
```

### AU915 RP002-1.0.5

**Uplink Datarates (`DRs_up`):**

| DR | Modulation | Notes |
|----|------------|-------|
| 0 | SF12/125kHz | |
| 1 | SF11/125kHz | |
| 2 | SF10/125kHz | |
| 3 | SF9/125kHz | |
| 4 | SF8/125kHz | |
| 5 | SF7/125kHz | |
| 6 | SF8/500kHz | |
| 7 | LR-FHSS | Not supported |
| 8 | RFU | |
| 9 | SF6/125kHz | **New in RP002-1.0.5** |
| 10 | SF5/125kHz | **New in RP002-1.0.5** |
| 11-15 | RFU | |

**Downlink Datarates (`DRs_dn`):** Same as US915.

**Example Configuration:**

```json
{
  "msgtype": "router_config",
  "region": "AU915",
  "DRs_up": [
    [12, 125, 0], [11, 125, 0], [10, 125, 0], [9, 125, 0],
    [8, 125, 0], [7, 125, 0], [8, 500, 0], [-2, 0, 0],
    [-1, 0, 0], [6, 125, 0], [5, 125, 0], [-1, 0, 0],
    [-1, 0, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0]
  ],
  "DRs_dn": [
    [5, 500, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0],
    [-1, 0, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0],
    [12, 500, 0], [11, 500, 0], [10, 500, 0], [9, 500, 0],
    [8, 500, 0], [7, 500, 0], [6, 500, 0], [-1, 0, 0]
  ],
  "upchannels": [
    [915200000, 0, 10], [915400000, 0, 10], [915600000, 0, 10],
    [915800000, 0, 10], [916000000, 0, 10], [916200000, 0, 10],
    [916400000, 0, 10], [916600000, 0, 10]
  ]
}
```

### EU868 RP002-1.0.5

EU868 uses symmetric datarates (same for uplink and downlink). Can use either `DRs` or `DRs_up`/`DRs_dn`:

| DR | Modulation | Notes |
|----|------------|-------|
| 0 | SF12/125kHz | |
| 1 | SF11/125kHz | |
| 2 | SF10/125kHz | |
| 3 | SF9/125kHz | |
| 4 | SF8/125kHz | |
| 5 | SF7/125kHz | |
| 6 | SF7/250kHz | |
| 7 | FSK 50kbps | |
| 8-11 | LR-FHSS | Not supported |
| 12 | SF6/125kHz | **New in RP002-1.0.5** |
| 13 | SF5/125kHz | **New in RP002-1.0.5** |
| 14-15 | RFU | |

**Example Configuration (symmetric):**

```json
{
  "msgtype": "router_config",
  "region": "EU868",
  "DRs": [
    [12, 125, 0], [11, 125, 0], [10, 125, 0], [9, 125, 0],
    [8, 125, 0], [7, 125, 0], [7, 250, 0], [0, 0, 0],
    [-2, 0, 0], [-2, 0, 0], [-2, 0, 0], [-2, 0, 0],
    [6, 125, 0], [5, 125, 0], [-1, 0, 0], [-1, 0, 0]
  ],
  "upchannels": [
    [868100000, 0, 13], [868300000, 0, 13], [868500000, 0, 13]
  ]
}
```

## Implementation Details

### Code Location

**File:** `src/s2e.c`

```c
// DR table storage
rps_t dr_defs[DR_CNT];      // Legacy symmetric table
rps_t dr_defs_up[DR_CNT];   // Uplink table (RP002-1.0.5)
rps_t dr_defs_dn[DR_CNT];   // Downlink table (RP002-1.0.5)
u1_t  asymmetric_drs;       // Flag: using separate tables

// Get uplink DR definition
rps_t s2e_dr2rps_up (s2ctx_t* s2ctx, u1_t dr) {
    if (dr >= DR_CNT)
        return RPS_ILLEGAL;
    if (s2ctx->asymmetric_drs)
        return s2ctx->dr_defs_up[dr];
    return s2ctx->dr_defs[dr];
}

// Get downlink DR definition
rps_t s2e_dr2rps_dn (s2ctx_t* s2ctx, u1_t dr) {
    if (dr >= DR_CNT)
        return RPS_ILLEGAL;
    if (s2ctx->asymmetric_drs)
        return s2ctx->dr_defs_dn[dr];
    return s2ctx->dr_defs[dr];
}
```

### Parsing in `router_config`

```c
case J_DRs: {
    // Legacy symmetric DR definitions
    parse_dr_array(D, s2ctx->dr_defs, "DRs");
    break;
}
case J_DRs_up: {
    // Uplink-specific DR definitions (RP002-1.0.5)
    parse_dr_array(D, s2ctx->dr_defs_up, "DRs_up");
    s2ctx->asymmetric_drs = 1;
    break;
}
case J_DRs_dn: {
    // Downlink-specific DR definitions (RP002-1.0.5)
    parse_dr_array(D, s2ctx->dr_defs_dn, "DRs_dn");
    s2ctx->asymmetric_drs = 1;
    break;
}
```

### DR Mapping

| Operation | Function | Table Used |
|-----------|----------|------------|
| Uplink frame received | `s2e_dr2rps_up()` | `DRs_up` or `DRs` |
| Uplink DR in `updf` message | Uses uplink table | Maps to DR index |
| Downlink transmission | `s2e_dr2rps_dn()` | `DRs_dn` or `DRs` |
| Downlink DR in `dnmsg` | Uses downlink table | Maps to DR index |

### Upchannels Configuration

The `upchannels` array specifies valid DR ranges per channel:

```json
"upchannels": [[frequency, minDR, maxDR], ...]
```

For SF5/SF6 support, `maxDR` must include the new DR indices:

| Region | SF5/SF6 Uplink DRs | Recommended maxDR |
|--------|-------------------|-------------------|
| US915 | DR7 (SF6), DR8 (SF5) | 8 |
| AU915 | DR9 (SF6), DR10 (SF5) | 10 |
| EU868 | DR12 (SF6), DR13 (SF5) | 13 |

## Backward Compatibility

### Compatibility Matrix

| LNS | Station | Behavior |
|-----|---------|----------|
| Old (only `DRs`) | Old | Symmetric DRs, works |
| Old (only `DRs`) | New | Symmetric DRs, works |
| New (`DRs_up`/`DRs_dn`) | Old | Fields ignored, uses `DRs` |
| New (`DRs_up`/`DRs_dn`) | New | Asymmetric DRs, full support |

### Legacy Configuration

For backward compatibility with older stations, LNS can send both formats:

```json
{
  "msgtype": "router_config",
  "region": "US915",
  "DRs": [
    [10, 125, 0], [9, 125, 0], [8, 125, 0], [7, 125, 0],
    [8, 500, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0],
    [12, 500, 1], [11, 500, 1], [10, 500, 1], [9, 500, 1],
    [8, 500, 1], [7, 500, 1], [-1, 0, 0], [-1, 0, 0]
  ],
  "DRs_up": [...],
  "DRs_dn": [...]
}
```

Old stations use `DRs`, new stations use `DRs_up`/`DRs_dn`.

## Feature Detection

### Version Message

Stations with `updn-dr` support include it in the `features` field:

```json
{
  "msgtype": "version",
  "station": "2.1.0",
  "features": "rmtsh gps updn-dr"
}
```

### LNS Detection Logic

```python
def on_station_version(msg):
    features = msg.get('features', '').split()
    
    if 'updn-dr' in features:
        # Station supports DRs_up/DRs_dn
        return build_router_config_asymmetric()
    else:
        # Use legacy DRs field
        return build_router_config_legacy()
```

### Hardware Considerations

SF5/SF6 spreading factors require SX1302/SX1303 hardware:

| Hardware | SF5/SF6 | Notes |
|----------|---------|-------|
| SX1301 | No | SF7-SF12 only |
| SX1302 | Yes | Full SF5-SF12 support |
| SX1303 | Yes | Full SF5-SF12 support |

The `updn-dr` feature indicates protocol support. SF5/SF6 hardware support depends on the gateway's chipset.

## Message Examples

### Uplink Frame (`updf`)

DR in uplink uses the uplink table:

```json
{
  "msgtype": "updf",
  "MHdr": 64,
  "DevAddr": 12345678,
  "DR": 7,
  "Freq": 902300000,
  "upinfo": { ... }
}
```

With US915 `DRs_up`, DR7 = SF6/125kHz.

### Downlink Message (`dnmsg`)

DR in downlink uses the downlink table:

```json
{
  "msgtype": "dnmsg",
  "DevEui": "00-11-22-33-44-55-66-77",
  "dC": 0,
  "diid": 12345,
  "pdu": "...",
  "RxDelay": 1,
  "RX1DR": 10,
  "RX1Freq": 923300000,
  "RX2DR": 8,
  "RX2Freq": 923300000
}
```

With US915 `DRs_dn`:
- RX1DR 10 = SF10/500kHz
- RX2DR 8 = SF12/500kHz

## References

- [LoRaWAN Regional Parameters RP002-1.0.5](https://resources.lora-alliance.org/technical-specifications)
- [SX1302 Datasheet](https://www.semtech.com/products/wireless-rf/lora-core/sx1302) - SF5/SF6 support
