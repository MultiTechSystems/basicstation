#!/bin/bash

. ../testlib.sh

# PDU-only mode tests uplink encoding (station -> LNS)
# Downlinks (LNS -> station) always use hex encoding

echo "=== Testing PDU-only uplink with hex encoding (default) ==="
PDU_ENCODING=hex python test.py
hex_status=$?

if [ $hex_status -ne 0 ]; then
    echo "FAIL: PDU-only hex encoding test failed"
    exit $hex_status
fi

echo ""
echo "=== Testing PDU-only uplink with base64 encoding ==="
PDU_ENCODING=base64 python test.py
base64_status=$?

if [ $base64_status -ne 0 ]; then
    echo "FAIL: PDU-only base64 encoding test failed"
    exit $base64_status
fi

echo ""
echo "PASS: Both hex and base64 uplink encoding tests passed"
exit 0