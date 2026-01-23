#!/bin/bash

# Test AS923 SF5/SF6 support (RP2 1.0.5)
# Requires testsim1302 or testms1302 variant for SF5/SF6 support
if [[ "$TEST_VARIANT" != "testsim1302" && "$TEST_VARIANT" != "testms1302" ]]; then
    echo "SKIP: Test requires testsim1302 or testms1302 variant for SF5/SF6 support"
    exit 0
fi

. ../testlib.sh

python test.py
collect_gcda
