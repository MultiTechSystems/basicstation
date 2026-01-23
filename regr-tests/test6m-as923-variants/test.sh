#!/bin/bash

# Test AS923 variant region names (AS923-1, AS923-2, AS923-3, AS923-4)
# Verifies hyphenated region names are correctly parsed in router_config

. ../testlib.sh

python test.py
collect_gcda
