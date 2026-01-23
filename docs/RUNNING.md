# Running Basic Station

## Installation on MTCDT Gateway

### Copy IPK to Gateway

```bash
scp lora-basic-station_*.ipk user@gateway:/tmp/
```

### Install Package

```bash
ssh user@gateway
sudo opkg install --force-reinstall /tmp/lora-basic-station_*.ipk
```

## Runtime Directories

Basic Station uses the following runtime directory structure:

```
/var/run/lora/
├── 1/                    # First concentrator instance
│   ├── station           # Station binary (symlink or copy)
│   ├── station.conf      # Configuration file
│   └── tc.uri            # LNS connection URI
├── 2/                    # Second concentrator instance (16-channel mode)
│   ├── station
│   ├── station.conf
│   └── tc.uri
└── lora-pkt-fwd-1.pid    # PID file
```

### Multi-Slave (16-Channel) Mode

When running with two concentrator cards:
- Directory `1/` contains master process and first slave (slave#0)
- Directory `2/` contains second slave (slave#1)
- Master coordinates both slaves via IPC

## Service Management

### Start/Stop/Restart

```bash
# Using init.d script
sudo /etc/init.d/lora-network-server start
sudo /etc/init.d/lora-network-server stop
sudo /etc/init.d/lora-network-server restart
```

### Enable/Disable Service

Edit `/etc/default/lora-basic-station`:
```
ENABLED=yes    # or "no" to disable
```

## Configuration Files

### station.conf

Main configuration file containing:
- `SX1301_conf` or `SX130x_conf`: Concentrator hardware settings
- Radio frequencies, gains, and channel mappings
- PPS/GPS settings

Example:
```json
{
  "SX1301_conf": {
    "lorawan_public": true,
    "clksrc": 0,
    "pps": true,
    "device": "/dev/spidev0.0",
    "radio_0": {"enable": true, "freq": 923600000, "type": "SX1257"},
    "radio_1": {"enable": true, "freq": 922600000, "type": "SX1257"}
  }
}
```

### tc.uri

LNS connection URI:
```
wss://lns.example.com:443
```

## Log Files

Station logs are written to:
```
/var/log/lora-station.log
```

### Viewing Logs

```bash
# Follow log in real-time
tail -F /var/log/lora-station.log

# Filter by component
grep '\[SYN:' /var/log/lora-station.log   # Time sync messages
grep '\[RAL:' /var/log/lora-station.log   # Radio abstraction layer
grep '\[S00:' /var/log/lora-station.log   # Slave 0 messages
grep '\[S01:' /var/log/lora-station.log   # Slave 1 messages
```

### Log Prefixes

| Prefix | Description |
|--------|-------------|
| `[SYS:...]` | System/startup messages |
| `[RAL:...]` | Radio abstraction layer |
| `[SYN:...]` | Time synchronization |
| `[AIO:...]` | Async I/O / network |
| `[TC:...]` | Traffic controller (LNS connection) |
| `[S00:...]` | Slave 0 (primary concentrator) |
| `[S01:...]` | Slave 1 (secondary concentrator) |

## Troubleshooting

### Station Keeps Restarting

Check for:
1. Invalid tc.uri (LNS unreachable)
2. Missing or invalid certificates
3. Hardware communication errors (SPI)

### PPS/GPS Issues

For SX1301 in multi-slave mode:
- Only slave#0 can have PPS enabled
- Use gpsd for shared GPS access

For SX1302/SX1303:
- Each slave can have independent PPS

### Clock Drift Errors

```
[SYN:WARN] Repeated excessive clock drifts...
```

This indicates time synchronization issues. Check:
1. GPS/PPS configuration
2. Concentrator hardware health
3. System load affecting timing
