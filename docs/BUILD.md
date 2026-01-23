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
