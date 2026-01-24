# Protobuf TC Protocol Design

## Overview

This document describes a binary protocol option for the TC (Traffic Controller) 
protocol using Protocol Buffers (protobuf) to reduce backhaul bandwidth consumption.

## Backward Compatibility Strategy

The protocol maintains backward compatibility by:

1. **Discovery phase remains JSON** - The initial WebSocket connection and 
   `/router-info` query use the existing JSON format
2. **Version message remains JSON** - Station sends JSON `version` message with 
   a new `capabilities` field indicating protobuf support
3. **router_config remains JSON** - LNS responds with JSON, including a 
   `protocol_format` field to select binary mode
4. **Data messages switch to binary** - After negotiation, uplink/downlink 
   messages use protobuf over WebSocket binary frames

### Negotiation Flow

```
Station                                    LNS
   |                                        |
   |-- JSON: {"router": "..."}  ----------->|  Discovery (unchanged)
   |<- JSON: {"uri": "...", ...} -----------|
   |                                        |
   |== WebSocket Connect ==================>|
   |                                        |
   |-- JSON: {"msgtype":"version",  ------->|  Version with capabilities
   |         "protocol":2,                  |
   |         "capabilities":["protobuf"],   |
   |         ...}                           |
   |                                        |
   |<- JSON: {"msgtype":"router_config", ---|  Config enables protobuf
   |         "protocol_format":"protobuf",  |
   |         ...}                           |
   |                                        |
   |-- BINARY: UplinkMessage  ------------->|  Data phase uses protobuf
   |<- BINARY: DownlinkMessage -------------|
```

## Protobuf Schema

```protobuf
syntax = "proto3";
package basicstation;

// Message type enumeration (replaces "msgtype" string)
enum MessageType {
  MSG_UNKNOWN = 0;
  MSG_UPDF = 1;      // Uplink data frame
  MSG_JREQ = 2;      // Join request
  MSG_PROPDF = 3;    // Proprietary frame
  MSG_DNTXED = 4;    // TX confirmation
  MSG_TIMESYNC = 5;  // Time sync
  MSG_DNMSG = 10;    // Downlink message
  MSG_DNSCHED = 11;  // Multicast schedule
}

// Common radio metadata for uplinks
message RadioMetadata {
  uint32 dr = 1;           // Data rate (0-15)
  uint32 freq = 2;         // Frequency in Hz
  int64 rctx = 3;          // Radio context
  int64 xtime = 4;         // Internal timestamp
  int64 gpstime = 5;       // GPS time (microseconds since epoch)
  int32 rssi = 6;          // RSSI (negative dBm)
  float snr = 7;           // SNR
  int32 fts = 8;           // Fine timestamp (-1 if unavailable)
  double rxtime = 9;       // UTC receive time
}

// Uplink data frame (replaces msgtype:"updf")
message UplinkDataFrame {
  uint32 mhdr = 1;
  fixed32 dev_addr = 2;    // 4-byte device address
  uint32 fctrl = 3;
  uint32 fcnt = 4;
  bytes fopts = 5;         // Frame options (raw bytes, not hex)
  int32 fport = 6;         // -1 if no port
  bytes frm_payload = 7;   // Payload (raw bytes)
  fixed32 mic = 8;         // 4-byte message integrity code
  RadioMetadata upinfo = 9;
  double ref_time = 10;
  bytes pdu = 11;          // Raw PHYPayload (pdu-only mode)
}

// Join request (replaces msgtype:"jreq")
message JoinRequest {
  uint32 mhdr = 1;
  uint64 join_eui = 2;     // 8 bytes as uint64
  uint64 dev_eui = 3;      // 8 bytes as uint64
  uint32 dev_nonce = 4;
  int32 mic = 5;
  RadioMetadata upinfo = 6;
  double ref_time = 7;
}

// Proprietary frame (replaces msgtype:"propdf")
message ProprietaryFrame {
  bytes frm_payload = 1;   // Entire PHYPayload
  RadioMetadata upinfo = 2;
  double ref_time = 3;
}

// TX confirmation (replaces msgtype:"dntxed")
message TxConfirmation {
  int64 diid = 1;
  uint64 dev_eui = 2;
  int64 rctx = 3;
  int64 xtime = 4;
  double txtime = 5;
  int64 gpstime = 6;
  uint32 dr = 7;
  uint32 freq = 8;
}

// Time sync request/response (replaces msgtype:"timesync")
message TimeSync {
  int64 txtime = 1;        // Station -> LNS
  int64 gpstime = 2;       // LNS -> Station
  int64 xtime = 3;         // LNS -> Station (for GPS transfer)
}

// Downlink message (replaces msgtype:"dnmsg")
message DownlinkMessage {
  uint64 dev_eui = 1;
  uint32 dc = 2;           // Device class: 0=A, 1=B, 2=C
  int64 diid = 3;
  bytes pdu = 4;           // Raw PDU (not hex)
  uint32 rx_delay = 5;
  uint32 rx1_dr = 6;
  uint32 rx1_freq = 7;
  uint32 rx2_dr = 8;
  uint32 rx2_freq = 9;
  uint32 priority = 10;
  int64 xtime = 11;
  int64 rctx = 12;
  int64 gpstime = 13;      // For Class B
  uint32 dr = 14;          // For Class B
  uint32 freq = 15;        // For Class B
  double mux_time = 16;    // RTT monitoring
}

// Multicast schedule entry
message ScheduleEntry {
  bytes pdu = 1;
  uint32 dr = 2;
  uint32 freq = 3;
  uint32 priority = 4;
  int64 gpstime = 5;
  int64 rctx = 6;
}

// Multicast schedule (replaces msgtype:"dnsched")
message DownlinkSchedule {
  repeated ScheduleEntry schedule = 1;
}

// Wrapper message for all TC protocol messages
message TcMessage {
  MessageType type = 1;
  oneof payload {
    UplinkDataFrame updf = 2;
    JoinRequest jreq = 3;
    ProprietaryFrame propdf = 4;
    TxConfirmation dntxed = 5;
    TimeSync timesync = 6;
    DownlinkMessage dnmsg = 10;
    DownlinkSchedule dnsched = 11;
  }
}
```

