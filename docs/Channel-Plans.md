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

## Testing

Region support can be tested using the `test6-regions` regression test:

```bash
cd regr-tests
./run-regression-tests -T test6-regions
```

This test verifies that the station accepts router_config for each supported region and configures the correct parameters.
