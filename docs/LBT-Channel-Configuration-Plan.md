# LBT Channel Configuration Feature Plan

This document outlines the plan to add configurable Listen Before Talk (LBT) channels to Basic Station, allowing the LNS to specify LBT channel frequencies separately from uplink channels.

## Executive Summary

**Problem:** LBT channels are currently auto-derived from uplink channels, providing no flexibility for custom LBT configurations.

**Solution:** Add new `router_config` fields:
- `lbt_enabled` - Enable/disable LBT from LNS
- `lbt_channels` - Array of explicit LBT channel configurations
- `lbt_rssi_target` - RSSI threshold for channel clear detection

**Feature Flag:** `lbtconf` - Indicates station supports explicit LBT configuration

**Backward Compatible:** If `lbt_channels` not provided, falls back to deriving from uplink channels.

**Hardware:** Supports SX1301 (8 channels, FPGA LBT) and SX1302/SX1303 (16 channels, SX1261 LBT).

## Table of Contents

- [Background](#background)
- [Current Implementation](#current-implementation)
- [Proposed Changes](#proposed-changes)
- [Protocol Changes](#protocol-changes)
- [Implementation Details](#implementation-details)
- [Backward Compatibility](#backward-compatibility)
- [Testing Plan](#testing-plan)
- [Timeline](#timeline)

## Background

### What is LBT?

Listen Before Talk (LBT), also known as Clear Channel Assessment (CCA), is a regulatory requirement in certain regions (AS923, KR920) that requires gateways to listen on a channel before transmitting to ensure it is not already in use.

### Regulatory Requirements

| Region | LBT Required | RSSI Target | Scan Time |
|--------|--------------|-------------|-----------|
| AS923-1 | Yes | -80 dBm | 5000 µs |
| KR920 | Yes | -67 dBm | 5000 µs |
| EU868 | No | - | - |
| US915 | No | - | - |

### Why Configurable LBT Channels?

Currently, LBT channels are automatically derived from the configured uplink channels. However, there are scenarios where LBT channels should differ from uplink channels:

1. **Downlink-only frequencies**: Some frequencies used for downlink may not be in the uplink channel plan
2. **Regulatory compliance**: Specific LBT frequencies may be mandated that don't align with the channel plan
3. **Operational flexibility**: Network operators may need fine-grained control over LBT behavior
4. **Multi-gateway coordination**: Different gateways may need different LBT configurations

## Current Implementation

### Code Flow

1. **Region Detection**: `router_config` message specifies the region (e.g., `AS923-1`, `KR920`)
2. **CCA Flag**: If the region requires CCA, `cca_region` is set
3. **LBT Setup**: `setup_LBT()` is called in `sx130xconf.c` or `sx1301v2conf.c`
4. **Channel Population**: If `nb_channel == 0`, LBT channels are derived from uplink channels

### Key Code Locations

| File | Function | Purpose |
|------|----------|---------|
| `src/sx130xconf.c` | `setup_LBT()` | SX1301/SX1302 LBT configuration |
| `src/sx1301v2conf.c` | `setup_LBT()` | Master/slave LBT configuration |
| `src/s2e.c` | `s2e_canTxEU868()`, `s2e_canTxPerChnlDC()` | TX permission checks |

### Current Auto-Population Logic

From `sx130xconf.c`:

```c
// By default use up link frequencies as LBT frequencies
// Otherwise we should have gotten a freq list from the server
if( sx130xconf->lbt.nb_channel == 0 ) {
    for( int rfi=0; rfi < LGW_RF_CHAIN_NB; rfi++ ) {
        // ... iterate through enabled IF chains
        // ... add frequencies to LBT channel list
    }
}
```

### LBT Channel Limits

| Hardware | Max LBT Channels | Constant | LBT Implementation |
|----------|-----------------|----------|-------------------|
| SX1301 | 8 | `LBT_CHANNEL_FREQ_NB` | Built-in FPGA-based LBT |
| SX1302 | 16 | `LGW_LBT_CHANNEL_NB_MAX` | External SX1261 radio for LBT |
| SX1303 | 16 | `LGW_LBT_CHANNEL_NB_MAX` | External SX1261 radio for LBT |

### Hardware-Specific Implementation

The LBT feature is implemented differently on each chipset:

**SX1301:**
- Uses `lgw_lbt_setconf()` HAL function
- LBT performed by FPGA on the concentrator
- Configuration via `struct lgw_conf_lbt_s`

**SX1302/SX1303:**
- Uses `lgw_sx1261_setconf()` HAL function
- LBT performed by external SX1261 radio
- Configuration via `sx1261_cfg.lbt_conf`
- Additional parameter: `transmit_time_ms` (dwell time limit)

## Proposed Changes

### Overview

Add a new `lbt_channels` field to the `router_config` message that allows the LNS to specify LBT channel frequencies explicitly. If not provided, maintain current behavior of deriving LBT channels from uplink configuration.

### Feature Flag

No new feature flag is required. This is a backward-compatible extension to the existing protocol.

## Protocol Changes

### New Fields in `router_config`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lbt_enabled` | Boolean | No | Enable/disable LBT (default: region-dependent) |
| `lbt_channels` | Array | No | Array of LBT channel configurations |

### LBT Channel Entry Format

Each entry in `lbt_channels` is an object:

```json
{
  "freq_hz": 923200000,
  "scan_time_us": 5000,
  "bandwidth": 125000
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `freq_hz` | Integer | Yes | - | Channel frequency in Hz |
| `scan_time_us` | Integer | No | Region default | Channel scan time in microseconds |
| `bandwidth` | Integer | No | 125000 | Channel bandwidth in Hz (125000, 250000, 500000) |

### Example `router_config` with LBT Channels

```json
{
  "msgtype": "router_config",
  "region": "AS923-1",
  "DRs": [...],
  "upchannels": [
    [923200000, 0, 5],
    [923400000, 0, 5]
  ],
  "lbt_channels": [
    {"freq_hz": 923200000, "scan_time_us": 5000},
    {"freq_hz": 923400000, "scan_time_us": 5000},
    {"freq_hz": 923600000, "scan_time_us": 5000},
    {"freq_hz": 923800000, "scan_time_us": 5000}
  ],
  "sx1302_conf": [...]
}
```

### LBT Parameters in `router_config`

Additional LBT parameters can be specified at the top level:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `lbt_enabled` | Boolean | true (if region requires) | Enable/disable LBT |
| `lbt_rssi_target` | Integer | Region default | RSSI threshold in dBm |
| `lbt_rssi_offset` | Integer | 0 | RSSI calibration offset |
| `lbt_scan_time_us` | Integer | Region default | Default scan time for all channels |

**Example with explicit LBT channels:**

```json
{
  "msgtype": "router_config",
  "region": "AS923-1",
  "lbt_enabled": true,
  "lbt_rssi_target": -80,
  "lbt_scan_time_us": 5000,
  "lbt_channels": [
    {"freq_hz": 923200000},
    {"freq_hz": 923400000}
  ]
}
```

**Example disabling LBT (for testing/development):**

```json
{
  "msgtype": "router_config",
  "region": "AS923-1",
  "lbt_enabled": false
}
```

Note: Disabling LBT in regions where it is required may violate regulatory requirements. This option is intended for testing and development purposes only.

## Implementation Details

### Phase 1: Protocol Parsing

#### Files to Modify

1. **`src/kwlist.txt`** - Add new keywords:
   ```
   lbt_enabled
   lbt_channels
   lbt_rssi_target
   lbt_scan_time_us
   ```

2. **`src/s2e.c`** - Parse `lbt_channels` in `handle_router_config()`:
   - Store LBT channel list in s2ctx or pass to RAL layer
   - Parse `lbt_rssi_target`, `lbt_scan_time_us` parameters

#### New Data Structures

```c
// In s2e.h or sx130xconf.h
typedef struct {
    u4_t freq_hz;
    u2_t scan_time_us;
    u1_t bandwidth;  // BW_125KHZ, BW_250KHZ, BW_500KHZ
} lbt_channel_t;

typedef struct {
    u1_t nb_channel;
    s1_t rssi_target;
    s1_t rssi_offset;
    u2_t default_scan_time_us;
    lbt_channel_t channels[LBT_MAX_CHANNELS];
} lbt_config_t;
```

### Phase 2: Configuration Application

#### Files to Modify

1. **`src/sx130xconf.c`** - Modify `setup_LBT()` for SX1301 and SX1302/SX1303:

   **SX1301 path (`#if !defined(CFG_sx1302)`):**
   ```c
   static int setup_LBT (struct sx130xconf* sx130xconf, u4_t cca_region, lbt_config_t* lbt_config) {
       // If LNS provided LBT channels, use them
       if( lbt_config && lbt_config->nb_channel > 0 ) {
           for( int i=0; i < lbt_config->nb_channel && i < LBT_CHANNEL_FREQ_NB; i++ ) {
               sx130xconf->lbt.channels[i].freq_hz = lbt_config->channels[i].freq_hz;
               sx130xconf->lbt.channels[i].scan_time_us = lbt_config->channels[i].scan_time_us;
           }
           sx130xconf->lbt.nb_channel = min(lbt_config->nb_channel, LBT_CHANNEL_FREQ_NB);
           if( lbt_config->rssi_target != 0 )
               sx130xconf->lbt.rssi_target = lbt_config->rssi_target;
       }
       
       // Existing fallback: derive from uplink channels
       if( sx130xconf->lbt.nb_channel == 0 ) {
           // ... existing auto-population logic ...
       }
       
       // Apply via lgw_lbt_setconf()
   }
   ```

   **SX1302/SX1303 path (`#else` / `CFG_sx1302`):**
   ```c
   static int setup_LBT (struct sx130xconf* sx130xconf, u4_t cca_region, lbt_config_t* lbt_config) {
       // If LNS provided LBT channels, use them
       if( lbt_config && lbt_config->nb_channel > 0 ) {
           for( int i=0; i < lbt_config->nb_channel && i < LGW_LBT_CHANNEL_NB_MAX; i++ ) {
               sx130xconf->sx1261_cfg.lbt_conf.channels[i].freq_hz = lbt_config->channels[i].freq_hz;
               sx130xconf->sx1261_cfg.lbt_conf.channels[i].scan_time_us = lbt_config->channels[i].scan_time_us;
               sx130xconf->sx1261_cfg.lbt_conf.channels[i].bandwidth = lbt_config->channels[i].bandwidth;
               sx130xconf->sx1261_cfg.lbt_conf.channels[i].transmit_time_ms = TX_DWELLTIME_LBT;
           }
           sx130xconf->sx1261_cfg.lbt_conf.nb_channel = min(lbt_config->nb_channel, LGW_LBT_CHANNEL_NB_MAX);
           if( lbt_config->rssi_target != 0 )
               sx130xconf->sx1261_cfg.lbt_conf.rssi_target = lbt_config->rssi_target;
       }
       
       // Existing fallback: derive from uplink channels
       if( sx130xconf->sx1261_cfg.lbt_conf.nb_channel == 0 ) {
           // ... existing auto-population logic ...
       }
       
       // Apply via lgw_sx1261_setconf()
   }
   ```

2. **`src/sx1301v2conf.c`** - Similar modifications for master/slave configuration (SX1301-based multi-board setups)

### Phase 3: Validation

Add validation for LBT channel configuration:

```c
static int validate_lbt_config(lbt_config_t* lbt_config, u4_t cca_region) {
    // Check channel count limits
    if( lbt_config->nb_channel > LBT_MAX_CHANNELS ) {
        LOG(MOD_RAL|ERROR, "Too many LBT channels: %d (max %d)", 
            lbt_config->nb_channel, LBT_MAX_CHANNELS);
        return 0;
    }
    
    // Validate frequencies are within region bounds
    // Validate scan times are within acceptable range
    // Warn if unusual configurations detected
    
    return 1;
}
```

## Backward Compatibility

### Compatibility Matrix

| LNS Version | Station Version | Behavior |
|-------------|-----------------|----------|
| Old (no `lbt_channels`) | Old | Uses uplink channels for LBT |
| Old (no `lbt_channels`) | New | Uses uplink channels for LBT (unchanged) |
| New (with `lbt_channels`) | Old | `lbt_channels` ignored, uses uplink channels |
| New (with `lbt_channels`) | New | Uses LNS-provided LBT channels |

### Fallback Behavior

1. If `lbt_channels` is not present → derive from uplink channels (existing behavior)
2. If `lbt_channels` is empty array → derive from uplink channels
3. If `lbt_channels` has entries → use LNS-provided configuration
4. If individual channel missing `scan_time_us` → use `lbt_scan_time_us` or region default

### Feature Detection

LNS implementations can check station version (≥2.1.0) to determine if `lbt_channels` is supported. No explicit feature flag is needed since the field is simply ignored by older stations.

## Testing Plan

### Unit Tests

1. **Parsing Tests**
   - Parse `router_config` with `lbt_channels`
   - Parse with missing optional fields
   - Parse with invalid values (out of range, wrong types)
   - Parse empty `lbt_channels` array

2. **Configuration Tests**
   - Verify LBT channels applied correctly to HAL structures
   - Verify fallback to uplink channels when not provided
   - Verify channel limits enforced

### Integration Tests

1. **AS923-1 Region**
   - Test with explicit LBT channels
   - Test without LBT channels (fallback)
   - Verify LBT behavior with simulated busy channel

2. **KR920 Region**
   - Same tests as AS923-1 with different RSSI threshold

3. **Non-LBT Regions**
   - Verify `lbt_channels` is ignored for EU868, US915

4. **Hardware Platform Tests**
   - **SX1301**: Verify LBT channels applied via `lgw_lbt_setconf()`
   - **SX1302/SX1303**: Verify LBT channels applied via `lgw_sx1261_setconf()`
   - **Master/Slave**: Verify LBT distribution across boards in `sx1301v2conf.c`

### Regression Tests

1. Existing LBT tests must continue to pass
2. Verify no change in behavior when `lbt_channels` not provided

## Implementation Status

### Milestone 1: Protocol Definition (Complete)
- Define JSON schema for `lbt_channels`
- Document in LNS Integration Guide

### Milestone 2: Parsing Implementation (Complete)
- Added keywords to `kwlist.txt`: `lbt_enabled`, `lbt_channels`, `lbt_rssi_target`, `lbt_rssi_offset`, `lbt_scan_time_us`
- Implemented parsing in `s2e.c` `handle_router_config()`
- Added `struct lbt_config` and `struct lbt_channel` data structures in `sx130xconf.h`

### Milestone 3: Configuration Application (Complete)
- Modified `setup_LBT()` in `sx130xconf.c` to accept LBT config from LNS
- Modified `setup_LBT()` in `sx1301v2conf.c` similarly
- Added `lbt_config` parameter to `ral_config()` and propagated through the call chain
- Added `lbtconf` feature flag to version message
- SX1302/SX1303 LBT structures defined in `sx130xconf.h` for simulation builds

### Milestone 4: Testing (Complete)
- Existing `test3c-cca` validates basic CCA/LBT functionality (KR920 region, auto-derived channels)
- New `test3d-lbtconf` validates explicit `lbt_channels` configuration (AS923-1 region)

### Milestone 5: Documentation (Complete)
- This plan document updated with implementation status

## Design Decisions

1. **Per-channel RSSI targets**: Not supported. HAL does not support per-channel RSSI thresholds; a single `rssi_target` applies to all LBT channels.

2. **LBT disable flag**: Supported via `lbt_enabled: false` in `router_config`. This provides a cleaner alternative to the existing `nocca` runtime flag.

3. **Dynamic updates**: Not supported. LBT configuration is applied at connection time. If the LNS needs to change LBT configuration, it should disconnect and reconnect with new settings.

## References

- [LoRaWAN Regional Parameters](https://resources.lora-alliance.org/technical-specifications)
- [SX1302 HAL Documentation](https://github.com/Lora-net/sx1302_hal)
- [AS923 Regulatory Requirements](https://www.thethingsnetwork.org/docs/lorawan/regional-parameters/)
