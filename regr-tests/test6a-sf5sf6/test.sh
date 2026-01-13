#!/bin/bash

# --- Revised 3-Clause BSD License ---
# Copyright Semtech Corporation 2022. All rights reserved.

# This test requires testsim1302 variant for SF5/SF6 support
# Skip if running with testsim (no SF5/SF6 support)
if [[ "$TEST_VARIANT" != "testsim1302" ]]; then
    echo "Skipping test - requires testsim1302 variant (SF5/SF6 support)"
    exit 0
fi

. ../testlib.sh

# Test SF5/SF6 with SX1302/SX1303 (RP2 1.0.5)
python test.py
banner "SF5/SF6 test done"
collect_gcda
