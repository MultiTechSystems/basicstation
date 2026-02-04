# Development Notes

## TODO

### Version Info in MUXS Messages (IMPLEMENTED)
The `firmware` and `package` fields in the MUXS version message are now populated:

**Station-side changes (committed):**
- `sys_firmware()`: Reads from `/etc/mlinux-version` (mLinux) or `/etc/issue` (fallback)
- `sys_package()`: Uses `CFG_package_version` if defined at compile time, else falls back to `version.txt`
- `tc.c`: Updated to use `sys_firmware()` and `sys_package()`
- Startup log and `-v` output updated to show both values

**Bitbake recipe change needed:**
Add to the recipe's `EXTRA_OEMAKE` to inject the package version at compile time:
```bitbake
EXTRA_OEMAKE += 'CFG_package_version=\"${PV}\"'
```

This will define `CFG_package_version` as a string macro (e.g., `"2.0.6-27"`) that `sys_package()` returns.

**Expected output after recipe update:**
```json
{"msgtype":"version","station":"2.1.0(mlinux/sx1303)","firmware":"mLinux 6.0.2","package":"2.0.6-27",...}
```

### Fine Timestamp Support (CLARIFIED)
GitHub issue #177 was caused by incorrectly combining `fts` with `rxtime`. The original
implementation tried to add fine timestamp nanoseconds to the rxtime field, but this is
wrong because:
- `rxtime`: GPS-synced timestamp of packet arrival (microsecond precision)
- `fts`: Separate 32-bit counter for a specific point in packet reception (for TDoA)

These measure different events and cannot be combined. The correct approach (now implemented):
- `fts` is sent as a **separate field** in uplink messages
- `rxtime` remains the consistent GPS-synced timestamp
- LNS uses `fts` independently for TDoA geolocation when available

**Status:** `fts` field is populated in both `ral_lgw.c` (single-concentrator) and
`ral_slave.c` (master/slave mode) for SX1302/SX1303 when `ftime_received` is set by HAL.

## Completed Today (2026-01-23)

- Added `rpi64` platform support for 64-bit Raspberry Pi OS (aarch64)
- Added `v5.0.1-rpi64.patch` for the SX1301 HAL
- Updated `docs/BUILD.md` with Raspberry Pi build instructions
- Cherry-picked all changes to feature branches and pushed to origin

## Potential Future Work

### rpi64 Platform
- Consider adding `CFLAGS.rpi64.std` optimization flags if needed (currently inherits defaults)
- Test with SX1302/SX1303 concentrators (would need `rpi64` entries in `lgw1302` deps)

### Build System
- The `deps.clean` target doesn't exist - could add for convenience
- No `rpi64` variant for corecell/SX1302 builds yet (CFG.rpi64 only has `lgw1` not `sx1302`)

### Bitbake Recipe Update for Protobuf Support (COMPLETED)
The bitbake recipe has been updated to support the new protobuf-based TC protocol.

**Changes made to recipe:**
1. Updated `SRCREV_station` to `f14ee079e1d8a19cb060859b760dc15bfe6fc659` (2.1.x with protobuf)
2. Embedded nanopb source files directly in recipe:
   - Added `pb.h`, `pb_common.c`, `pb_common.h`, `pb_decode.c`, `pb_decode.h`, `pb_encode.c`, `pb_encode.h` to SRC_URI
   - Modified `do_compile()` to copy nanopb files to `${S}/src/nanopb/` (included in VPATH automatically)
3. Updated `setup.gmk` to include `-I${TD}/src/nanopb` in INCS.mlinux

**Recipe location:** `mts-device/layers/meta-mts-device/recipes-connectivity/lora/lora-basic-station-sx1303_2.0.6-27.bb`

**Files in recipe directory:**
- `setup.gmk` - minimal mlinux-specific setup with nanopb include path
- `pb.h`, `pb_*.c`, `pb_*.h` - nanopb library sources (from nanopb 0.4.9.1)

**Build command:**
```bash
cd /path/to/mts-device
export MACHINE=mtcdt
source oe-init-build-env build
bitbake lora-basic-station-sx1303
```

