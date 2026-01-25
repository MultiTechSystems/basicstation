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

**Important Notes:**
- Do NOT use `bitbake -c clean` as it removes the source directory with your changes
- To force a full recompile, remove object files: `rm -f $WORKDIR/build-mlinux-sx1303/s2core/*.o`
  - Note: Use `rm -f` not `rm -rf` to avoid shell glob issues over SSH
- If changing `.proto` files, regenerate the protobuf C files locally first (see Protobuf section below)
- The gateway requires `sudo` for deployment; use `echo 'password' | sudo -S` for non-interactive sudo

**Verifying Object Files Were Rebuilt:**

**IMPORTANT:** `bitbake -c compile -f` does NOT always trigger actual recompilation even when source files have changed. The more reliable approach is to:

1. Remove the specific object files you changed
2. Source the `run.do_compile` script directly to invoke make

```bash
# More reliable rebuild method:
cd $WORKDIR/build-mlinux-sx1303/s2core
rm -f ral_lgw.o sx130xconf.o ../lib/libs2core.a ../bin/station
source $MTS_DEVICE/build/tmp/work/mtcdt-mlinux-linux-gnueabi/$RECIPE/$VERSION/temp/run.do_compile
```

Always verify timestamps:

```bash
# Check object file timestamps (should match current time after build)
ls -la $WORKDIR/build-mlinux-sx1303/s2core/ral_lgw.o
ls -la $WORKDIR/build-mlinux-sx1303/s2core/sx130xconf.o

# If timestamps are old, force removal and rebuild:
ssh $BUILDSERVER "rm -f $WORKDIR/build-mlinux-sx1303/s2core/*.o"
ssh $BUILDSERVER "cd $MTS_DEVICE && source oe-init-build-env build && bitbake $RECIPE -c compile -f"

# Verify new binary contains your changes
strings $WORKDIR/build-mlinux-sx1303/bin/station | grep 'your_search_string'
```

**Automated Build Script:**

Use the `build-deploy.sh` script in the repository root for automated build/deploy:

```bash
./build-deploy.sh              # Build and deploy
./build-deploy.sh --build      # Build only
./build-deploy.sh --deploy     # Deploy only (use last build)
./build-deploy.sh --clean      # Clean objects before build
./build-deploy.sh --restart    # Just restart station on gateway
```

The script automatically verifies object files were updated after compilation.

**Example: MTCDT SX1303 Development**
```bash
# Configuration (adjust for your environment)
BUILDSERVER="jreiss@buildslavemtcdt3dm2"
GATEWAY_IP="10.10.200.140"
GATEWAY_USER="admin"
GATEWAY_PASS="admin2019!"
MTS_DEVICE="/home/jreiss/mts-device"
VERSION="2.0.6-27-r5"  # Check: ls $MTS_DEVICE/build/tmp/work/mtcdt-mlinux-linux-gnueabi/lora-basic-station-sx1303/
WORKDIR="$MTS_DEVICE/build/tmp/work/mtcdt-mlinux-linux-gnueabi/lora-basic-station-sx1303/$VERSION/git"
RECIPE="lora-basic-station-sx1303"

# Step 1: Copy source files to build server
scp src/*.c src/*.h src-linux/*.c src-linux/*.h $BUILDSERVER:$WORKDIR/src/

# Step 2: Clean objects (optional - needed if headers changed)
ssh $BUILDSERVER "rm -f $WORKDIR/build-mlinux-sx1303/s2core/*.o"

# Step 3: Compile
ssh $BUILDSERVER "cd $MTS_DEVICE && export MACHINE=mtcdt && source oe-init-build-env build && bitbake $RECIPE -c compile -f"

# Step 4: Copy binary from build server
scp $BUILDSERVER:$WORKDIR/build-mlinux-sx1303/bin/station /tmp/station-test

# Step 5: Deploy to gateway
sshpass -p '$GATEWAY_PASS' scp /tmp/station-test $GATEWAY_USER@$GATEWAY_IP:/tmp/station
sshpass -p '$GATEWAY_PASS' ssh $GATEWAY_USER@$GATEWAY_IP "echo '$GATEWAY_PASS' | sudo -S cp /tmp/station /opt/lora/station-sx1303 && echo '$GATEWAY_PASS' | sudo -S chmod +x /opt/lora/station-sx1303 && echo '$GATEWAY_PASS' | sudo -S /etc/init.d/lora-network-server restart"
```

