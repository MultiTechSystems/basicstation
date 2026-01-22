# Test Suite Updates

This document describes the updates made to the Basic Station regression test suite to support modern build environments, mbedTLS 3.x compatibility, and SX1302/SX1303 hardware simulation.

## Overview

The test suite has been modernized to:
- Run on Ubuntu 22.04 with Python 3.11
- Support mbedTLS versions 2.28.x and 3.6.x
- Add SX1302/SX1303 test variants (testsim1302, testms1302)
- Fix compatibility with websockets library 16.x
- Regenerate PKI certificates (valid until 2036)

## Build Variants

Four test variants are now available:

| Variant | Description |
|---------|-------------|
| `testsim` | Simulated SX1301 gateway (libloragw in master process) |
| `testsim1302` | Simulated SX1302/SX1303 with SF5/SF6 support |
| `testms` | Master/slave model simulation |
| `testms1302` | Master/slave with SF5/SF6 support |

### Building Variants

```bash
# Standard variants
make platform=linux variant=testsim
make platform=linux variant=testms

# SX1302/1303 variants (with SF5/SF6 support)
make platform=linux variant=testsim1302
make platform=linux variant=testms1302
```

## mbedTLS Compatibility

### Version Support

The build system now supports multiple mbedTLS versions via the `MBEDTLS_VERSION` environment variable:

```bash
# Default (2.28.0)
make platform=linux variant=testsim

# Specific version
MBEDTLS_VERSION=2.28.8 make platform=linux variant=testsim
MBEDTLS_VERSION=3.6.0 make platform=linux variant=testsim
```

### Changes for mbedTLS 3.x

1. **Repository URL**: Changed from `github.com/ARMmbed/mbedtls` to `github.com/Mbed-TLS/mbedtls`

2. **Branch naming**: mbedTLS 3.x uses `v3.x.x` format instead of `mbedtls-3.x.x`

3. **Submodules**: mbedTLS 3.x requires the `framework` submodule

4. **PSA Crypto**: mbedTLS 3.x requires PSA crypto initialization before cryptographic operations

5. **API Changes**:
   - `mbedtls/net.h` → `mbedtls/net_sockets.h`
   - `mbedtls/certs.h` removed
   - `mbedtls_pk_parse_key()` requires RNG function parameter
   - ECP keypair members are now private (affects ECDSA in CUPS)

### Source Code Updates

The following files were updated for mbedTLS 3.x compatibility:

- `src/tls.h` - Conditional includes, PSA init declaration
- `src/tls.c` - PSA initialization, API signature changes
- `src/cups.c` - ECDSA API compatibility for signature verification

## Test Infrastructure Updates

### Run Script Options

New options added to `run-regression-tests`:

```bash
# Skip build step (use pre-built binaries)
./run-regression-tests --nobuild

# Run specific variant only
./run-regression-tests --variant=testsim1302

# Combine options
./run-regression-tests --nobuild --variant=testms -Ttest3-updn-tls
```

### Modular Test Runners

New category-specific test runners:

| Script | Tests |
|--------|-------|
| `run-tests-core` | test1-selftests, test2-fs, test7-respawn |
| `run-tests-tls-cups` | test3-updn-tls, test3a-updn-tls, test4-cups, test5-rmtsh, test5-runcmd, test8-web |
| `run-tests-updn` | test3b-dnC, test3b-dnC_2ant, test3b-rx2_2ant, test3c-cca |
| `run-tests-pps` | test2-gps, test2-pps, test3d-bcns |
| `run-tests-all` | All tests |

### Python Compatibility Fixes

**websockets 16.x**: The handler signature changed from `async def handle_ws(self, ws, path)` to `async def handle_ws(self, ws)`. A compatibility helper `get_ws_path(ws)` was added to `pysys/tcutils.py`.

**Signed timeOffset**: Fixed handling of signed 64-bit timeOffset values in `pysys/simutils.py` for proper timing in simulation.

## PKI Certificate Updates

All test certificates were regenerated with:
- 10-year validity (expires January 2036)
- Subject Alternative Name (SAN) with `DNS:localhost`
- SHA-256 signatures

A regeneration script is provided: `regr-tests/pki-data/regen-certs.sh`

## GitHub Actions CI

The CI workflow (`.github/workflows/regr-tests.yml`) has been updated:

### Environment
- Ubuntu 22.04 (previously 18.04)
- Python 3.11 (previously 3.7)
- Actions v4 (previously v2)

### Matrix Strategy

Tests run as a matrix across:
- mbedTLS versions: 2.28.8, 3.6.0
- Test categories: core, tls-cups, updn, pps
- Variant groups: standard (testsim+testms), SX1302 (testsim1302+testms1302)

This results in 16 parallel jobs for comprehensive coverage.

### Coverage Reports

Coverage data is collected from all jobs and merged into a combined report.

## Usage Examples

### Running Tests Locally

```bash
# Full test suite with all variants
./run-regression-tests

# Quick test with single variant
./run-regression-tests --variant=testsim -Ttest1-selftests

# TLS tests only
cd regr-tests && ./run-tests-tls-cups --variant=testsim

# With specific mbedTLS version
MBEDTLS_VERSION=3.6.0 ./run-regression-tests -b
```

### CI-style Run

```bash
# Build once, run tests without rebuilding
make platform=linux variant=testsim
make platform=linux variant=testms
cd regr-tests
./run-tests-core --nobuild --ghactions --variant=testsim
./run-tests-core --nobuild --ghactions --variant=testms
```

## Compatibility Notes

- The test suite is backward compatible with existing test scripts
- SF5/SF6 tests only run on 1302 variants (testsim1302, testms1302)
- All variants run the same core test suite
