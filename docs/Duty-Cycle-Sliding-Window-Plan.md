# Duty Cycle Sliding Window Implementation Plan

This document outlines the plan to change the duty cycle implementation from a "time-off-air" approach to a sliding window approach that more accurately reflects regulatory requirements across multiple regions.

## Executive Summary

**Problem:** Current implementation blocks transmission for a fixed period after each TX. This is overly conservative and doesn't match regulations which define duty cycle as percentage over a rolling time period.

**Solution:** Implement sliding window duty cycle tracking:
- Track actual TX time per band/channel over a configurable window (default 1 hour)
- Allow transmission if cumulative TX time in window is within duty cycle limit
- Support multiple regions: EU868, AS923, IN865, and others
- More accurate and allows bursty traffic patterns

**Feature Flag:** `dutyconf` - Indicates station supports configurable duty cycle parameters

**New `router_config` Fields:**
- `duty_cycle_window` - Sliding window duration in seconds (default 3600)
- `duty_cycle_limits` - Per-band or per-channel duty cycle limits
- `duty_cycle_mode` - Mode selection: `band`, `channel`, or `power`

**Backward Compatible:** 
- Uses existing hardcoded EU868 bands (K/L/M/N/P/Q) by default
- Default 1-hour sliding window when `dutyconf` feature present
- `duty_cycle_enabled` flag to enable/disable from LNS

## Implementation Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Data Structures (`s2e.h`) | COMPLETE |
| Phase 2 | Core Functions (`s2e.c`) | COMPLETE |
| Phase 3 | Configuration Parsing | COMPLETE |
| Phase 4 | Feature Flag (`dutyconf`) | COMPLETE |
| Testing | Region-specific DC tests | COMPLETE |

**Implemented Features:**
- `duty_cycle_enabled` field in `router_config` (disable station-side DC enforcement)
- `duty_cycle_window` field (configurable sliding window in seconds, 60-86400)
- `duty_cycle_mode` field: `legacy`, `band`, `channel`, `power`
- `duty_cycle_limits` field (per-band or per-channel limits in permille)
- `dutyconf` feature flag advertised to LNS
- Sliding window TX history tracking with configurable record count
- Multi-band support (EU868) and multi-channel support (AS923/KR920)

**Test Coverage:**
- `regr-tests/test9a-dc-eu868/` - EU868 band-based duty cycle tests
- `regr-tests/test9b-dc-as923/` - AS923 channel-based duty cycle tests
- `regr-tests/test9c-dc-kr920/` - KR920 channel-based duty cycle tests

## Table of Contents

