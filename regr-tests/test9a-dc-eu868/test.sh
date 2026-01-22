#!/bin/bash

# EU868 Duty Cycle Tests
# Tests band-based DC: 10% (869.4-869.65), 1% (868.0-868.6), 0.1% (other)

. ../testlib.sh

TESTS=(
    "DISABLED"    # duty_cycle_enabled: false
    "BAND_10PCT"  # 10% band rapid TX
    "BAND_1PCT"   # 1% band blocking
    "BAND_01PCT"  # 0.1% band heavy blocking
    "MULTIBAND"   # Separate band budgets
    "WINDOW"      # DC window recovery
)

# Allow running single test with DC_TEST env var
if [ -n "$DC_TEST" ]; then
    TESTS=("$DC_TEST")
fi

failed=0
passed=0

for test in "${TESTS[@]}"; do
    echo ""
    echo "=== EU868: $test ==="
    DC_TEST="$test" python test.py
    if [ $? -eq 0 ]; then
        echo "PASSED: $test"
        passed=$((passed + 1))
    else
        echo "FAILED: $test"
        failed=$((failed + 1))
    fi
    sleep 0.5
done

echo ""
echo "EU868 DC Tests: $passed passed, $failed failed"

if [ $failed -eq 0 ]; then
    banner "EU868 duty cycle tests passed"
else
    exit 1
fi

collect_gcda
