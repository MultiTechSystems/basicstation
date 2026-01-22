#!/bin/bash

# Test duty_cycle_enabled router_config option
# Runs multiple test cases for different regions and config options

. ../testlib.sh

# Test cases to run
# Note: Only testing regions with DC limits (EU868, KR920)
# US915/AU915 don't have station-side DC enforcement
TESTS=(
    "EU868_DC_DISABLED"   # EU868 with duty_cycle_enabled: false - all frames pass
    "EU868_DC_ENABLED"    # EU868 with duty_cycle_enabled: true - frames blocked
    "EU868_DC_DEFAULT"    # EU868 with no setting - frames blocked (default)
    "KR920_DC_DISABLED"   # KR920 with duty_cycle_enabled: false - all frames pass
    "KR920_DC_DEFAULT"    # KR920 with no setting - frames blocked (default)
)

failed=0

for test_case in "${TESTS[@]}"; do
    echo ""
    echo "========================================"
    echo "Running: $test_case"
    echo "========================================"
    
    DC_TEST_CASE="$test_case" python test.py
    result=$?
    
    if [ $result -ne 0 ]; then
        echo "FAILED: $test_case"
        failed=1
        break
    fi
    
    echo "PASSED: $test_case"
    sleep 1
done

if [ $failed -eq 0 ]; then
    banner "All duty_cycle tests passed"
else
    echo "FAILED: duty_cycle tests"
    exit 1
fi

collect_gcda
