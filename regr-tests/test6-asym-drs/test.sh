#!/bin/bash

# --- Revised 3-Clause BSD License ---
# Copyright Semtech Corporation 2022. All rights reserved.

# Skip testms variant - master/slave model requires different config
if [[ "$TEST_VARIANT" == "testms" ]]; then
    echo "Skipping test - testms variant not supported for this test"
    exit 0
fi

. ../testlib.sh

# Test asymmetric datarate support (RP2 1.0.5)
# This test uses the US902 RP2 1.0.5 region config with DRs_up and DRs_dn

python test.py
banner "Asymmetric DR test done"
collect_gcda
