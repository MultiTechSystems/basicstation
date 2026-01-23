# GPS/PPS Recovery for SX1302/SX1303

This document describes the GPS/PPS recovery feature for SX1302/SX1303 gateways.

## Overview

This feature improves timing reliability by detecting and recovering from GPS/PPS synchronization issues on SX1302/SX1303 hardware.

## Features

### 1. PPS Reset Recovery (SX1302/SX1303 only)

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

The changes are in `src/timesync.c`:

1. Added `loragw_sx1302.h` include for `sx1302_gps_enable()`
2. Added static variables to track reset state
3. Added PPS reset logic in the PPS rejection path
4. Added excessive drift exit after threshold exceeded
