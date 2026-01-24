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

## Building for MTCDT (Yocto/Bitbake)

### Hardware Mappings

| Machine | Card Model | Chipset | Recipe |
|---------|------------|---------|--------|
| mtcdt | MTAC-003 | SX1303 | lora-basic-station-sx1303 |
| mtcdt | MTAC-LORA-1.5 | SX1301 | lora-basic-station |
| mtcap3 | - | SX1303 | lora-basic-station-sx1303 |
| mtcap | - | SX1301 | lora-basic-station |
| mtcap2 | - | SX1301 | lora-basic-station |

**Note:** The v2 gateway (lgw2/SX1301AR API) is no longer supported or built by MultiTech.
The SX1303 (MTAC-003) replaced the geolocation feature that the v2 gateway provided.
The `sx1301v2conf.c` code path remains in the codebase but is not actively maintained.

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

### Quick Debug Workflow (Preferred for Development)

For faster iteration during debugging, copy the binary directly from the work directory
instead of generating a full IPK package:

```bash
# 1. Copy modified source to the work directory
scp src/sx130xconf.c user@buildserver:~/mts-device/build/tmp/work/mtcdt-mlinux-linux-gnueabi/lora-basic-station-sx1303/<version>/git/src/

# 2. Force recompile (skip packaging)
ssh user@buildserver "cd ~/mts-device && export MACHINE=mtcdt && source oe-init-build-env build && bitbake lora-basic-station-sx1303 -c compile -f"

# 3. Copy binary directly to gateway (skip IPK)
scp user@buildserver:~/mts-device/build/tmp/work/mtcdt-mlinux-linux-gnueabi/lora-basic-station-sx1303/<version>/git/build-mlinux-sx1303/bin/station /tmp/station
scp /tmp/station admin@<gateway-ip>:/home/admin/

# 4. Install and restart on gateway
ssh admin@<gateway-ip> "echo '<password>' | sudo -S cp /home/admin/station /opt/lora/station-sx1303 && echo '<password>' | sudo -S /etc/init.d/lora-network-server restart"
```

**Note:** The binary name in `/opt/lora/` depends on the chipset:
- SX1301: `station`
- SX1303: `station-sx1303`

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
