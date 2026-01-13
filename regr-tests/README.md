# Basic Station Regression Tests

This directory contains the regression test suite for Basic Station.

## Quick Start

```bash
# Run all tests
./run-regression-tests

# Run with verbose output
./run-regression-tests -v

# Run specific test
./run-regression-tests --tests="test3-updn-tls"

# Force rebuild before testing
./run-regression-tests -b

# Clean run (remove previous test logs)
./run-regression-tests -c
```

## Test Variants

Tests are run against multiple build variants:

| Variant | Description |
|---------|-------------|
| `testsim` | Simulated SX1301 gateway (libloragw in master process) |
| `testsim1302` | Simulated SX1302/SX1303 with SF5/SF6 support |
| `testms` | Master/slave model simulation |

### Building Variants

```bash
# Build testsim variant
make platform=linux variant=testsim

# Build testsim1302 variant (SF5/SF6 support)
make platform=linux variant=testsim1302

# Build testms variant
make platform=linux variant=testms
```

## Test Structure

Each test is in a directory named `test<N>-<name>/` containing:

| File | Purpose |
|------|---------|
| `test.sh` | Main test script (shell-based tests) |
| `test.py` | Main test script (Python-based tests) |
| `makefile` | Build integration (typically includes `testlib.mk`) |
| `station.conf` | Station configuration for the test |
| `slave-0.conf` | Radio/HAL configuration |
| `.gitignore` | Files to clean up after test |

## Available Tests

### Core Tests

| Test | Description |
|------|-------------|
| `test1-selftests` | Built-in self-tests |
| `test2-fs` | File system operations |
| `test2-gps` | GPS functionality |
| `test2-pps` | PPS (Pulse Per Second) timing |

### Uplink/Downlink Tests

| Test | Description |
|------|-------------|
| `test3-updn-tls` | Uplink/downlink with TLS |
| `test3a-updn-tls` | Additional TLS tests |
| `test3b-dnC` | Class C downlink |
| `test3b-dnC_2ant` | Class C downlink with 2 antennas |
| `test3b-rx2_2ant` | RX2 window with 2 antennas |
| `test3c-cca` | Clear Channel Assessment |
| `test3d-bcns` | Beacon tests |

### Protocol Tests

| Test | Description |
|------|-------------|
| `test4-cups` | CUPS (Configuration and Update Server) |
| `test5-rmtsh` | Remote shell |
| `test5-runcmd` | Remote command execution |

### RP2 1.0.5 Tests

| Test | Description | Variant |
|------|-------------|---------|
| `test6-asym-drs` | Asymmetric DR support (US915/AU915) | testsim |
| `test6a-sf5sf6-hw` | SF5/SF6 spreading factors | testsim1302 only |

### Other Tests

| Test | Description |
|------|-------------|
| `test7-respawn` | Station respawn behavior |
| `test8-web` | Web interface |

## Test Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TEST_VARIANT` | Build variant to test | `testsim` |
| `IGNORE` | Regex pattern for tests to skip | `livecups` |
| `BUILD_DIR` | Build directory path | Auto-detected |

## Writing Tests

### Shell-based Test

```bash
#!/bin/bash
. ../testlib.sh

# Your test logic here
station -p --temp . &
sleep 2

# Verify something
if grep "expected" station.log; then
    banner "Test passed"
else
    banner "Test FAILED"
    exit 1
fi

collect_gcda
```

### Python-based Test

```python
import asyncio
import tcutils as tu
import simutils as su

class TestMuxs(tu.Muxs):
    async def handle_updf(self, ws, msg):
        # Handle uplink
        pass

async def test_start():
    muxs = TestMuxs()
    await muxs.start_server()
    # Start station...

asyncio.ensure_future(test_start())
asyncio.get_event_loop().run_forever()
```

### Variant-Specific Tests

To run a test only with specific variants:

```bash
#!/bin/bash

# Skip if not the required variant
if [[ "$TEST_VARIANT" != "testsim1302" ]]; then
    echo "Skipping test - requires testsim1302 variant"
    exit 0
fi

. ../testlib.sh
# ... rest of test
```

## Test Utilities

### Python Modules

Located in `../pysys/`:

| Module | Purpose |
|--------|---------|
| `tcutils.py` | TC (Traffic Controller) server utilities, router configs |
| `simutils.py` | LGW simulator utilities |
| `testutils.py` | Common test helpers |

### Router Configurations

Available in `tcutils.py`:

| Config | Description |
|--------|-------------|
| `router_config_EU863` | EU868 8-channel |
| `router_config_US902_8ch` | US915 8-channel (legacy) |
| `router_config_US902_8ch_RP2` | US915 8-channel RP2 1.0.5 (SX1302) |
| `router_config_US902_8ch_RP2_sx1301` | US915 8-channel RP2 1.0.5 (SX1301 sim) |
| `router_config_AU915_8ch_RP2` | AU915 8-channel RP2 1.0.5 |

## Example Configurations

The `example-configs/` directory contains real-world station.conf files:

| File | Gateway | Region | Hardware |
|------|---------|--------|----------|
| `mtcap3-station.conf.A00` | MTCAP3 | AU915 | SX1303/SX1250 |
| `mtcap3-station.conf.E00` | MTCAP3 | EU868 | SX1303/SX1250 |
| `mtcap3-station.conf.U00` | MTCAP3 | US915 | SX1303/SX1250 |
| `mtcdt-station.conf.A00` | MTCDT | AU915 | SX1303/SX1250 |
| `mtcdt-station.conf.E00` | MTCDT | EU868 | SX1303/SX1250 |
| `mtcdt-station.conf.U00` | MTCDT | US915 | SX1303/SX1250 |

Source: [MultiTechSystems/multitech-gateway-tx-power-tables](https://github.com/MultiTechSystems/multitech-gateway-tx-power-tables)

## PKI Data

The `pki-data/` directory contains test certificates and keys for TLS testing.
**These are for testing only - do not use in production.**

## Coverage Collection

Tests automatically collect code coverage data using `lcov`. Coverage files
(`.info`) are saved in each test directory after running.

To generate a coverage report:

```bash
# After running tests
lcov -a test1-selftests/testsim.info -a test3-updn-tls/testsim.info -o combined.info
genhtml combined.info -o coverage-report
```

## Troubleshooting

### Test Timeout

Default timeout is 120 seconds. Increase with:

```bash
timeout=300 ./test.sh
```

### Viewing Failed Test Logs

```bash
cat t.log/fail-test3-updn-tls__testsim.log
```

### Keeping Test Files

To preserve generated files for debugging:

```bash
cd test3-updn-tls
./test.sh --keep
```

## CI Integration

For GitHub Actions, use the `--ghactions` flag:

```bash
./run-regression-tests -g -n
```

This enables:
- Grouped output sections
- Skipping hardware-dependent tests (`-n`)
