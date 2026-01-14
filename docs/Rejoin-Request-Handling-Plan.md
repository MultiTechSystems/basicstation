# Rejoin Request Handling Plan

This document outlines the plan to fix rejoin request handling in Basic Station. Currently, rejoin requests are incorrectly parsed using the same logic as join requests, but the frame formats differ.

## Executive Summary

**Problem:** Rejoin frames are rejected because code expects 23-byte join request length, but rejoin is 19 bytes (Type 0/2) or 24 bytes (Type 1).

**Solution:** For rejoin frames, send raw PDU to LNS instead of parsing into fields:
```json
{"msgtype": "rejoin", "MHdr": 192, "pdu": "<hex>", "MIC": -123456}
```

**Msgtype:** `rejoin` already exists in code - this changes the message **format**, not the msgtype.

**Rationale:** 
- LNS has device context to properly interpret rejoin type and LoRaWAN version
- Forward compatible with future rejoin types without station updates

**Backward Compatible:** Join request parsing unchanged. Old stations drop rejoin frames silently.

## Table of Contents

- [Problem Statement](#problem-statement)
- [LoRaWAN Frame Formats](#lorawan-frame-formats)
- [Current Implementation](#current-implementation)
- [Proposed Solution](#proposed-solution)
- [Implementation Details](#implementation-details)
- [Protocol Impact](#protocol-impact)
- [Testing Plan](#testing-plan)

## Problem Statement

Basic Station currently treats rejoin requests the same as join requests, expecting a 23-byte frame and parsing fields (JoinEUI, DevEUI, DevNonce). However:

1. **Rejoin requests are 19 bytes**, not 23 bytes like join requests
2. **Field layout differs** between rejoin types (Type 0/2 vs Type 1)
3. **Field names differ** (RJcount vs DevNonce, NetID vs JoinEUI)
4. **LoRaWAN versions** may define additional rejoin types in the future

The current code rejects valid rejoin frames because of the length check:

```c
if( ftype == FRMTYPE_JREQ || ftype == FRMTYPE_REJOIN ) {
    if( len != OFF_jreq_len)  // OFF_jreq_len = 23, but rejoin is 19 bytes!
        goto badframe;
```

## LoRaWAN Frame Formats

### Join Request (MHDR = 0x00) - 23 bytes

```
+------+----------+---------+-----------+-----+
|  1   |    8     |    8    |     2     |  4  |  bytes
+======+==========+=========+===========+=====+
| MHdr | JoinEUI  | DevEUI  | DevNonce  | MIC |
+------+----------+---------+-----------+-----+
```

### Rejoin Request Type 0 (MHDR = 0xC0) - 19 bytes

```
+------+----------+-------+---------+----------+-----+
|  1   |    1     |   3   |    8    |    2     |  4  |  bytes
+======+==========+=======+=========+==========+=====+
| MHdr | RJType=0 | NetID | DevEUI  | RJcount0 | MIC |
+------+----------+-------+---------+----------+-----+
```

### Rejoin Request Type 1 (MHDR = 0xC0) - 24 bytes

```
+------+----------+----------+---------+----------+-----+
|  1   |    1     |    8     |    8    |    2     |  4  |  bytes
+======+==========+==========+=========+==========+=====+
| MHdr | RJType=1 | JoinEUI  | DevEUI  | RJcount1 | MIC |
+------+----------+----------+---------+----------+-----+
```

### Rejoin Request Type 2 (MHDR = 0xC0) - 19 bytes

```
+------+----------+-------+---------+----------+-----+
|  1   |    1     |   3   |    8    |    2     |  4  |  bytes
+======+==========+=======+=========+==========+=====+
| MHdr | RJType=2 | NetID | DevEUI  | RJcount2 | MIC |
+------+----------+-------+---------+----------+-----+
```

### Summary of Frame Lengths

| Frame Type | MHDR | Length | Key Differences |
|------------|------|--------|-----------------|
| Join Request | 0x00 | 23 bytes | JoinEUI (8), DevNonce (2) |
| Rejoin Type 0 | 0xC0 | 19 bytes | NetID (3), RJcount0 (2) |
| Rejoin Type 1 | 0xC0 | 24 bytes | JoinEUI (8), RJcount1 (2) |
| Rejoin Type 2 | 0xC0 | 19 bytes | NetID (3), RJcount2 (2) |

## Current Implementation

### Location

`src/lora.c` - `s2e_parse_lora_frame()`

### Current Code (lines 107-138)

```c
if( ftype == FRMTYPE_JREQ || ftype == FRMTYPE_REJOIN ) {
    if( len != OFF_jreq_len)  // OFF_jreq_len = 23
        goto badframe;
    uL_t joineui = rt_rlsbf8(&frame[OFF_joineui]);
    
    // ... JoinEUI filter check ...
    
    str_t msgtype = (ftype == FRMTYPE_JREQ ? "jreq" : "rejoin");
    u1_t  mhdr = frame[OFF_mhdr];
    uL_t  deveui = rt_rlsbf8(&frame[OFF_deveui]);
    u2_t  devnonce = rt_rlsbf2(&frame[OFF_devnonce]);
    s4_t  mic = (s4_t)rt_rlsbf4(&frame[len-4]);
    uj_encKVn(buf,
              "msgtype", 's', msgtype,
              "MHdr",    'i', mhdr,
              rt_joineui,'E', joineui,
              rt_deveui, 'E', deveui,
              "DevNonce",'i', devnonce,
              "MIC",     'i', mic,
              NULL);
    return 1;
}
```

### Problems

1. Length check fails for rejoin (19 or 24 bytes vs expected 23)
2. Field offsets are wrong for rejoin frames
3. Field names are incorrect (DevNonce vs RJcount, JoinEUI vs NetID for Type 0/2)
4. No support for different rejoin types

## Proposed Solution

### Approach: Send Raw PDU for Rejoin

Instead of parsing rejoin frames into fields, send the raw PDU to the LNS:

1. **Join Request (MHDR = 0x00)**: Continue parsing into fields (backward compatible)
2. **Rejoin Request (MHDR = 0xC0)**: Send raw PDU with minimal parsing

### Rationale

1. **Version Independence**: LoRaWAN versions may define new rejoin types or modify existing ones
2. **LNS Responsibility**: The LNS has the context (device profile, LoRaWAN version) to properly interpret the rejoin frame
3. **Simplicity**: Avoids complex conditional parsing based on rejoin type
4. **Forward Compatibility**: New rejoin types automatically supported without station updates

### New Message Format for Rejoin

```json
{
  "msgtype": "rejoin",
  "MHdr": 192,
  "pdu": "C0010203040506070809101112131415161718",
  "MIC": -1234567890
}
```

| Field | Type | Description |
|-------|------|-------------|
| `msgtype` | String | `"rejoin"` |
| `MHdr` | Integer | MHDR byte value (0xC0 = 192) |
| `pdu` | String | Full frame as hex string (includes MHdr through MIC) |
| `MIC` | Integer | MIC extracted from last 4 bytes (for quick validation) |

## Implementation Details

### Phase 1: Modify Frame Parsing

**File:** `src/lora.c`

```c
// Constants for rejoin frames
#define OFF_rejoin_type    1
#define OFF_rejoin_minlen 19  // Type 0/2
#define OFF_rejoin_maxlen 24  // Type 1

int s2e_parse_lora_frame (ujbuf_t* buf, const u1_t* frame , int len, dbuf_t* lbuf) {
    // ... existing validation ...
    
    int ftype = frame[OFF_mhdr] & MHDR_FTYPE;
    
    // Handle Join Request - keep existing parsing for backward compatibility
    if( ftype == FRMTYPE_JREQ ) {
        if( len != OFF_jreq_len)
            goto badframe;
        // ... existing jreq parsing ...
        return 1;
    }
    
    // Handle Rejoin Request - send raw PDU
    if( ftype == FRMTYPE_REJOIN ) {
        // Validate minimum length (Type 0/2 = 19 bytes)
        if( len < OFF_rejoin_minlen || len > OFF_rejoin_maxlen )
            goto badframe;
        
        u1_t mhdr = frame[OFF_mhdr];
        s4_t mic = (s4_t)rt_rlsbf4(&frame[len-4]);
        
        // Optional: Apply JoinEUI filter for Type 1 rejoin only
        // Type 1 has JoinEUI at offset 2
        if( len == OFF_rejoin_maxlen && frame[OFF_rejoin_type] == 1 ) {
            uL_t joineui = rt_rlsbf8(&frame[2]);
            // ... apply filter if needed ...
        }
        
        uj_encKVn(buf,
                  "msgtype", 's', "rejoin",
                  "MHdr",    'i', mhdr,
                  "pdu",     'H', len, &frame[0],
                  "MIC",     'i', mic,
                  NULL);
        xprintf(lbuf, "rejoin MHdr=%02X len=%d MIC=%d pdu=%H",
                mhdr, len, mic, len, &frame[0]);
        return 1;
    }
    
    // ... rest of existing code for data frames ...
}
```

### Phase 2: Update Test Cases

**File:** `src/selftest_lora.c`

Add test cases for:
- Rejoin Type 0 (19 bytes)
- Rejoin Type 1 (24 bytes)  
- Rejoin Type 2 (19 bytes)
- Invalid rejoin lengths

### Phase 3: Documentation

Update LNS Integration Guide with new rejoin message format.

## Protocol Impact

### Message Format Change

The `rejoin` msgtype already exists but currently outputs the same fields as `jreq`. This plan changes the rejoin message format to use raw PDU instead of parsed fields.

**Join Request (unchanged):**
```json
{
  "msgtype": "jreq",
  "MHdr": 0,
  "JoinEui": "01-02-03-04-05-06-07-08",
  "DevEui": "11-12-13-14-15-16-17-18",
  "DevNonce": 12345,
  "MIC": -1234567890,
  "DR": 5,
  "Freq": 868100000,
  "upinfo": { ... }
}
```

**Rejoin Request (new format):**
```json
{
  "msgtype": "rejoin",
  "MHdr": 192,
  "pdu": "C001AABBCC1112131415161718F1F2DEADBEEF",
  "MIC": -1234567890,
  "DR": 5,
  "Freq": 868100000,
  "upinfo": { ... }
}
```

### LNS Handling

LNS implementations need to:

1. **Detect message type**: Check `msgtype` field for `"rejoin"`
2. **Parse PDU**: Decode hex string to bytes
3. **Determine rejoin type**: Check byte at offset 1
4. **Extract fields**: Parse based on rejoin type and LoRaWAN version

Example LNS parsing (Python):

```python
def handle_rejoin(msg):
    pdu = bytes.fromhex(msg['pdu'])
    mhdr = pdu[0]
    rejoin_type = pdu[1]
    
    if rejoin_type == 0:
        # Type 0: NetID (3) + DevEUI (8) + RJcount0 (2) + MIC (4)
        netid = int.from_bytes(pdu[2:5], 'little')
        deveui = pdu[5:13]
        rjcount = int.from_bytes(pdu[13:15], 'little')
    elif rejoin_type == 1:
        # Type 1: JoinEUI (8) + DevEUI (8) + RJcount1 (2) + MIC (4)
        joineui = pdu[2:10]
        deveui = pdu[10:18]
        rjcount = int.from_bytes(pdu[18:20], 'little')
    elif rejoin_type == 2:
        # Type 2: NetID (3) + DevEUI (8) + RJcount2 (2) + MIC (4)
        netid = int.from_bytes(pdu[2:5], 'little')
        deveui = pdu[5:13]
        rjcount = int.from_bytes(pdu[13:15], 'little')
```

### Backward Compatibility

| Station Version | LNS Version | Behavior |
|-----------------|-------------|----------|
| Old | Any | Rejoin frames rejected (length check fails) |
| New | Old | LNS receives `rejoin` msgtype, may ignore or error |
| New | New | Full rejoin support |

**Note:** Old stations silently drop rejoin frames, so upgrading improves functionality without breaking existing setups.

## Testing Plan

### Unit Tests

1. **Join Request Parsing** (unchanged)
   - Valid 23-byte join request
   - Too short (22 bytes) - rejected
   - JoinEUI filter applied

2. **Rejoin Type 0 Parsing**
   - Valid 19-byte frame with RJType=0
   - Verify PDU in output matches input

3. **Rejoin Type 1 Parsing**
   - Valid 24-byte frame with RJType=1
   - Optional: JoinEUI filter for Type 1

4. **Rejoin Type 2 Parsing**
   - Valid 19-byte frame with RJType=2

5. **Invalid Rejoin Frames**
   - Too short (< 19 bytes)
   - Too long (> 24 bytes)
   - Invalid RJType

### Integration Tests

1. **End-to-End Rejoin Flow**
   - Simulate device sending rejoin
   - Verify LNS receives correct `rejoin` message
   - Verify LNS can parse PDU correctly

2. **Mixed Traffic**
   - Join requests and rejoin requests interleaved
   - Verify correct message types

### Regression Tests

1. **Existing Join Request Tests**
   - All existing jreq tests must pass unchanged

2. **Filter Behavior**
   - JoinEUI filter continues to work for jreq
   - Optional: JoinEUI filter for rejoin Type 1

## Timeline

| Phase | Task | Estimate |
|-------|------|----------|
| 1 | Modify `s2e_parse_lora_frame()` | 2 hours |
| 2 | Add unit tests | 2 hours |
| 3 | Integration testing | 2 hours |
| 4 | Documentation update | 1 hour |

## References

- [LoRaWAN 1.1 Specification](https://resources.lora-alliance.org/technical-specifications) - Section 6.2.4 Rejoin-request message
- [LoRaWAN Backend Interfaces 1.0](https://resources.lora-alliance.org/technical-specifications) - Rejoin handling