## Message Size Comparison

### Typical Uplink Data Frame (updf)

**JSON format** (~270 bytes):
```json
{"msgtype":"updf","MHdr":64,"DevAddr":16909060,"FCtrl":0,"FCnt":42,
"FOpts":"","FPort":1,"FRMPayload":"0102030405060708","MIC":-12345678,
"DR":5,"Freq":868100000,"RefTime":1706100000.123456,
"upinfo":{"rctx":0,"xtime":1234567890123,"gpstime":1234567890000000,
"rssi":-50,"snr":9.5,"fts":-1,"rxtime":1706100000.123456}}
```

**Protobuf format** (~65 bytes):
- Header (type enum): 2 bytes
- mhdr (varint): 2 bytes
- dev_addr (varint): 5 bytes
- fctrl (varint): 1 byte
- fcnt (varint): 2 bytes
- fopts (empty): 0 bytes
- fport (varint): 2 bytes
- frm_payload (8 bytes + tag): 10 bytes
- mic (varint): 5 bytes
- RadioMetadata submessage: ~35 bytes
  - dr: 2 bytes
  - freq: 5 bytes
  - rctx: 2 bytes
  - xtime: 9 bytes
  - gpstime: 9 bytes
  - rssi: 2 bytes
  - snr: 5 bytes
  - fts: 2 bytes
  - rxtime: 9 bytes
- ref_time: 9 bytes

**Savings: ~76% reduction** (270 → 65 bytes)

### Typical Join Request (jreq)

**JSON format** (~230 bytes):
```json
{"msgtype":"jreq","MHdr":0,"JoinEui":"0102030405060708",
"DevEui":"0807060504030201","DevNonce":12345,"MIC":-12345678,
"DR":5,"Freq":868100000,"RefTime":1706100000.123456,
"upinfo":{"rctx":0,"xtime":1234567890123,"gpstime":1234567890000000,
"rssi":-50,"snr":9.5,"fts":-1,"rxtime":1706100000.123456}}
```

