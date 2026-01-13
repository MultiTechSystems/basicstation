# Example Station Configuration Files

These are example `station.conf` files for MultiTech gateways with SX1303/SX1250 hardware.

## File Naming Convention

- `mtcap3-station.conf.XXX` - For MTCAP3 (Conduit AP3) gateways
- `mtcdt-station.conf.XXX` - For MTCDT (Conduit) gateways with SX1303 card

Region codes:
- `A00` - AU915 (Australia 915MHz)
- `E00` - EU868 (Europe 868MHz)
- `U00` - US915 (North America 915MHz)

## Hardware Configuration

These configs are for SX1303 concentrators with SX1250 radios:
- `"type": "SX1250"` for radio configuration
- Supports SF5 and SF6 spreading factors (RP2 1.0.5)
- TX power tables calibrated for each hardware variant

## Source

Original files from:
https://github.com/MultiTechSystems/multitech-gateway-tx-power-tables

## Usage

Copy the appropriate file to your station's working directory as `station.conf`
or reference it via `"radio_conf": "path/to/config.conf"` in your main config.