**One-liner version (copy-paste friendly):**
```bash
WORKDIR="/home/jreiss/mts-device/build/tmp/work/mtcdt-mlinux-linux-gnueabi/lora-basic-station-sx1303/2.0.6-27-r5/git" && \
scp src/*.c src/*.h jreiss@buildslavemtcdt3dm2:$WORKDIR/src/ && \
ssh jreiss@buildslavemtcdt3dm2 "rm -f $WORKDIR/build-mlinux-sx1303/s2core/*.o && cd /home/jreiss/mts-device && export MACHINE=mtcdt && source oe-init-build-env build && bitbake lora-basic-station-sx1303 -c compile -f" && \
scp jreiss@buildslavemtcdt3dm2:$WORKDIR/build-mlinux-sx1303/bin/station /tmp/station-test && \
sshpass -p 'admin2019!' scp /tmp/station-test admin@10.10.200.140:/tmp/station && \
sshpass -p 'admin2019!' ssh admin@10.10.200.140 "echo 'admin2019!' | sudo -S cp /tmp/station /opt/lora/station-sx1303 && echo 'admin2019!' | sudo -S /etc/init.d/lora-network-server restart"
```

### Regenerating Protobuf Files

If you modify `src/tc.proto`, you must regenerate `tc.pb.c` and `tc.pb.h`:

```bash
# Activate Python environment with protobuf support
source pyenv/bin/activate

# Prepare nanopb (first time only)
cd deps/nanopb && bash prep.sh && cd ../..

# Generate protobuf C files
cd src
python3 ../deps/nanopb/git-repo/generator/nanopb_generator.py -I . -D . tc.proto
cd ..

# Now copy both .proto and generated files to build server
scp src/tc.proto src/tc.pb.c src/tc.pb.h $BUILDSERVER:$WORKDIR/src/
```

**Troubleshooting Protobuf Changes:**
- If you add `optional` fields, ensure nanopb >= 0.4.5 (check with `grep PB_PROTO_HEADER_VERSION tc.pb.h`)
- Proto3 `optional` generates `has_fieldname` boolean fields
- Always regenerate and copy both `tc.pb.c` and `tc.pb.h` together
- Clean object files after protobuf changes: `rm -rf $WORKDIR/build-mlinux-sx1303/s2core/*.o`

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

## Debugging Methodology: Tests First

**Rule: Write tests to find bugs rather than searching through code.**

When debugging issues, follow this approach:

1. **Hypothesis from symptoms** - Form a hypothesis about what's failing
2. **Write a minimal test** - Create a selftest that exercises that code path
3. **Test proves/disproves** - If the test fails as expected, you've found the bug
4. **Fix verified by test** - The same test validates the fix

### Example: Writing a Bug-Finding Test

```bash
# 1. Create test file (see src/selftest_s2e.c for example)
vi src/selftest_mytest.c

# 2. Add to selftests.h
extern void selftest_mytest();

# 3. Add to selftests.c array
selftest_mytest,

# 4. Build and run
make platform=linux variant=testsim
cd regr-tests/test1-selftests
STATION_SELFTESTS=1 ../../build-linux-testsim/bin/station -p 2>&1 | grep -i mytest
```

### Quick Selftest Run

```bash
cd regr-tests/test1-selftests
STATION_SELFTESTS=1 ../../build-linux-testsim/bin/station -p
```

This runs all selftests including any new ones you've added. The output shows
`ALL N SELFTESTS PASSED` on success.

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