**Protobuf format** (~55 bytes):
- Header: 2 bytes
- mhdr: 1 byte
- join_eui: 9 bytes
- dev_eui: 9 bytes
- dev_nonce: 3 bytes
- mic: 5 bytes
- RadioMetadata: ~35 bytes

**Savings: ~76% reduction** (230 → 55 bytes)

### Typical Downlink Message (dnmsg) - Class A

**JSON format** (~280 bytes):
```json
{"msgtype":"dnmsg","DevEui":"0807060504030201","dC":0,"diid":123456,
"pdu":"600403020100020001020304050607080102030405060708091011121314",
"RxDelay":1,"RX1DR":5,"RX1Freq":868100000,"RX2DR":0,"RX2Freq":869525000,
"priority":1,"xtime":1234567890123,"rctx":0,"MuxTime":1706100000.123456}
```

**Protobuf format** (~70 bytes):
- Header: 2 bytes
- dev_eui: 9 bytes
- dc: 1 byte
- diid: 5 bytes
- pdu (29 bytes + tag): 31 bytes
- rx_delay: 2 bytes
- rx1_dr/freq: 7 bytes
- rx2_dr/freq: 7 bytes
- priority: 2 bytes
- xtime: 9 bytes
- rctx: 2 bytes
- mux_time: 9 bytes

**Savings: ~75% reduction** (280 → 70 bytes)

### TX Confirmation (dntxed)

**JSON format** (~180 bytes):
```json
{"msgtype":"dntxed","diid":123456,"DevEui":"0807060504030201",
"rctx":0,"xtime":1234567890123,"txtime":1706100000.123456,
"gpstime":1234567890000000,"DR":5,"Freq":868100000}
```

**Protobuf format** (~45 bytes)

**Savings: ~75% reduction** (180 → 45 bytes)

### PDU-Only Mode with Protobuf

When combined with PDU-only mode (`pdu_only: true`), protobuf achieves maximum efficiency
by sending the raw PHYPayload without parsing into individual LoRaWAN fields.

**Configuration:**
```json
{
  "msgtype": "router_config",
  "pdu_only": true,
  "protocol_format": "protobuf",
  ...
}
```

**Protobuf pdu-only format** (~80 bytes for 24-byte frame):
- pdu field (raw bytes): 26 bytes (tag + length + 24 bytes data)
- RadioMetadata: ~45 bytes
- ref_time: 9 bytes

| Format | Size | vs JSON Parsed |
|--------|------|----------------|
| JSON (parsed) | ~325 bytes | baseline |
| JSON (pdu-only hex) | ~254 bytes | -22% |
| Protobuf (parsed) | ~90 bytes | -72% |
| **Protobuf (pdu-only)** | **~80 bytes** | **-75%** |