**Note:** The existing `nanopb` recipe in `meta-openembedded` is blacklisted ("Needs forward porting to use python3"), so embedding the source files directly was the simplest solution.

### GPS Position Reporting via gps-ctrl
The LNS can request the gateway to send its GPS coordinates periodically. This would enable:
- Automatic gateway location registration for TDoA geolocation
- Detection of mobile gateways
- Verification of gateway placement

**Implementation:**
1. Add `gps_report_interval` field to router_config (seconds, 0=disabled)
2. When enabled, station sends periodic GPS position updates to LNS
3. Message format (JSON): `{"msgtype":"gpspos", "lat":N, "lon":E, "alt":M, "time":T}`
4. Update `tc-server.py` to handle `gpspos` messages and auto-register with TDoA locator

**Files to modify:**
- `src/s2e.c` - add GPS reporting timer and message encoding
- `src/tc.c` - parse `gps_report_interval` from router_config
- `regr-tests/feature-tests/tc-server.py` - handle incoming `gpspos` messages

### Debugging Methodology: Tests First, Not Code Archaeology

**Rule: Write tests to find bugs rather than searching through code.**

When debugging:
1. **Hypothesis from symptoms** - Form a hypothesis about what's failing based on observable behavior
2. **Write a minimal test** that exercises that specific code path
3. **Test proves/disproves the hypothesis** - If the test fails as expected, you've found the bug
4. **Fix is verified by the test** - The same test validates the fix and prevents regression

**Example: Asymmetric DR Bug (2026-01-25)**

Symptoms: Station failed with `--asym-dr` flag (4294 MHz frequencies, RF disabled), worked without it.

Instead of grepping through `s2e.c`, `ral.c`, `sx130xconf.c` etc., the correct approach:
1. Write `selftest_s2e.c` that initializes both symmetric and asymmetric DR configurations
2. Test `any125kHz()` behavior with both configurations
3. Test immediately showed: symmetric DRs return `true`, asymmetric DRs return `false`
4. Root cause identified: `any125kHz()` used `s2e_dr2rps()` which only checks `dr_defs[]`, not `dr_defs_up[]`

Benefits:
- Faster than manual code review
- More reliable - tests don't miss edge cases
- Leaves regression test for future changes
- Documents the bug and its fix

See `src/selftest_s2e.c` for the test implementation.

### Code Quality
- `src-linux/gps.c:342` has a misleading indentation warning (while loop / LOG macro)

### Documentation
- Could add troubleshooting section for common Raspberry Pi issues (SPI permissions, GPIO reset pin configuration)
- Could document environment variables like `LORAGW_SPI` and `LORAGW_SPI_SPEED` from the HAL patch

### LBT Enhancements (from sx130xconf.c)
- Full SX1261 LBT support for SX1302/SX1303 (currently stubbed)
- AS923-2/3/4 regional LBT parameters
- LNS-provided LBT channel configuration via router_config
- LNS-provided RSSI target override

### Protobuf Protocol Enhancements
- Add `runcmd` response message (currently one-way)
- Add `rmtsh` session management improvements
- Consider adding compression on top of protobuf for further savings
- Auto-generated Python protobuf (`tc_pb2.py`) for tc-server.py is working - consider packaging

### TC Server Improvements (tc-server.py)
- TDoA geolocation (3+ gateways receiving same packet)
- Better handling of station reconnects with stale protobuf state
- Configurable timesync interval
- Class B beacon scheduling

### Test Suite Enhancements
- Add integration tests for protobuf + pdu-only combined mode
- Add stress tests for high uplink rates with protobuf
- Add tests for GPS position reporting when implemented
- Consider fuzzing protobuf decoder with malformed inputs

### Hardware Support
- SX1261 standalone support (for LBT and FSK)
- Fine timestamp calibration per gateway
- Multi-SX1302 configurations (beyond current master/slave)

### Protocol Extensions
- Downlink acknowledgment improvements (detailed TX status)
- Gateway statistics message (periodic health/metrics)
- Remote configuration updates (beyond router_config)