- [Background](#background)
- [Current Implementation](#current-implementation)
- [ETSI Regulations](#etsi-regulations)
- [Proposed Solution](#proposed-solution)
- [Protocol Changes](#protocol-changes)
- [Implementation Details](#implementation-details)
- [Memory Considerations](#memory-considerations)
- [Backward Compatibility](#backward-compatibility)
- [Testing Plan](#testing-plan)

## Background

### Regions with Duty Cycle Requirements

#### EU868 (ETSI EN 300 220)

| Band | Frequency Range | Duty Cycle | Max TX Time/Hour |
|------|-----------------|------------|------------------|
| K | 863 - 865 MHz | 0.1% | 3.6 seconds |
| L | 865 - 868 MHz | 1% | 36 seconds |
| M | 868 - 868.6 MHz | 1% | 36 seconds |
| N | 868.7 - 869.2 MHz | 0.1% | 3.6 seconds |
| P | 869.4 - 869.65 MHz | 10% | 360 seconds |
| Q | 869.7 - 870 MHz | 1% | 36 seconds |

#### AS923 (Country-Specific)

| Country | Duty Cycle | Notes |
|---------|------------|-------|
| Japan (AS923-1) | 10% | All channels, with LBT |
| Singapore | None | No duty cycle requirement |
| Thailand | 1% or 10% | Power-based: 10% for ≤+17 dBm EIRP, 1% for >+17 dBm |
| Other AS923 | Varies | Country-specific regulations |

#### IN865

| Frequency Range | Duty Cycle | Max TX Time/Hour |
|-----------------|------------|------------------|
| 865 - 867 MHz | 10% | 360 seconds |

#### EU433

| Band | Frequency Range | Duty Cycle | Max TX Time/Hour |
|------|-----------------|------------|------------------|
| All | 433.05 - 434.79 MHz | 10% | 360 seconds |

### Regulatory References

**ETSI EN 300 220** defines duty cycle as:

> "Duty cycle is defined as the ratio, expressed as a percentage, of the maximum transmitter 'on' time on one carrier frequency, relative to a one hour period."

Key points:
- Reference period is typically **1 hour**
- Duty cycle is cumulative over the period, not per-transmission
- A device can transmit in bursts as long as total TX time stays within limit
- Some regions have power-based duty cycle (e.g., Thailand)

## Current Implementation

### Approach: Time-Off-Air After Transmission

The current implementation calculates a "blocked until" time after each transmission:

```c
// From s2e.c
static const u2_t DC_EU868BAND_RATE[] = {
    [DC_BAND_K]= 1000,  // 0.1% = 1/1000
    [DC_BAND_L]=  100,  // 1%   = 1/100
    [DC_BAND_M]=  100,  // 1%
    [DC_BAND_N]= 1000,  // 0.1%
    [DC_BAND_P]=   10,  // 10%  = 1/10
    [DC_BAND_Q]=  100,  // 1%
};

// After transmission:
dcbands[band] = txtime + airtime * DC_EU868BAND_RATE[band];
```

### Example

For a 100ms transmission in Band L (1% duty cycle):
- `blocked_until = txtime + 100ms * 100 = txtime + 10 seconds`

### Problems

1. **Overly Conservative**: Cannot burst multiple transmissions even if total would be within duty cycle
2. **Doesn't Match Regulations**: ETSI specifies cumulative time over 1 hour, not time-off-air
3. **No Flexibility**: Cannot configure window size for different regulatory interpretations
4. **Memory Efficient but Inaccurate**: Only stores one timestamp per band

## ETSI Regulations

### EN 300 220-2 V3.2.1 (2018-06)

Section 4.3.1 - Duty Cycle:

> "For equipment operating in the 863 MHz to 870 MHz band, the Duty Cycle shall not be greater than X% of any one hour period."

### Interpretation

- **One Hour Period**: Rolling/sliding window, not fixed calendar hours
- **Cumulative**: Sum of all transmission times in the window
- **Per Band**: Each frequency band has its own duty cycle limit

### Example Scenario

Band L (1% duty cycle, 36s max per hour):
- 10:00:00 - TX 5s
- 10:15:00 - TX 5s
- 10:30:00 - TX 5s
- 10:45:00 - TX 5s
- 10:50:00 - TX 5s (Total: 25s, OK)
- 11:00:01 - First 5s TX expires from window, can TX another 5s

Current implementation would require 500s (8.3 min) wait after each 5s TX.

## Proposed Solution

### Sliding Window Approach

Track transmission history and calculate cumulative TX time within the window:

```
                      Sliding Window (default 1 hour)
    |<--------------------------------------------------------->|
    |                                                           |
    [TX1]     [TX2]           [TX3]    [TX4]        [TX5]      NOW
    |___|     |__|            |____|   |_|          |__|
    
    Cumulative TX time = sum of all TX durations in window
    Can TX if: cumulative + new_airtime <= duty_cycle_limit * window
```

### Data Structure

Store recent transmissions per band:

```c
typedef struct {
    ustime_t timestamp;   // When transmission occurred
    u4_t     airtime_us;  // Duration in microseconds
} dc_tx_record_t;

typedef struct {
    dc_tx_record_t records[DC_MAX_RECORDS];
    u1_t head;            // Circular buffer head
    u1_t count;           // Number of valid records
    u4_t cumulative_us;   // Cached cumulative TX time in window
} dc_band_history_t;
```

### Algorithm

```c
int can_transmit(dc_band_history_t* history, u4_t new_airtime_us, 
                 u4_t window_us, u4_t limit_permille) {
    ustime_t now = rt_getTime();
    ustime_t window_start = now - window_us;
    
    // Expire old records and recalculate cumulative
    u4_t cumulative = 0;
    for (int i = 0; i < history->count; i++) {
        int idx = (history->head + i) % DC_MAX_RECORDS;
        if (history->records[idx].timestamp >= window_start) {
            cumulative += history->records[idx].airtime_us;
        }
    }
    
    // Check if new transmission would exceed limit
    u4_t max_tx_us = (window_us / 1000) * limit_permille;  // permille = 1/1000
    return (cumulative + new_airtime_us) <= max_tx_us;
}
```

## Protocol Changes

### New Fields in `router_config`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `duty_cycle_enabled` | Boolean | Region-dependent | Enable/disable duty cycle enforcement |
| `duty_cycle_window` | Integer | 3600 | Sliding window duration in seconds |
| `duty_cycle_mode` | String | `"band"` | Mode: `"band"`, `"channel"`, or `"power"` |
| `duty_cycle_limits` | Object/Array | Region defaults | Duty cycle limits (permille) |

**Default `duty_cycle_enabled` by Region:**

| Region | Default Enabled | Notes |
|--------|-----------------|-------|
| EU868 | Yes | ETSI regulations |
| EU433 | Yes | ETSI regulations |
| AS923-1 (Japan) | Yes | With LBT |
| AS923-1 (Thailand) | Yes | Power-based |
| AS923-1 (Singapore) | No | No duty cycle requirement |
| IN865 | Yes | 10% limit |
| US915 | No | FCC regulations (no duty cycle) |
| AU915 | No | No duty cycle requirement |

**Note:** Setting `duty_cycle_enabled: false` is equivalent to the existing `nodc: true` flag.

### Duty Cycle Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `band` | Per frequency band limits (EU868 style) | EU868 with K/L/M/N/P/Q bands |
| `channel` | Single limit for all channels | AS923, IN865 with uniform limit |
| `power` | Power-based limits | Thailand (10% ≤+17dBm, 1% >+17dBm) |

### Example Configurations

**EU868 (band-based, default):**
```json
{
  "msgtype": "router_config",
  "region": "EU868",
  "duty_cycle_window": 3600,
  "duty_cycle_mode": "band",
  "duty_cycle_limits": {
    "K": 1,      // 0.1% = 1 permille
    "L": 10,     // 1% = 10 permille
    "M": 10,     // 1%
    "N": 1,      // 0.1%
    "P": 100,    // 10% = 100 permille
    "Q": 10      // 1%
  }
}
```

**AS923 Japan (channel-based, 10%):**
```json
{
  "msgtype": "router_config",
  "region": "AS923-1",
  "duty_cycle_window": 3600,
  "duty_cycle_mode": "channel",
  "duty_cycle_limits": 100
}
```

**IN865 (channel-based, 10%):**
```json
{
  "msgtype": "router_config",
  "region": "IN865",
  "duty_cycle_window": 3600,
  "duty_cycle_mode": "channel",
  "duty_cycle_limits": 100
}
```

**Thailand (power-based):**
```json
{
  "msgtype": "router_config",
  "region": "AS923-1",
  "duty_cycle_window": 3600,
  "duty_cycle_mode": "power",
  "duty_cycle_limits": [
    {"max_eirp_dbm": 17, "limit": 100},
    {"max_eirp_dbm": 30, "limit": 10}
  ]
}
```

**No duty cycle (Singapore):**
```json
{
  "msgtype": "router_config",
  "region": "AS923-1",
  "nodc": true
}
```

**Shorter window for testing:**
```json
{
  "msgtype": "router_config",
  "region": "EU868",
  "duty_cycle_window": 60
}
```

### Feature Flag

Add `dutyconf` to the `features` field in the `version` message:

```json
{
  "msgtype": "version",
  "station": "2.1.0",
  "features": "rmtsh gps updn-dr lbtconf dutyconf"
}
```

## Implementation Details

### Phase 1: Data Structures

**File:** `src/s2e.h`

```c
// Configurable limits
enum { DC_MAX_RECORDS = 64 };  // Max TX records per band/channel per txunit
enum { DC_DEFAULT_WINDOW_US = 3600000000ULL };  // 1 hour in microseconds
enum { DC_MAX_POWER_LEVELS = 4 };  // Max power-based duty cycle tiers

// Duty cycle modes
enum {
    DC_MODE_BAND = 0,    // Per frequency band (EU868)
    DC_MODE_CHANNEL = 1, // Single limit all channels (AS923, IN865)
    DC_MODE_POWER = 2    // Power-based limits (Thailand)
};

typedef struct {
    ustime_t timestamp;
    u4_t     airtime_us;
} dc_tx_record_t;

typedef struct {
    dc_tx_record_t records[DC_MAX_RECORDS];
    u1_t head;
    u1_t count;
} dc_history_t;

// Power-based duty cycle tier
typedef struct {
    s1_t max_eirp_dbm;   // Max EIRP for this tier
    u2_t limit_permille; // Duty cycle limit (permille)
} dc_power_tier_t;

typedef struct s2txunit {
    // Band-based history (EU868) or single channel history
    dc_history_t dc_history[DC_NUM_BANDS];
    ustime_t dc_perChnl[MAX_DNCHNLS+1];
    txidx_t  head;
    tmr_t    timer;
} s2txunit_t;
```

**File:** `src/s2e.c` - Add to s2ctx_t or global:

```c
// Duty cycle configuration
static ustime_t dc_window_us = DC_DEFAULT_WINDOW_US;
static u1_t dc_mode = DC_MODE_BAND;

// Band-based limits (EU868 default)
static u2_t dc_band_limits_permille[DC_NUM_BANDS] = {
    [DC_BAND_K] = 1,    // 0.1%
    [DC_BAND_L] = 10,   // 1%
    [DC_BAND_M] = 10,   // 1%
    [DC_BAND_N] = 1,    // 0.1%
    [DC_BAND_P] = 100,  // 10%
    [DC_BAND_Q] = 10,   // 1%
};

// Channel-based limit (AS923, IN865)
static u2_t dc_channel_limit_permille = 100;  // 10% default

// Power-based limits (Thailand)
static dc_power_tier_t dc_power_tiers[DC_MAX_POWER_LEVELS] = {
    { .max_eirp_dbm = 17, .limit_permille = 100 },  // 10% at ≤+17dBm
    { .max_eirp_dbm = 30, .limit_permille = 10 },   // 1% at >+17dBm
};
static u1_t dc_power_tier_count = 2;
```

### Phase 2: Core Functions

**File:** `src/s2e.c`

```c
// Expire old records from history
static void dc_expire_old(dc_history_t* h, ustime_t window_start) {
    while (h->count > 0) {
        int idx = h->head;
        if (h->records[idx].timestamp >= window_start)
            break;
        h->head = (h->head + 1) % DC_MAX_RECORDS;
        h->count--;
    }
}

// Calculate cumulative TX time in current window
static u4_t dc_cumulative(dc_history_t* h, ustime_t window_start) {
    u4_t total = 0;
    for (int i = 0; i < h->count; i++) {
        int idx = (h->head + i) % DC_MAX_RECORDS;
        if (h->records[idx].timestamp >= window_start)
            total += h->records[idx].airtime_us;
    }
    return total;
}

// Get duty cycle limit based on mode
static u2_t dc_get_limit(txjob_t* txjob) {
    switch (dc_mode) {
        case DC_MODE_BAND:
            return dc_band_limits_permille[freq2band(txjob->freq)];
        
        case DC_MODE_CHANNEL:
            return dc_channel_limit_permille;
        
        case DC_MODE_POWER: {
            // Find tier based on TX power
            s1_t txpow_dbm = txjob->txpow / TXPOW_SCALE;
            for (int i = 0; i < dc_power_tier_count; i++) {
                if (txpow_dbm <= dc_power_tiers[i].max_eirp_dbm)
                    return dc_power_tiers[i].limit_permille;
            }
            // Default to most restrictive if above all tiers
            return dc_power_tiers[dc_power_tier_count-1].limit_permille;
        }
        
        default:
            return 100;  // 10% default
    }
}

// Get history bucket for this transmission
static dc_history_t* dc_get_history(s2ctx_t* s2ctx, txjob_t* txjob) {
    switch (dc_mode) {
        case DC_MODE_BAND:
            return &s2ctx->txunits[txjob->txunit].dc_history[freq2band(txjob->freq)];
        
        case DC_MODE_CHANNEL:
        case DC_MODE_POWER:
            // Use single bucket (index 0) for channel/power modes
            return &s2ctx->txunits[txjob->txunit].dc_history[0];
        
        default:
            return &s2ctx->txunits[txjob->txunit].dc_history[0];
    }
}

// Check if transmission is allowed (sliding window)
static int s2e_canTx_sliding(s2ctx_t* s2ctx, txjob_t* txjob, int* ccaDisabled) {
    ustime_t now = rt_getTime();
    ustime_t window_start = now - dc_window_us;
    
    dc_history_t* h = dc_get_history(s2ctx, txjob);
    u2_t limit_permille = dc_get_limit(txjob);
    
    // Expire old records
    dc_expire_old(h, window_start);
    
    // Calculate available TX time
    u4_t max_tx_us = (dc_window_us / 1000) * limit_permille;
    u4_t used_us = dc_cumulative(h, window_start);
    
    if (used_us >= max_tx_us) {
        LOG(MOD_S2E|VERBOSE, "%J %F - DC limit: used=%uus max=%uus (%.1f%%)",
            txjob, txjob->freq, used_us, max_tx_us, limit_permille/10.0);
        return 0;
    }
    
    u4_t available_us = max_tx_us - used_us;
    if (txjob->airtime <= available_us) {
        return 1;  // Can transmit
    }
    
    LOG(MOD_S2E|VERBOSE, "%J %F - DC limit: used=%uus avail=%uus need=%uus",
        txjob, txjob->freq, used_us, available_us, (u4_t)txjob->airtime);
    return 0;
}

// Record transmission
static void dc_record_tx(s2ctx_t* s2ctx, txjob_t* txjob) {
    dc_history_t* h = dc_get_history(s2ctx, txjob);
    
    if (h->count >= DC_MAX_RECORDS) {
        // Drop oldest record
        h->head = (h->head + 1) % DC_MAX_RECORDS;
        h->count--;
    }
    int idx = (h->head + h->count) % DC_MAX_RECORDS;
    h->records[idx].timestamp = txjob->txtime;
    h->records[idx].airtime_us = txjob->airtime;
    h->count++;
}
```

### Phase 3: Configuration Parsing

**File:** `src/kwlist.txt` - Add keywords:

```
duty_cycle_window
duty_cycle_mode
duty_cycle_limits
```

**File:** `src/s2e.c` - In `handle_router_config()`:

```c
case J_duty_cycle_window: {
    u4_t window_sec = uj_intRange(D, 60, 86400);  // 1 min to 24 hours
    dc_window_us = (ustime_t)window_sec * 1000000ULL;
    break;
}

case J_duty_cycle_mode: {
    str_t mode = uj_str(D);
    if (strcmp(mode, "band") == 0)
        dc_mode = DC_MODE_BAND;
    else if (strcmp(mode, "channel") == 0)
        dc_mode = DC_MODE_CHANNEL;
    else if (strcmp(mode, "power") == 0)
        dc_mode = DC_MODE_POWER;
    else
        uj_error(D, "Invalid duty_cycle_mode: %s", mode);
    break;
}

case J_duty_cycle_limits: {
    if (dc_mode == DC_MODE_BAND) {
        // Object with band names as keys
        uj_enterObject(D);
        ujcrc_t band;
        while ((band = uj_nextField(D))) {
            int limit = uj_intRange(D, 1, 1000);
            switch (band) {
                case J_K: dc_band_limits_permille[DC_BAND_K] = limit; break;
                case J_L: dc_band_limits_permille[DC_BAND_L] = limit; break;
                case J_M: dc_band_limits_permille[DC_BAND_M] = limit; break;
                case J_N: dc_band_limits_permille[DC_BAND_N] = limit; break;
                case J_P: dc_band_limits_permille[DC_BAND_P] = limit; break;
                case J_Q: dc_band_limits_permille[DC_BAND_Q] = limit; break;
            }
        }
        uj_exitObject(D);
    } else if (dc_mode == DC_MODE_CHANNEL) {
        // Single integer value
        dc_channel_limit_permille = uj_intRange(D, 1, 1000);
    } else if (dc_mode == DC_MODE_POWER) {
        // Array of {max_eirp_dbm, limit} objects
        uj_enterArray(D);
        dc_power_tier_count = 0;
        while (uj_nextSlot(D) >= 0 && dc_power_tier_count < DC_MAX_POWER_LEVELS) {
            uj_enterObject(D);
            ujcrc_t field;
            while ((field = uj_nextField(D))) {
                switch (field) {
                    case J_max_eirp_dbm:
                        dc_power_tiers[dc_power_tier_count].max_eirp_dbm = uj_intRange(D, -30, 36);
                        break;
                    case J_limit:
                        dc_power_tiers[dc_power_tier_count].limit_permille = uj_intRange(D, 1, 1000);
                        break;
                }
            }
            uj_exitObject(D);
            dc_power_tier_count++;
        }
        uj_exitArray(D);
    }
    break;
}
```

### Phase 4: Feature Flag

**File:** `src-linux/sys_linux.c`

```c
static void startupMaster2 (tmr_t* tmr) {
    // ... existing features ...
    rt_addFeature("dutyconf");  // supports configurable duty cycle
}
```

## Memory Considerations

### Current Implementation

Per txunit: `6 bands * 8 bytes = 48 bytes`

### Sliding Window Implementation

Per txunit: `6 bands * (64 records * 12 bytes + 2 bytes) = 4,620 bytes`

### Optimization Options

1. **Reduce DC_MAX_RECORDS**: 32 records = 2,316 bytes/txunit
2. **Shared history across txunits**: If antennas share bands
3. **Compact timestamp**: Store offset from window start (4 bytes instead of 8)

### Recommended: 32 records per band

- Supports 32 transmissions per band per hour before wraparound
- Typical gateway traffic is well within this limit
- Memory: ~2.3KB per txunit vs 48 bytes current

## Backward Compatibility

### Default Behavior

When `dutyconf` feature is present but no configuration provided:
- Uses **existing hardcoded band definitions** per region
- Uses **sliding window** with default 1-hour duration
- Duty cycle **enabled/disabled per region** (same as current behavior)

### Behavior Matrix

| Configuration | Behavior |
|--------------|----------|
| No duty cycle fields | Sliding window with hardcoded EU868 bands, 1-hour window |
| `duty_cycle_window` only | Uses specified window with hardcoded band limits |
| `duty_cycle_enabled: false` | Disables duty cycle enforcement |
| `nodc: true` | Disables duty cycle enforcement (legacy, equivalent) |
| `duty_cycle_mode: "channel"` | Single limit for all channels |
| `duty_cycle_mode: "power"` | Power-based limits |

### Migration Path

1. **No changes needed**: Existing deployments continue to work with hardcoded bands
2. **Automatic improvement**: Sliding window is more permissive than time-off-air
3. **Optional configuration**: LNS can customize if needed

### Feature Detection

```python
def on_station_version(msg):
    features = msg.get('features', '').split()
    if 'dutyconf' in features:
        # Station uses sliding window with configurable parameters
        # Can send: duty_cycle_enabled, duty_cycle_window, duty_cycle_mode, duty_cycle_limits
        return build_router_config_with_duty_cycle()
    else:
        # Station uses legacy time-off-air implementation
        return build_router_config_legacy()
```

## Testing Plan

### Unit Tests

1. **Window expiration**
   - Records older than window are expired
   - Cumulative calculation is correct after expiration

2. **Duty cycle enforcement**
   - TX allowed when within limit
   - TX rejected when would exceed limit
   - Edge cases: exactly at limit, just over limit

3. **Circular buffer**
   - Buffer wraparound works correctly
   - Old records dropped when full

4. **Configuration parsing**
   - Valid window values accepted
   - Invalid values rejected with appropriate errors
   - Per-band limits parsed correctly

### Integration Tests

1. **Bursty traffic**
   - Multiple rapid transmissions allowed if within limit
   - Rejected when cumulative exceeds limit

2. **Long-running test**
   - 1+ hour test verifying window slides correctly
   - Old transmissions properly expire

3. **Multi-band (EU868)**
   - Each band (K/L/M/N/P/Q) tracked independently
   - No cross-band interference
   - Transmitting in one band doesn't affect another band's budget
   - Test: Send on 10% band, 1% band, 0.1% band in sequence

4. **Multi-channel (AS923/KR920)**
   - Each channel tracked independently for per-channel DC regions
   - Transmitting on one channel doesn't affect another channel's budget
   - Test: Cycle through channels to maximize throughput

### Regression Tests

1. **Existing DC tests**
   - Behavior should be same or more permissive
   - No previously-allowed TX should be rejected

## Timeline

| Phase | Task | Estimate |
|-------|------|----------|
| 1 | Data structures | 2 hours |
| 2 | Core functions | 4 hours |
| 3 | Configuration parsing | 2 hours |
| 4 | Feature flag | 1 hour |
| 5 | Unit tests | 4 hours |
| 6 | Integration tests | 4 hours |
| 7 | Documentation | 2 hours |

## Design Decisions

1. **Window size default**: 1 hour per ETSI specification
2. **Minimum window**: 60 seconds (for testing)
3. **Maximum window**: 24 hours (practical limit)
4. **Record limit**: 32-64 per band (memory vs capacity tradeoff)
5. **Permille units**: 1/1000 for 0.1% precision without floating point

## References

- [ETSI EN 300 220-2 V3.2.1](https://www.etsi.org/deliver/etsi_en/300200_300299/30022002/03.02.01_60/en_30022002v030201p.pdf) - Short Range Devices
- [LoRaWAN Regional Parameters EU868](https://resources.lora-alliance.org/technical-specifications)
