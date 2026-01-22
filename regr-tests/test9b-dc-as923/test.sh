#!/bin/bash

# AS923 Duty Cycle Tests  
# Tests per-channel DC (10% per channel with LBT)

. ../testlib.sh

TESTS=(
    "DISABLED"   # duty_cycle_enabled: false
    "SINGLE_CH"  # Single channel DC
    "MULTI_CH"   # Multi-channel separate budgets
    "WINDOW"     # DC window recovery
)

if [ -n "$DC_TEST" ]; then
    TESTS=("$DC_TEST")
fi

failed=0
passed=0

for test in "${TESTS[@]}"; do
    echo ""
    echo "=== AS923: $test ==="
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
echo "AS923 DC Tests: $passed passed, $failed failed"

if [ $failed -eq 0 ]; then
    banner "AS923 duty cycle tests passed"
else
    exit 1
fi

collect_gcda
