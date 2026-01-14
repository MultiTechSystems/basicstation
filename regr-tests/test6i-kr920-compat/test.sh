#!/bin/bash

# Test KR920 backward compatibility (RP2 1.0.5)
# This test uses the KR920 RP2 1.0.5 region config with standard DRs (DR0-5)
# Works with all variants: testsim, testsim1302, testms, testms1302

. ../testlib.sh

python test.py
collect_gcda
