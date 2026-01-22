# mbedTLS Update and 3.x Compatibility

## Overview

This feature updates the mbedTLS dependency handling to support both the legacy 2.x branch and the newer 3.x releases. The mbedTLS library provides TLS/SSL and cryptographic functionality used for secure connections to CUPS and LNS servers.

## Changes

### Build System Updates

#### `deps/mbedtls/prep.sh`

- **Repository URL**: Updated from `github.com/ARMmbed/mbedtls` to `github.com/Mbed-TLS/mbedtls` (repository was migrated)
- **Version flexibility**: Added `MBEDTLS_VERSION` environment variable support
  - Default: `2.28.0` for backward compatibility
  - Supports any 2.x or 3.x version
- **Branch naming**: Handles different tag formats (`mbedtls-2.x.x` vs `v3.x.x`)
- **Submodule handling**: mbedTLS 3.x requires the `framework` submodule
  - Full clone (not shallow) for 3.x to properly fetch submodules
  - Automatic `git submodule update --init --recursive`
- **Version change detection**: Automatically rebuilds when version changes

#### `deps/mbedtls/makefile`

- **PSA headers**: Added rules to copy `psa/*.h` headers required by mbedTLS 3.x
- The PSA (Platform Security Architecture) crypto API is used by mbedTLS 3.x

### Source Code Compatibility

#### `src/tls.h`

- Conditional include for `mbedtls/net.h` (2.x) vs `mbedtls/net_sockets.h` (3.x)
- Added `tls_ensurePsaInit()` function declaration for PSA initialization

#### `src/tls.c`

- **PSA crypto initialization**: Required for mbedTLS 3.x before any crypto operations
- **Conditional includes**: Handle removed headers (`mbedtls/certs.h` removed in 3.x)
- **API changes**: `mbedtls_pk_parse_key()` requires RNG parameter in 3.x
- **Key format detection**: Improved handling of PEM vs DER key formats

#### `src/cups.c`

- **ECDSA API changes**: mbedTLS 3.x made `ecp_keypair` struct members private
- Updated signature verification to use new API (`mbedtls_ecp_set_public_key`)
- PSA initialization before ECDSA operations

## Usage

### Building with Default mbedTLS (2.28.0)

```bash
make platform=linux variant=testsim
```

### Building with Specific mbedTLS Version

```bash
# Use mbedTLS 2.28.8
MBEDTLS_VERSION=2.28.8 make platform=linux variant=testsim

# Use mbedTLS 3.6.0
MBEDTLS_VERSION=3.6.0 make platform=linux variant=testsim
```

### Forcing mbedTLS Rebuild

Delete the cached clone to force a fresh download:

```bash
rm -rf deps/mbedtls/git-repo deps/mbedtls/platform-*
make platform=linux variant=testsim
```

## Compatibility

| mbedTLS Version | Status | Notes |
|-----------------|--------|-------|
| 2.28.x (LTS)    | Supported | Default, recommended for production |
| 3.6.x           | Supported | Latest features, PSA crypto API |

## Testing

Both mbedTLS 2.x and 3.x have been tested with the full regression test suite:

```bash
cd regr-tests
./run-regression-tests
```

## Security Considerations

- mbedTLS 2.28.x is the Long-Term Support (LTS) branch with security updates
- mbedTLS 3.x includes the PSA Crypto API for improved security architecture
- Both versions receive security patches from the Mbed TLS team
