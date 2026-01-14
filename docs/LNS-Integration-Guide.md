# LNS Integration Guide: TC Protocol Changes for RP2 1.0.5

This document describes the Traffic Controller (TC) JSON protocol changes introduced to support LoRaWAN Regional Parameters 2 (RP2) version 1.0.5, including asymmetric uplink/downlink datarates and SF5/SF6 spreading factors.

## Executive Summary

**New Protocol Fields in `router_config`:**
- `DRs_up` / `DRs_dn` - Separate uplink/downlink datarate tables (US915, AU915)
- `lbt_channels` - Explicit LBT channel configuration (AS923, KR920)
- `lbt_enabled` - Enable/disable LBT from LNS

**Feature Flags** (in `version` message):
- `updn-dr` - Station supports `DRs_up`/`DRs_dn` fields
- `lbtconf` - Station supports `lbt_channels`/`lbt_enabled` fields

**Hardware Requirements:**
- SF5/SF6 requires SX1302/SX1303 chipset
- SX1301 limited to SF7-SF12

**Backward Compatible:** All changes are additive; legacy configurations continue to work.

## Table of Contents

- [Overview](#overview)
- [Capability Detection](#capability-detection)
- [Protocol Changes](#protocol-changes)
  - [Asymmetric Datarate Support](#asymmetric-datarate-support)
  - [DR Array Format](#dr-array-format)
  - [Backward Compatibility](#backward-compatibility)
- [Regional Configurations](#regional-configurations)
  - [US915](#us915)
  - [AU915](#au915)
  - [EU868](#eu868)
- [Hardware Requirements](#hardware-requirements)
- [Implementation Examples](#implementation-examples)
- [Migration Guide](#migration-guide)

## Overview

LoRaWAN Regional Parameters 2 version 1.0.5 introduced several changes that affect how datarates are defined and used:

1. **Asymmetric Datarates**: US915 and AU915 now have different datarate definitions for uplink and downlink
2. **SF5/SF6 Support**: New spreading factors SF5 and SF6 are available on SX1302/SX1303 hardware
3. **Extended DR Range**: Higher DR indices are now defined for SF5/SF6 in various regions

These changes require updates to the `router_config` message sent from the LNS to Basic Station.

## Capability Detection

When Basic Station connects to the LNS, it sends a `version` message that includes capability information:

```json
{
  "msgtype": "version",
  "station": "2.1.0",
  "firmware": "<firmware version>",
  "package": "<firmware version>",
  "model": "<platform identifier>",
  "protocol": 2,
  "features": "rmtsh gps updn-dr lbtconf"
}
```

### Feature Flags

| Feature | Description |
|---------|-------------|
| `rmtsh` | Remote shell support enabled |
| `gps` | GPS support enabled |
| `prod` | Production mode (development features disabled) |
| `updn-dr` | **Separate uplink/downlink datarate support** (RP002-1.0.5) |
| `lbtconf` | **LBT channel configuration support** via `lbt_channels` field |

### Using the `updn-dr` Feature Flag

The `updn-dr` feature flag indicates that Basic Station supports the `DRs_up` and `DRs_dn` fields in `router_config`. LNS implementations can use this to determine which configuration format to send:

| Station Features | LNS Action |
|-----------------|------------|
| `updn-dr` present | Can send `DRs_up`/`DRs_dn` for RP002-1.0.5 regions |
| `updn-dr` absent | Use legacy `DRs` field only |

**Example Detection (Python):**

```python
def on_station_version(msg):
    """Handle version message from Basic Station."""
    features = msg.get('features', '').split()
    
    if 'updn-dr' in features:
        # Station supports separate uplink/downlink datarates
        return build_router_config_rp2()
    else:
        # Use legacy symmetric datarates
        return build_router_config_legacy()
```

**Note:** SF5/SF6 hardware support is determined by the gateway's chipset (SX1302/SX1303), not by a feature flag. The `updn-dr` flag indicates protocol support for separate DR tables, which is independent of hardware capability.

### Using the `lbtconf` Feature Flag

The `lbtconf` feature flag indicates that Basic Station supports the `lbt_channels` and `lbt_enabled` fields in `router_config` for explicit LBT (Listen Before Talk) configuration:

| Station Features | LNS Action |
|-----------------|------------|
| `lbtconf` present | Can send `lbt_channels`, `lbt_enabled`, `lbt_rssi_target` |
| `lbtconf` absent | LBT channels derived from uplink channels (legacy behavior) |

See [LBT Channel Configuration Plan](LBT-Channel-Configuration-Plan.md) for detailed protocol specification.

## Protocol Changes

### Asymmetric Datarate Support

Prior to RP2 1.0.5, all regions used a single `DRs` array for both uplink and downlink datarates. With RP2 1.0.5, some regions (notably US915 and AU915) now have different datarate definitions for uplink vs downlink.

**New Fields in `router_config`:**

| Field | Type | Description |
|-------|------|-------------|
| `DRs_up` | Array | Uplink datarate definitions (16 entries) |
| `DRs_dn` | Array | Downlink datarate definitions (16 entries) |

When `DRs_up` and `DRs_dn` are present, Basic Station uses:
- `DRs_up` for mapping received uplink frames to DR values
- `DRs_dn` for transmitting downlink frames

### DR Array Format

Each DR entry is a 3-element array: `[SF, BW, dnonly]`

| Element | Value | Meaning |
|---------|-------|---------|
| SF | 5-12 | Spreading factor (SF5=5, SF6=6, ..., SF12=12) |
| SF | 0 | FSK modulation |
| SF | -1 | Reserved/Undefined (RFU) |
| SF | -2 | LR-FHSS (not supported by SX130x) |
| BW | 125/250/500 | Bandwidth in kHz |
| dnonly | 0/1 | 1 = downlink only (not valid for uplink) |

**Example DR entry:** `[7, 125, 0]` = SF7 at 125kHz, valid for both up and down

### Backward Compatibility

Basic Station maintains full backward compatibility:

| Configuration | Behavior |
|--------------|----------|
| Only `DRs` present | Uses symmetric datarates (legacy behavior) |
| `DRs_up` and `DRs_dn` present | Uses asymmetric datarates (RP2 1.0.5) |
| All three present | `DRs_up`/`DRs_dn` take precedence, `DRs` ignored |

**Important:** When using asymmetric DRs, you MUST provide both `DRs_up` AND `DRs_dn`. Providing only one will result in undefined behavior.

## Regional Configurations

### US915

US915 has asymmetric datarates in RP2 1.0.5:

**Uplink Datarates (`DRs_up`):**

| DR | Modulation | Notes |
|----|------------|-------|
| 0 | SF10/125kHz | |
| 1 | SF9/125kHz | |
| 2 | SF8/125kHz | |
| 3 | SF7/125kHz | |
| 4 | SF8/500kHz | |
| 5-6 | LR-FHSS | Not supported |
| 7 | SF6/125kHz | **New in RP2 1.0.5** |
| 8 | SF5/125kHz | **New in RP2 1.0.5** |
| 9-15 | RFU | |

**Downlink Datarates (`DRs_dn`):**

| DR | Modulation | Notes |
|----|------------|-------|
| 0 | SF5/500kHz | **New in RP2 1.0.5** |
| 1-7 | RFU | |
| 8 | SF12/500kHz | |
| 9 | SF11/500kHz | |
| 10 | SF10/500kHz | |
| 11 | SF9/500kHz | |
| 12 | SF8/500kHz | |
| 13 | SF7/500kHz | |
| 14 | SF6/500kHz | **New in RP2 1.0.5** |
| 15 | RFU | |

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

### AU915

AU915 also has asymmetric datarates, with different uplink structure than US915:

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
| 9 | SF6/125kHz | **New in RP2 1.0.5** |
| 10 | SF5/125kHz | **New in RP2 1.0.5** |
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

### EU868

EU868 uses symmetric datarates (same for uplink and downlink), but RP2 1.0.5 adds SF5/SF6 at DR12/DR13:

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
| 12 | SF6/125kHz | **New in RP2 1.0.5** |
| 13 | SF5/125kHz | **New in RP2 1.0.5** |
| 14-15 | RFU | |

**Example Configuration (symmetric DRs):**

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
    [868100000, 0, 13], [868300000, 0, 13], [868500000, 0, 13],
    [868850000, 0, 13], [869050000, 0, 13], [869525000, 0, 13]
  ]
}
```

## Hardware Requirements

### SF5/SF6 Support

SF5 and SF6 spreading factors are **only supported on SX1302/SX1303** chipsets:

| Hardware | SF5/SF6 Support | Notes |
|----------|-----------------|-------|
| SX1301 | ❌ No | SF7-SF12 only |
| SX1302 | ✅ Yes | SF5-SF12 supported |
| SX1303 | ✅ Yes | SF5-SF12 supported |

**Graceful Degradation:** If an LNS sends DR definitions with SF5/SF6 to a gateway with SX1301 hardware:
- Basic Station will accept the configuration
- SF5/SF6 DRs will be marked as invalid internally
- Uplinks at SF5/SF6 will not be received
- Downlinks at SF5/SF6 DRs will fail

### Upchannels Configuration

The `upchannels` array specifies valid DR ranges for each channel:

```json
"upchannels": [[frequency, minDR, maxDR], ...]
```

For SF5/SF6 support, ensure `maxDR` includes the SF5/SF6 DR indices:

| Region | SF5/SF6 Uplink DRs | Recommended maxDR |
|--------|-------------------|-------------------|
| US915 | DR7 (SF6), DR8 (SF5) | 8 |
| AU915 | DR9 (SF6), DR10 (SF5) | 10 |
| EU868 | DR12 (SF6), DR13 (SF5) | 13 |

## Implementation Examples

### Python Example (LNS Side)

```python
def build_router_config_us915_rp2():
    """Build US915 router_config with RP2 1.0.5 asymmetric DRs."""
    return {
        'msgtype': 'router_config',
        'region': 'US915',
        'freq_range': [902000000, 928000000],
        'max_eirp': 30.0,
        
        # Asymmetric datarates for RP2 1.0.5
        'DRs_up': [
            [10, 125, 0],  # DR0 - SF10/125
            [9, 125, 0],   # DR1 - SF9/125
            [8, 125, 0],   # DR2 - SF8/125
            [7, 125, 0],   # DR3 - SF7/125
            [8, 500, 0],   # DR4 - SF8/500
            [-2, 0, 0],    # DR5 - LR-FHSS (unsupported)
            [-2, 0, 0],    # DR6 - LR-FHSS (unsupported)
            [6, 125, 0],   # DR7 - SF6/125 (NEW)
            [5, 125, 0],   # DR8 - SF5/125 (NEW)
            [-1, 0, 0], [-1, 0, 0], [-1, 0, 0],
            [-1, 0, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0]
        ],
        'DRs_dn': [
            [5, 500, 0],   # DR0 - SF5/500 (NEW)
            [-1, 0, 0], [-1, 0, 0], [-1, 0, 0],
            [-1, 0, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0],
            [12, 500, 0],  # DR8 - SF12/500
            [11, 500, 0],  # DR9 - SF11/500
            [10, 500, 0],  # DR10 - SF10/500
            [9, 500, 0],   # DR11 - SF9/500
            [8, 500, 0],   # DR12 - SF8/500
            [7, 500, 0],   # DR13 - SF7/500
            [6, 500, 0],   # DR14 - SF6/500 (NEW)
            [-1, 0, 0]
        ],
        
        # Include SF5/SF6 in upchannels (maxDR=8)
        'upchannels': [
            [902300000, 0, 8],
            [902500000, 0, 8],
            [902700000, 0, 8],
            [902900000, 0, 8],
            [903100000, 0, 8],
            [903300000, 0, 8],
            [903500000, 0, 8],
            [903700000, 0, 8]
        ],
        
        # Hardware config
        'hwspec': 'sx1302/1',
        'sx1302_conf': [...],  # Radio configuration
    }


def build_router_config_us915_legacy():
    """Build US915 router_config with legacy symmetric DRs."""
    return {
        'msgtype': 'router_config',
        'region': 'US915',
        'freq_range': [902000000, 928000000],
        'max_eirp': 30.0,
        
        # Legacy symmetric datarates (pre-RP2 1.0.5)
        'DRs': [
            [10, 125, 0],  # DR0
            [9, 125, 0],   # DR1
            [8, 125, 0],   # DR2
            [7, 125, 0],   # DR3
            [8, 500, 0],   # DR4
            [-1, 0, 0], [-1, 0, 0], [-1, 0, 0],
            [12, 500, 1],  # DR8 - downlink only
            [11, 500, 1],  # DR9 - downlink only
            [10, 500, 1],  # DR10 - downlink only
            [9, 500, 1],   # DR11 - downlink only
            [8, 500, 1],   # DR12 - downlink only
            [7, 500, 1],   # DR13 - downlink only
            [-1, 0, 0], [-1, 0, 0]
        ],
        
        'upchannels': [
            [902300000, 0, 4],  # DR0-4 only (no SF5/SF6)
            ...
        ],
        
        'hwspec': 'sx1301/1',
        'sx1301_conf': [...],
    }
```

### Handling Uplink DR in Messages

When Basic Station reports an uplink frame, the `DR` field uses the uplink DR table:

```json
{
  "msgtype": "updf",
  "DR": 7,          // DR7 = SF6/125kHz (using DRs_up table)
  "Freq": 902300000,
  ...
}
```

### Specifying Downlink DR

When sending downlink, use the downlink DR table indices:

```json
{
  "msgtype": "dnmsg",
  "RX1DR": 10,      // DR10 = SF10/500kHz (using DRs_dn table)
  "RX1Freq": 923300000,
  "RX2DR": 8,       // DR8 = SF12/500kHz (using DRs_dn table)
  "RX2Freq": 923300000,
  ...
}
```

## Migration Guide

### For LNS Developers

1. **Detect Station Capabilities**
   - Parse the `features` field in the `version` message
   - Check for `updn-dr` to determine if separate uplink/downlink DRs are supported
   - Check hardware type (SX1302/SX1303) for SF5/SF6 support

2. **Update Router Config Generation**
   - If `updn-dr` feature present: use `DRs_up` and `DRs_dn` for US915/AU915
   - If `updn-dr` feature absent: use legacy `DRs` field only
   - For symmetric regions (EU868), can use either format

3. **Update Upchannels**
   - Extend `maxDR` in upchannels to include SF5/SF6 DR indices
   - Use appropriate maxDR based on gateway hardware capability

4. **Update DR Mapping**
   - When processing uplinks, map DR using uplink table
   - When generating downlinks, map DR using downlink table

### Backward Compatibility Checklist

| Scenario | Action |
|----------|--------|
| Old LNS + New Station | Works - Station accepts legacy `DRs` |
| New LNS + Old Station | Check for `updn-dr` feature; use `DRs` if absent |
| Mixed fleet | Detect capabilities via `features`, send appropriate config |

### Testing Recommendations

1. **Unit Tests**
   - Verify DR mapping for both uplink and downlink
   - Test undefined/RFU DR handling

2. **Integration Tests**  
   - Test with both SX1301 and SX1302 hardware
   - Verify SF5/SF6 frames are correctly handled

3. **Regression Tests**
   - Ensure legacy `DRs` configurations still work
   - Test upgrade path from legacy to RP2 1.0.5

## Reference

- [LoRaWAN Regional Parameters RP2-1.0.5](https://resources.lora-alliance.org/technical-specifications)
- [Basic Station Protocol Documentation](https://lora-developers.semtech.com/build/software/lora-basics/lora-basics-for-gateways/)
- [SX1302/SX1303 Datasheet](https://www.semtech.com/products/wireless-rf/lora-core/sx1302)
