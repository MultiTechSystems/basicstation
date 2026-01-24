# Building Basic Station

## Prerequisites

### For Native Linux Build

```bash
sudo apt-get install -y build-essential
```

### For Yocto/Bitbake Build (MTCDT)

Requires a configured mts-device build environment with Yocto/OpenEmbedded.

## Building Locally (Native Linux)

### Build Variants

| Variant | Description |
|---------|-------------|
| `testsim` | Single SX1301 simulator for regression tests |
| `testms` | Multi-slave SX1301 simulator for regression tests |
| `testsim1302` | Single SX1302/SX1303 simulator for regression tests |
| `testms1302` | Multi-slave SX1302/SX1303 simulator for regression tests |

### Build Commands

```bash
# Build a specific variant
make platform=linux variant=testsim

# Build output is in build-linux-<variant>/
ls build-linux-testsim/bin/station
```

## Building for Raspberry Pi

Basic Station can be built natively on a Raspberry Pi for use with SX1301-based
concentrators (e.g., RAK2245, IMST iC880A).

### Platform Selection

| Platform | Architecture | Raspberry Pi OS |
|----------|--------------|-----------------|
| `rpi` | arm-linux-gnueabihf | 32-bit (armhf) |
| `rpi64` | aarch64-linux-gnu | 64-bit (arm64) |

To check which architecture your Raspberry Pi is running:

```bash
gcc -dumpmachine
# Returns: arm-linux-gnueabihf (32-bit) or aarch64-linux-gnu (64-bit)
```

### Build Commands

```bash
# For 64-bit Raspberry Pi OS
make platform=rpi64 variant=std

# For 32-bit Raspberry Pi OS
make platform=rpi variant=std

# Build output
ls build-rpi64-std/bin/station
```

### Clean Rebuild

If switching platforms or encountering build issues, clean the dependencies:

```bash
make super-clean
make platform=rpi64 variant=std
```

### Running

```bash
cd examples/live-s2.sm.tc
~/basicstation/build-rpi64-std/bin/station
```

Configure your station by editing `station.conf` and providing appropriate
certificates and server URIs for your LoRaWAN Network Server.

## Building for MTCDT (Yocto/Bitbake)

### Hardware Mappings

| Machine | Card Model | Chipset | Recipe |
|---------|------------|---------|--------|
| mtcdt | MTAC-003 | SX1303 | lora-basic-station-sx1303 |
| mtcdt | MTAC-LORA-1.5 | SX1301 | lora-basic-station |
| mtcap3 | - | SX1303 | lora-basic-station-sx1303 |
| mtcap | - | SX1301 | lora-basic-station |
| mtcap2 | - | SX1301 | lora-basic-station |

### Setup Build Environment

```bash
cd /path/to/mts-device
export MACHINE=mtcdt
source oe-init-build-env build
```

### Build Recipes

| Recipe | Description |
|--------|-------------|
| `lora-basic-station` | SX1301-based concentrators |
| `lora-basic-station-sx1303` | SX1302/SX1303-based concentrators |

### Build Commands

```bash
# Build SX1301 variant
bitbake lora-basic-station

# Build SX1303 variant
bitbake lora-basic-station-sx1303

# Force recompile after source changes
bitbake lora-basic-station -c compile -f
bitbake lora-basic-station
```

### Output Location

IPK packages are generated in:
```
build/tmp/deploy/ipk/mtcdt/lora-basic-station_*.ipk
build/tmp/deploy/ipk/mtcdt/lora-basic-station-sx1303_*.ipk
```

### Modifying Source Code

Source code for the recipe is located at:
```
build/tmp/work/mtcdt-mlinux-linux-gnueabi/lora-basic-station/<version>/git/
```

To apply changes:
1. Copy modified files to the git directory
2. Run `bitbake <recipe> -c compile -f` to force recompile
3. Run `bitbake <recipe>` to package

### Quick Iterative Development

For rapid development cycles, you can copy source files directly to the work directory
and rebuild without going through the full bitbake fetch/unpack cycle.

**Copy, build, and deploy in one shot:**
```bash
# Set variables (adjust for your environment)
BUILDSERVER="user@buildserver"
GATEWAY="user@gateway"
WORKDIR="/path/to/mts-device/build/tmp/work/mtcdt-mlinux-linux-gnueabi/lora-basic-station-sx1303/<version>/git"
RECIPE="lora-basic-station-sx1303"

# Copy source, compile, and deploy
scp src/*.c src/*.h src-linux/*.c src-linux/*.h $BUILDSERVER:$WORKDIR/src/ $BUILDSERVER:$WORKDIR/src-linux/ && \
ssh $BUILDSERVER "cd /path/to/mts-device && export MACHINE=mtcdt && source oe-init-build-env build && bitbake $RECIPE -c compile -f" && \
scp $BUILDSERVER:$WORKDIR/build-mlinux-sx1303/bin/station /tmp/station-test && \
scp /tmp/station-test $GATEWAY:/tmp/station && \
ssh $GATEWAY "sudo cp /tmp/station /opt/lora/station-sx1303 && sudo chmod +x /opt/lora/station-sx1303 && sudo /etc/init.d/lora-network-server restart"
```

Note: Replace paths, usernames, and server addresses with your actual values.

## Running Regression Tests

```bash
cd regr-tests

# Run all tests
./run-regression-tests --nohw

# Run with verbose output
./run-regression-tests --nohw --verbose

# Run specific variant
./run-regression-tests --nohw --variant=testsim
```

### Test Timing

| Environment | Duration | Notes |
|-------------|----------|-------|
| GitHub CI (parallel) | ~5 minutes | Full suite across all variants |
| Local (single variant) | ~15-20 minutes | All tests for one variant |

Individual test durations (testms1302 variant):

| Test | Duration | Notes |
|------|----------|-------|
| test1-selftests | ~6s | Quick sanity check |
| test2-pps | ~12s | PPS timing tests |
| test3-updn-tls | ~80s | TLS handshake overhead |
| test4-cups | ~46s | CUPS update protocol |
| test7-respawn | ~7s | Daemon restart |

For a quick smoke test, run `test1-selftests`:

```bash
cd regr-tests/test1-selftests
TEST_VARIANT=testms1302 ./test.sh
```

## Debugging on Gateway

For debugging crashes on the gateway, you can install gdb via Yocto/Bitbake.

### Building and Installing gdb

```bash
# Build gdb package
cd /path/to/mts-device
export MACHINE=mtcdt
source oe-init-build-env build
bitbake gdb

# Find the generated IPK
find build/tmp/deploy/ipk -name 'gdb*.ipk'
# Example: build/tmp/deploy/ipk/arm926ejste/gdb_9.1-r0.0_arm926ejste.ipk

# Copy to gateway and install
scp build/tmp/deploy/ipk/arm926ejste/gdb_9.1-r0.0_arm926ejste.ipk user@gateway:/tmp/
ssh user@gateway "sudo opkg install /tmp/gdb_9.1-r0.0_arm926ejste.ipk"
```

### Getting a Backtrace

```bash
# On gateway, run station under gdb
cd /var/run/lora/1
sudo gdb -batch -ex 'run' -ex 'bt' --args /opt/lora/station-sx1303 -l DEBUG

# Or with core dump
ulimit -c unlimited
sudo /opt/lora/station-sx1303 -l DEBUG
# After crash:
sudo gdb /opt/lora/station-sx1303 core -ex 'bt' -batch
```

See also: https://www.multitech.net/developer/software/mlinux/mlinux-software-development/debugging-a-cc-application/
