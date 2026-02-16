# Feature Flags Reference

This document defines the feature flags advertised by the gateway in the `version` message `features` field. These flags allow the LNS to discover gateway capabilities and configure behavior accordingly.

## Version String Format

```json
{
  "msgtype": "version",
  "station": "2.1.0-mts(corecell/std)",
  "firmware": "mPower 6.0.1",
  "package": "2.1.0-mts",
  "model": "corecell",
  "protocol": 2,
  "features": "rmtsh prod gps mts gps-conf duty-conf pdu-conf lbt-conf updn-dr lbs-dp"
}
```

## Feature Flag Naming Conventions

- All lowercase
- Dashes (`-`) as word separators (no underscores)
- `-conf` suffix: LNS can configure this option via `router_config`
- `-dp` suffix: data plane protocol

## Baseline Features

| Feature | Description |
|---------|-------------|
| `rmtsh` | Remote shell support - LNS can initiate shell session over WebSocket |
| `prod` | Production build - debug options (`nocca`, `nodc`, `nodwell`) are ignored |
| `gps` | GPS hardware available |
| `mts` | MultiTech Systems fork identifier |

## LNS Configurable Options

These features indicate the gateway will honor corresponding fields in `router_config`:

| Feature | Description |
|---------|-------------|
| `gps-conf` | LNS can enable/disable GPS |
| `duty-conf` | LNS can configure duty cycle via `duty_cycle_enabled` |
| `pdu-conf` | LNS can enable raw PDU mode via `pdu_only` |
| `lbt-conf` | LNS can send explicit LBT channel configuration |
| `updn-dr` | LNS can send separate uplink/downlink DR tables (RP002-1.0.5 compliant). Implies SF5/SF6 support (SX1302/SX1303 hardware). Required for US915/AU915 regions with extended data rates. |

## Protocol Support

### Legacy

| Feature | Description |
|---------|-------------|
| `pkt-fwd` | Legacy Semtech UDP packet forwarder protocol support |

### LBS (LoRa Basic Station) Protocol

| Feature | Description |
|---------|-------------|
| `lbs-dp` | LBS protobuf data plane (uplink/downlink messages) |

Note: LBS does not have a separate control plane. Configuration is delivered via `router_config` on connect. Configuration changes require reconnect.

## Example Feature Combinations

| Use Case | Features |
|----------|----------|
| SX1301 baseline (JSON) | `rmtsh prod gps mts` |
| SX1302/SX1303 baseline (JSON) | `rmtsh prod gps mts updn-dr` |
| SX1303 with LNS config options | `rmtsh prod gps mts updn-dr gps-conf duty-conf pdu-conf lbt-conf` |
| LBS protobuf | `rmtsh prod gps mts updn-dr lbs-dp` |

## Comparison with Upstream Basic Station

Upstream Semtech Basic Station (lorabasics/basicstation) only advertises:

- `rmtsh` - if remote shell enabled
- `prod` - if production build
- `gps` - if GPS device available

All other features are MTS additions.

## Version History

- **2.1.0-mts** - Initial standardized feature flags
  - Added `mts` identifier
  - Standardized on dash separators
  - Standardized `-conf` suffix for configurable options
