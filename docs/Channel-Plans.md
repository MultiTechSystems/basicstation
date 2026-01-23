# Channel Plan and Region Updates

This document describes the channel plan and region updates in Basic Station.

## Overview

Basic Station supports multiple LoRaWAN regional parameters as defined by the LoRa Alliance. This update adds support for additional regions and improves EU868 duty cycle band compliance.

## Supported Regions

### EU868 (Europe 863-870 MHz)

The EU868 region now implements proper sub-band duty cycle limits as per ETSI EN 300.220:

| Band | Frequency Range | Duty Cycle | Rate Divisor |
|------|-----------------|------------|--------------|
| K | 863-865 MHz | 0.1% | 1000 |
| L | 865-868 MHz | 1% | 100 |
| M | 868-868.6 MHz | 1% | 100 |
| N | 868.7-869.2 MHz | 0.1% | 1000 |
| P | 869.4-869.65 MHz | 10% | 10 |
| Q | 869.7-870 MHz | 1% | 100 |

Logging now shows the band letter (K-Q) instead of numeric duty cycle rates for easier debugging.

### IN865 (India 865-867 MHz)

- **Frequency Range**: 865-867 MHz
- **Max EIRP**: 30 dBm
- **Default Channels**: 865.0625, 865.4025, 865.985 MHz
- **Data Rates**: DR0-DR5 (SF12-SF7 at 125 kHz), DR6 (SF7 at 250 kHz), DR7 (FSK)

### AS923 Variants

The AS923 region is split into four sub-regions to accommodate different frequency offsets:

| Region | Frequency Offset | Default Channels |
|--------|------------------|------------------|
| AS923-1 | 0 MHz | 923.2, 923.4 MHz |
| AS923-2 | -1.8 MHz | 921.4, 921.6 MHz |
| AS923-3 | -6.6 MHz | 916.6, 916.8 MHz |
| AS923-4 | -5.9 MHz | 917.3, 917.5 MHz |

All AS923 variants:
- **Max EIRP**: 16 dBm
- **CCA Enabled**: Yes (Listen Before Talk required)
- **Duty Cycle**: 10% per channel

### IL915 (Israel 915-917 MHz)

- **Frequency Range**: 915-917 MHz
- **Max EIRP**: 14 dBm
- **Default Channels**: 915.9, 916.1, 916.3 MHz
- **Data Rates**: DR0-DR5 (SF12-SF7 at 125 kHz), DR6 (SF7 at 250 kHz), DR7 (FSK)
- **CCA Enabled**: No (no Listen Before Talk requirement)
- **Note**: IL915 uses the same frequency plan as AS923-4 but without CCA requirements

### US915 (United States 902-928 MHz)

- **Max EIRP**: Updated to 36 dBm to allow maximum power with any antenna gain
- **Note**: The radio layer subtracts antenna gain before transmission

## Configuration

Regions are configured via the `router_config` message from the LNS. The station automatically applies the correct TX power limits, duty cycle restrictions, and CCA requirements based on the region.

### Example router_config for AS923-1

```json
{
    "msgtype": "router_config",
    "region": "AS923-1",
    "max_eirp": 16.0,
    "freq_range": [915000000, 928000000],
    "DRs": [[12, 125, 0], [11, 125, 0], ...]
}
```

## Duty Cycle Management

### Per-Band Duty Cycle (EU868)

EU868 uses per-band duty cycle tracking. Each transmission updates the duty cycle timer for its respective band, blocking further transmissions until the duty cycle period expires.

### Per-Channel Duty Cycle (AS923, IN865)

AS923 and IN865 regions use per-channel duty cycle tracking with a 10% limit.

### Disabling Duty Cycle

For testing or when the LNS manages duty cycle externally, duty cycle limits can be disabled:

```json
{
    "router_config": {
        "nodc": true
    }
}
```

When disabled, the station logs: "DC limits disabled, transmissions regulated by the LNS"

## Fine Timestamp Handling

For SX1303 gateways receiving frames on multiple modems simultaneously, fine timestamps from mirror frames are now preserved. If a higher-quality frame is received without a fine timestamp, the timestamp from the mirror frame is copied before dropping the duplicate.

## Legacy Region Names

For backward compatibility, the following legacy region names are supported:

| Legacy Name | Maps To |
|-------------|---------|
| AS923 | AS923-1 |
| AS923JP | AS923-1 |
| US902 | US915 |

## CCA/LBT Implementation

Clear Channel Assessment (CCA) / Listen Before Talk (LBT) is supported for both SX1301 and SX1302/SX1303 concentrators.

### SX1301 LBT Configuration

For SX1301, LBT is configured using the built-in FPGA-based spectrum scanning:
- **RSSI Target**: -80 dBm
- **Scan Time**: 5000 µs per channel

### SX1302/SX1303 LBT Configuration

For SX1302/SX1303, LBT uses the SX1261 radio for spectrum scanning:
- **RSSI Target**: -80 dBm
- **Scan Time**: 5000 µs per channel
- **TX Dwell Time**: 4000 ms maximum

### Regions Requiring CCA

| Region | CCA Required |
|--------|--------------|
| AS923-1 | Yes |
| AS923-2 | Yes |
| AS923-3 | Yes |
| AS923-4 | Yes |
| KR920 | Yes |
| IL915 | No |
| Other regions | No |

## Testing

Region support can be tested using the regression tests:

```bash
cd regr-tests
# Test all region variants
./run-regression-tests -T test6-regions

# Test AS923 variants and IL915 with CCA verification
./run-regression-tests -T test6m-as923-variants
```

### test6m-as923-variants

This test verifies:
1. All AS923 variants (AS923-1, AS923-2, AS923-3, AS923-4) are correctly recognized
2. IL915 is correctly recognized
3. CCA/LBT is enabled for AS923 variants and blocks transmissions on busy channels
4. CCA/LBT is disabled for IL915 (verified via configuration logs)
