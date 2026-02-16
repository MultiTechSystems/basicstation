# GPS/PPS Recovery for SX1302/SX1303

This document describes the GPS/PPS recovery feature for SX1302/SX1303 gateways.

## Overview

This feature improves timing reliability by detecting and recovering from GPS/PPS synchronization issues on SX1302/SX1303 hardware. It also provides LNS control over GPS functionality via the `gps_enable` field in `router_config`.

## Features

### 1. GPS Control via LNS (`gps-conf`)

The LNS can enable or disable GPS processing via the `gps_enable` field in `router_config`:

```json
{
  "msgtype": "router_config",
  "gps_enable": false,
  ...
}
```

**Feature Flag:** `gps-conf` - Indicates station supports LNS-controlled GPS enable/disable.

**Use Cases:**
- Disable GPS when hardware issues are detected
- Reduce power consumption when GPS is not needed
- Troubleshoot timing issues by isolating GPS from PPS

**Behavior:**
- When disabled: GPS device connection is stopped, no NMEA parsing
- PPS processing continues based on HAL availability (independent of GPS)
- Station logs: `"GPS disabled by LNS via router_config"`

### 2. Session Change Detection (Slave Restart)

When a slave process restarts (session ID changes), the station detects this and resets timing state:

- Detects session change via `ral_xtime2sess()` comparison
- Resets drift statistics for affected txunit
- For primary slave (txunit 0): resets PPS/GPS sync state entirely
- Logs: `"Primary slave restarted - PPS/GPS sync reset, will re-acquire"`

This prevents timing errors caused by comparing xtimes from different sessions.

### 3. PPS Reset Recovery (SX1302/SX1303 only)

When the PPS (Pulse Per Second) signal is lost for an extended period, the station will attempt to recover by resetting the GPS synchronization:

- **Detection**: If PPS is lost for more than 90 seconds (`NO_PPS_RESET_THRES`)
- **Recovery**: Reset GPS synchronization by calling `sx1302_gps_enable(false)` then `sx1302_gps_enable(true)`
- **Retry**: Attempt reset every 5 seconds until recovery
- **Failsafe**: Force restart if GPS cannot recover after 6 reset attempts (`NO_PPS_RESET_FAIL_THRES`)

### 2. Excessive Clock Drift Detection

When the clock drift between MCU and SX130X cannot stabilize:

- **Detection**: Track consecutive excessive drift measurements
- **Tolerance**: Allow up to 2 × QUICK_RETRIES (6) attempts before increasing threshold
- **Failsafe**: Force restart after 5 × QUICK_RETRIES (15) consecutive failures

## Configuration

The following thresholds are defined in `src/timesync.c`:

| Define | Value | Description |
|--------|-------|-------------|
| `NO_PPS_RESET_THRES` | 90 | Seconds without PPS before attempting reset |
| `NO_PPS_RESET_FAIL_THRES` | 6 | Maximum reset attempts before restart |
| `QUICK_RETRIES` | 3 | Base retry count for drift detection |

## Compatibility

- **Hardware**: SX1302/SX1303 gateways only (guarded by `CFG_sx1302` or `CFG_gps_recovery`)
- **HAL**: Compatible with lora-net/sx1302_hal (uses `sx1302_gps_enable()` function)
- **Simulation**: testsim1302/testms1302 variants use `CFG_gps_recovery` with a mock
- **SX1301**: No changes - existing behavior preserved

## Use Cases

This feature is particularly useful in environments where:

1. GPS signal may be temporarily obstructed
2. GPS antenna connections are intermittent
3. The gateway operates in conditions with variable GPS reception
4. Long-running deployments where GPS synchronization may drift

## Behavior

### Normal Operation
- PPS pulses are tracked and used for precise timing
- Clock drift is monitored and compensated

### PPS Loss Detection
```
[SYN:XDEBUG] PPS: Rejecting PPS (xtime/pps_xtime spread): ...
```

### GPS Reset Attempt (SX1302/SX1303)
When PPS is lost for >90 seconds, the station attempts to reset GPS synchronization.

### Recovery Failure
```
[SYN:CRITICAL] XTIME/PPS out-of-sync need restart, forcing reset
```
Station exits to allow external process manager to restart.

### Excessive Drift Failure
```
[SYN:CRITICAL] Clock drift could not recover, forcing reset
```
Station exits after 15 consecutive drift failures.

## Implementation Details

### Source Files

- `src/timesync.c` - PPS recovery, session detection, drift monitoring
- `src/s2e.c` - `gps_enable` field parsing from router_config
- `src-linux/sys_linux.c` - GPS device control, `gps-conf` feature flag

### Key Changes

1. Added `loragw_sx1302.h` include for `sx1302_gps_enable()`
2. Added session change detection via `ral_xtime2sess()` comparison
3. Added static variables to track reset state
4. Added PPS reset logic in the PPS rejection path
5. Added excessive drift exit after threshold exceeded
6. Added `gps_enable` field parsing in `handle_router_config()`
7. Added `sys_setGPSEnabled()` for LNS GPS control

### router_config Fields

| Field | Type | Description |
|-------|------|-------------|
| `gps_enable` | boolean | Enable/disable GPS processing (default: current state) |