For details, see [PDU-Only-Mode.md](PDU-Only-Mode.md#pdu-only-mode-with-protobuf).

## Bandwidth Savings Estimates

### Assumptions

Based on typical LoRaWAN gateway deployments:

| Metric | Low Traffic | Medium Traffic | High Traffic |
|--------|-------------|----------------|--------------|
| Uplinks/day | 1,000 | 10,000 | 100,000 |
| Join requests/day | 10 | 100 | 1,000 |
| Downlinks/day | 100 | 1,000 | 10,000 |
| TX confirmations/day | 100 | 1,000 | 10,000 |
| Timesync/day | 1,440 | 1,440 | 1,440 |

### Daily Bandwidth (JSON vs Protobuf)

| Traffic Level | JSON/day | Protobuf/day | Savings/day |
|---------------|----------|--------------|-------------|
| Low | ~350 KB | ~85 KB | ~265 KB (76%) |
| Medium | ~3.5 MB | ~850 KB | ~2.65 MB (76%) |
| High | ~35 MB | ~8.5 MB | ~26.5 MB (76%) |

### Weekly Bandwidth

| Traffic Level | JSON/week | Protobuf/week | Savings/week |
|---------------|-----------|---------------|--------------|
| Low | ~2.5 MB | ~600 KB | ~1.9 MB |
| Medium | ~24.5 MB | ~6 MB | ~18.5 MB |
| High | ~245 MB | ~60 MB | ~185 MB |

### Monthly Bandwidth

| Traffic Level | JSON/month | Protobuf/month | Savings/month |
|---------------|------------|----------------|---------------|
| Low | ~10.5 MB | ~2.5 MB | ~8 MB |
| Medium | ~105 MB | ~25 MB | ~80 MB |
| High | ~1.05 GB | ~255 MB | ~795 MB |

## Implementation Plan

### Phase 1: Protocol Definition
1. Finalize protobuf schema
2. Add protobuf-c dependency (lightweight C implementation)
3. Generate C code from .proto files

### Phase 2: Station Implementation
1. Add `capabilities` field to version message
2. Parse `protocol_format` from router_config
3. Implement protobuf encoding for uplink messages
4. Implement protobuf decoding for downlink messages
5. Use WebSocket binary frames for protobuf messages

### Phase 3: Testing
See [Comprehensive Test Plan](#comprehensive-test-plan) below.

### Phase 4: LNS Support
1. Document LNS implementation requirements
2. Provide reference implementation/library

## Comprehensive Test Plan

### Unit Tests (selftest_protobuf.c)

#### 1. Encoding Tests

##### 1.1 UplinkDataFrame Encoding
```c
// Test: encode_updf_minimal
// Verify encoding of updf with minimal fields (no fopts, no payload)
// Expected: Valid protobuf, correct field values, size < JSON equivalent

// Test: encode_updf_full
// Verify encoding with all fields populated including large payload
// Expected: All fields correctly encoded, payload as raw bytes

// Test: encode_updf_negative_values
// Verify handling of negative DevAddr and MIC (common in LoRaWAN)
// Expected: sfixed32 correctly encodes negative values

// Test: encode_updf_max_payload
// Verify encoding with maximum payload size (242 bytes)
// Expected: Correct length-delimited encoding

// Test: encode_updf_fopts
// Verify FOpts (MAC commands) encoding as raw bytes
// Expected: Bytes field correctly encoded
```

##### 1.2 JoinRequest Encoding
```c
// Test: encode_jreq_basic
// Verify join request with typical EUIs and nonce
// Expected: EUIs as fixed64, correct byte order

// Test: encode_jreq_all_zeros
// Verify handling of all-zero EUIs (edge case)
// Expected: Fields present with zero values

// Test: encode_jreq_all_ones
// Verify handling of 0xFFFFFFFFFFFFFFFF EUIs
// Expected: Correct fixed64 encoding
```

##### 1.3 ProprietaryFrame Encoding
```c
// Test: encode_propdf_basic
// Verify proprietary frame encoding
// Expected: Entire PHYPayload as bytes field

// Test: encode_propdf_large
// Verify large proprietary frame (max size)
// Expected: Correct length-delimited encoding
```

##### 1.4 TxConfirmation Encoding
```c
// Test: encode_dntxed_basic
// Verify TX confirmation encoding
// Expected: All fields correctly encoded

// Test: encode_dntxed_with_gps
// Verify with GPS time present
// Expected: gpstime field populated
```

##### 1.5 TimeSync Encoding
```c
// Test: encode_timesync_request
// Verify station->LNS timesync request
// Expected: txtime field set

// Test: encode_timesync_response
// Verify LNS->station timesync response format
// Expected: gpstime and xtime fields set
```

##### 1.6 RadioMetadata Encoding
```c
// Test: encode_radiometa_complete
// Verify all radio metadata fields
// Expected: All fields present and correct

// Test: encode_radiometa_no_gps
// Verify handling when GPS unavailable (gpstime=0)
// Expected: Field present with zero value

// Test: encode_radiometa_no_fts
// Verify fine timestamp unavailable (fts=-1)
// Expected: Correct signed encoding

// Test: encode_radiometa_negative_rssi
// Verify negative RSSI values
// Expected: Correct signed int32 encoding

// Test: encode_radiometa_negative_snr
// Verify negative SNR values
// Expected: Correct float encoding
```

#### 2. Decoding Tests

##### 2.1 DownlinkMessage Decoding
```c
// Test: decode_dnmsg_class_a
// Verify Class A downlink decoding with xtime/rctx
// Expected: All RX window params correct

// Test: decode_dnmsg_class_b
// Verify Class B with gpstime and beacon params
// Expected: gpstime, dr, freq populated

// Test: decode_dnmsg_class_c
// Verify Class C immediate downlink
// Expected: Correct class enum value

// Test: decode_dnmsg_large_pdu
// Verify large PDU decoding (max 242 bytes)
// Expected: PDU bytes match input

// Test: decode_dnmsg_empty_pdu
// Verify handling of empty PDU (error case)
// Expected: Appropriate error returned

// Test: decode_dnmsg_mux_time
// Verify MuxTime for RTT calculation
// Expected: double precision preserved
```

##### 2.2 DownlinkSchedule Decoding
```c
// Test: decode_dnsched_single
// Verify single entry schedule
// Expected: One ScheduleEntry decoded

// Test: decode_dnsched_multiple
// Verify multiple entries (typical multicast)
// Expected: All entries in correct order

// Test: decode_dnsched_empty
// Verify empty schedule handling
// Expected: Empty array, no error

// Test: decode_dnsched_max_entries
// Verify maximum schedule size
// Expected: All entries decoded correctly
```

##### 2.3 TimeSync Response Decoding
```c
// Test: decode_timesync_response
// Verify LNS timesync response
// Expected: gpstime and xtime extracted

// Test: decode_timesync_gps_transfer
// Verify GPS time transfer mode
// Expected: xtime correctly associated
```

##### 2.4 RunCommand Decoding
```c
// Test: decode_runcmd_basic
// Verify command with arguments
// Expected: Arguments array populated

// Test: decode_runcmd_empty_args
// Verify command with no arguments
// Expected: Empty array, no error

// Test: decode_runcmd_special_chars
// Verify arguments with special characters
// Expected: Characters preserved correctly
```

##### 2.5 RemoteShell Decoding
```c
// Test: decode_rmtsh_start
// Verify session start message
// Expected: start=true, no data

// Test: decode_rmtsh_data
// Verify data transfer
// Expected: Binary data preserved

// Test: decode_rmtsh_stop
// Verify session stop
// Expected: stop=true
```

#### 3. Round-Trip Tests

```c
// Test: roundtrip_updf
// Encode updf, decode, compare all fields
// Expected: Perfect field preservation

// Test: roundtrip_jreq
// Encode jreq, decode, compare all fields
// Expected: Perfect field preservation

// Test: roundtrip_dnmsg
// Encode dnmsg (simulated LNS), decode at station
// Expected: All parameters match

// Test: roundtrip_binary_payload
// Verify binary data (PDU) survives round trip
// Expected: Byte-for-byte match
```

#### 4. Error Handling Tests

```c
// Test: decode_truncated_message
// Attempt to decode truncated protobuf
// Expected: Error returned, no crash

// Test: decode_invalid_tag
// Message with unknown field tag
// Expected: Unknown fields ignored (proto3)

// Test: decode_wrong_wire_type
// Field with incorrect wire type
// Expected: Error returned

// Test: decode_nested_depth_limit
// Deeply nested message (attack vector)
// Expected: Depth limit enforced

// Test: decode_oversized_string
// String/bytes field exceeding limit
// Expected: Error returned

// Test: encode_buffer_overflow
// Encoding to undersized buffer
// Expected: Error returned, no overflow
```

#### 5. Size Verification Tests

```c
// Test: size_updf_vs_json
// Compare protobuf size to JSON equivalent
// Expected: Protobuf < 30% of JSON size

// Test: size_jreq_vs_json
// Compare protobuf size to JSON equivalent
// Expected: Protobuf < 30% of JSON size

// Test: size_dnmsg_vs_json
// Compare protobuf size to JSON equivalent
// Expected: Protobuf < 30% of JSON size

// Test: size_packed_efficiency
// Verify varint packing for small values
// Expected: Small integers use minimal bytes
```

### Integration Tests (regr-tests/test-protobuf/)

#### 1. Negotiation Tests

```python
# test_nego_01_version_capabilities.py
# Verify station sends capabilities in version message
# Expected: {"capabilities": ["protobuf"]} present

# test_nego_02_lns_enables_protobuf.py
# Verify station switches to binary after router_config
# Expected: Subsequent messages are binary WebSocket frames

# test_nego_03_lns_no_protobuf.py
# Verify fallback when LNS doesn't enable protobuf
# Expected: Station continues with JSON

# test_nego_04_invalid_protocol_format.py
# Verify handling of unknown protocol_format value
# Expected: Station falls back to JSON

# test_nego_05_reconnect_renegotiate.py
# Verify re-negotiation after disconnect
# Expected: Protocol re-established correctly
```

#### 2. Uplink Flow Tests

```python
# test_uplink_01_data_frame.py
# Send simulated uplink, verify protobuf encoding
# Expected: Binary frame with correct TcMessage

# test_uplink_02_join_request.py
# Send simulated join, verify protobuf encoding
# Expected: JoinRequest message correct

# test_uplink_03_proprietary.py
# Send proprietary frame, verify encoding
# Expected: ProprietaryFrame message correct

# test_uplink_04_radio_metadata.py
# Verify all radio metadata fields transmitted
# Expected: RSSI, SNR, timestamps correct

# test_uplink_05_high_rate.py
# Send many uplinks rapidly
# Expected: All encoded correctly, no memory leaks
```

#### 3. Downlink Flow Tests

```python
# test_downlink_01_class_a.py
# Send protobuf downlink, verify station receives
# Expected: TX occurs in correct RX window

# test_downlink_02_class_c.py
# Send Class C downlink
# Expected: Immediate TX

# test_downlink_03_multicast.py
# Send dnsched with multiple entries
# Expected: All scheduled correctly

# test_downlink_04_tx_confirmation.py
# Verify dntxed sent as protobuf after TX
# Expected: Correct TxConfirmation message

# test_downlink_05_large_pdu.py
# Send maximum size PDU
# Expected: Complete PDU transmitted
```

#### 4. Mixed Protocol Tests

```python
# test_mixed_01_timesync.py
# Verify timesync works in protobuf mode
# Expected: Sync maintained

# test_mixed_02_error_messages.py
# Verify error handling in protobuf mode
# Expected: Errors reported correctly

# test_mixed_03_runcmd.py
# Verify runcmd works in protobuf mode
# Expected: Command executed

# test_mixed_04_rmtsh.py
# Verify remote shell in protobuf mode
# Expected: Session functional
```

#### 5. Backward Compatibility Tests

```python
# test_compat_01_json_lns.py
# Connect to JSON-only LNS
# Expected: Works normally, no protobuf

# test_compat_02_old_station.py
# Simulate old station (no capabilities)
# Expected: LNS works with JSON

# test_compat_03_upgrade_path.py
# Station upgrade scenario
# Expected: Smooth transition to protobuf

# test_compat_04_downgrade_path.py
# LNS downgrade scenario  
# Expected: Falls back to JSON
```

#### 6. Stress and Edge Case Tests

```python
# test_stress_01_sustained_traffic.py
# Hours of continuous traffic
# Expected: No memory growth, stable performance

# test_stress_02_burst_traffic.py
# Sudden traffic bursts
# Expected: All messages processed

# test_edge_01_connection_drop.py
# Connection drops mid-message
# Expected: Clean recovery

# test_edge_02_malformed_protobuf.py
# LNS sends malformed protobuf
# Expected: Error logged, connection maintained

# test_edge_03_partial_frame.py
# Incomplete WebSocket frame
# Expected: Handled gracefully
```

### Performance Tests

```python
# test_perf_01_encoding_latency.py
# Measure encoding time vs JSON
# Expected: Protobuf faster or equal

# test_perf_02_decoding_latency.py
# Measure decoding time vs JSON
# Expected: Protobuf faster

# test_perf_03_memory_usage.py
# Compare memory usage
# Expected: No significant increase

# test_perf_04_bandwidth_actual.py
# Measure actual bandwidth savings
# Expected: >70% reduction
```

### Test Coverage Requirements

- Line coverage: >90% for protobuf-related code
- Branch coverage: >85%
- All error paths tested
- All message types tested
- All field types tested (varint, fixed, bytes, nested)

## Dependencies

- **nanopb**: Lightweight C implementation of Protocol Buffers for embedded systems
  - Very small footprint (~16KB library code)
  - No dynamic memory allocation required (static allocation)
  - Supports proto3 including `oneof` and optional fields
  - Battle-tested: used in Android, ChromeOS, ARM products
  - OSS-Fuzz tested for security
  - Zlib license
  - https://github.com/nanopb/nanopb

### Why nanopb over protobuf-c?

| Aspect | nanopb | protobuf-c |
|--------|--------|------------|
| Code size | ~16KB | ~28KB |
| Memory | Static allocation | Dynamic allocation |
| Testing | OSS-Fuzz tested | Less extensive |
| Maintenance | Active development | Moderate |
| Proto3 support | Full | Full |

### Generated Code

The protocol is defined in `src/tc.proto`. Generated files:
- `src/tc.pb.h` - Type definitions and field descriptors
- `src/tc.pb.c` - Field descriptor bindings

To regenerate after schema changes:
```bash
cd src
python3 ../deps/nanopb/git-repo/generator/nanopb_generator.py tc.proto
```

The `.options` file (`src/tc.options`) controls static buffer sizes:
```
basicstation.UplinkDataFrame.frm_payload    max_size:256
basicstation.DownlinkMessage.pdu            max_size:256
# etc.
```

### LNS Implementation

LNS developers can use the standard `protoc` compiler with their language of choice:

```bash
# Rust
protoc --rust_out=. tc.proto

# Go
protoc --go_out=. tc.proto

# Java
protoc --java_out=. tc.proto

# C++
protoc --cpp_out=. tc.proto

# Python
protoc --python_out=. tc.proto
```

The wire format is 100% compatible - nanopb on the station produces standard protobuf 
that any compliant implementation can decode.

## Considerations

### Pros
- ~75% bandwidth reduction on data messages
- Lower latency (less parsing overhead)
- Backward compatible with existing LNS implementations
- Binary data (PDU, payload) sent as raw bytes instead of hex strings
- Standard `.proto` schema for cross-language support
- Well-tested library (nanopb) with OSS-Fuzz coverage
- Supports pdu-only mode for maximum efficiency (see [PDU-Only-Mode.md](PDU-Only-Mode.md))

### Cons
- Additional dependency (nanopb ~16KB)
- LNS must be updated to support binary mode
- Debugging requires protobuf-aware tools (e.g., `protoc --decode`)

### Alternatives Considered

1. **Hand-written encoder/decoder**: Initially implemented, but harder to maintain and test
2. **protobuf-c**: Larger footprint (~28KB vs ~16KB)
3. **MessagePack**: ~50% reduction, simpler but less efficient
4. **CBOR**: Similar to MessagePack, standardized (RFC 8949)
5. **Custom binary**: Maximum efficiency but non-standard
6. **Compression (gzip/zstd)**: Can be added on top of protobuf for additional savings

## Binary Size Impact

The protobuf feature adds approximately:
- nanopb library: ~16KB
- Generated descriptors (tc.pb.c): ~1KB  
- Wrapper code (tcpb.c): ~10KB
- **Total: ~27KB**

This can be disabled at compile time by removing `protobuf` from the `CFG` flags in `setup.gmk`.

## References

- [Protocol Buffers](https://protobuf.dev/)
- [nanopb](https://jpa.kapsi.fi/nanopb/) - Embedded protobuf implementation
- [nanopb GitHub](https://github.com/nanopb/nanopb)
- [LNS Protocol Documentation](https://doc.sm.tc/station/tcproto.html)
