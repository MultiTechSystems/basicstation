/*
 * --- Revised 3-Clause BSD License ---
 * Copyright MULTI-TECH SYSTEMS, INC. 2025. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification,
 * are permitted provided that the following conditions are met:
 *
 *     * Redistributions of source code must retain the above copyright notice,
 *       this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above copyright notice,
 *       this list of conditions and the following disclaimer in the documentation
 *       and/or other materials provided with the distribution.
 *     * Neither the name of MULTI-TECH SYSTEMS, INC. nor the names of its
 *       contributors may be used to endorse or promote products derived from this
 *       software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
 * ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL MULTI-TECH SYSTEMS, INC. BE LIABLE FOR ANY DIRECT,
 * INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
 * LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
 * OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
 * ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#if defined(CFG_selftests) && defined(CFG_protobuf)

#include <string.h>
#include <math.h>
#include "selftests.h"
#include "tcpb.h"
#include "rt.h"

// Helper to check double equality with tolerance
static int double_eq(double a, double b) {
    return fabs(a - b) < 1e-9;
}

// ============================================================================
// Encoding tests
// ============================================================================

static int test_encode_updf_minimal(void) {
    TSTART();
    
    u1_t buf[256];
    int len = tcpb_encUpdf(buf, sizeof(buf),
                           0x40,           // mhdr (unconfirmed data up)
                           0x01020304,     // devaddr
                           0x00,           // fctrl
                           42,             // fcnt
                           NULL, 0,        // fopts
                           -1,             // fport (none)
                           NULL, 0,        // payload
                           0x12345678,     // mic
                           5,              // dr
                           868100000,      // freq
                           0, 1234567890,  // rctx, xtime
                           0,              // gpstime (none)
                           -50,            // rssi
                           9.5,            // snr
                           -1,             // fts (none)
                           1706100000.123, // rxtime
                           1706100000.123); // reftime
    
    TCHECK(len > 0);
    TCHECK(len < 100);  // Should be much smaller than JSON equivalent
    LOG(MOD_SYS|INFO, "updf minimal encoded size: %d bytes", len);
    
    TDONE();
}

static int test_encode_updf_full(void) {
    TSTART();
    
    u1_t buf[512];
    u1_t fopts[] = {0x02, 0x03};
    u1_t payload[] = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08};
    
    int len = tcpb_encUpdf(buf, sizeof(buf),
                           0x40,           // mhdr
                           -123456,        // devaddr (negative)
                           0x80,           // fctrl
                           65535,          // fcnt (max 16-bit)
                           fopts, sizeof(fopts),
                           1,              // fport
                           payload, sizeof(payload),
                           -12345678,      // mic (negative)
                           5,              // dr
                           868100000,      // freq
                           123456789,      // rctx
                           9876543210123LL, // xtime
                           1234567890000000LL, // gpstime
                           -120,           // rssi
                           -5.5,           // snr (negative)
                           12345,          // fts
                           1706100000.123456,
                           1706100000.123456);
    
    TCHECK(len > 0);
    TCHECK(len < 150);  // Should still be compact
    LOG(MOD_SYS|INFO, "updf full encoded size: %d bytes", len);
    
    TDONE();
}

static int test_encode_updf_max_payload(void) {
    TSTART();
    
    u1_t buf[512];
    u1_t payload[242];  // Max LoRaWAN payload
    memset(payload, 0xAB, sizeof(payload));
    
    int len = tcpb_encUpdf(buf, sizeof(buf),
                           0x40, 0x01020304, 0x00, 42,
                           NULL, 0, 1,
                           payload, sizeof(payload),
                           0x12345678,
                           5, 868100000,
                           0, 1234567890, 0,
                           -50, 9.5, -1,
                           1706100000.0, 1706100000.0);
    
    TCHECK(len > 0);
    TCHECK(len < 350);  // Payload + overhead
    LOG(MOD_SYS|INFO, "updf max payload encoded size: %d bytes", len);
    
    TDONE();
}

static int test_encode_jreq_basic(void) {
    TSTART();
    
    u1_t buf[256];
    int len = tcpb_encJreq(buf, sizeof(buf),
                           0x00,                     // mhdr (join request)
                           0x0102030405060708ULL,    // joineui
                           0x0807060504030201ULL,    // deveui
                           12345,                    // devnonce
                           -12345678,                // mic
                           5, 868100000,
                           0, 1234567890, 1234567890000000LL,
                           -50, 9.5, -1,
                           1706100000.0, 1706100000.0);
    
    TCHECK(len > 0);
    TCHECK(len < 120);  // Join requests with radio metadata
    LOG(MOD_SYS|INFO, "jreq encoded size: %d bytes", len);
    
    TDONE();
}

static int test_encode_jreq_edge_cases(void) {
    TSTART();
    
    u1_t buf[256];
    
    // All zeros
    int len1 = tcpb_encJreq(buf, sizeof(buf),
                            0x00, 0, 0, 0, 0,
                            0, 0, 0, 0, 0, 0, 0.0, 0, 0.0, 0.0);
    TCHECK(len1 > 0);
    
    // All ones
    int len2 = tcpb_encJreq(buf, sizeof(buf),
                            0xFF,
                            0xFFFFFFFFFFFFFFFFULL,
                            0xFFFFFFFFFFFFFFFFULL,
                            65535, -1,
                            15, 999999999,
                            0x7FFFFFFFFFFFFFFFLL, 0x7FFFFFFFFFFFFFFFLL,
                            0x7FFFFFFFFFFFFFFFLL,
                            -140, 20.0, 0x7FFFFFFF,
                            9999999999.999999, 9999999999.999999);
    TCHECK(len2 > 0);
    
    TDONE();
}

static int test_encode_propdf(void) {
    TSTART();
    
    u1_t buf[256];
    u1_t payload[] = {0xE0, 0x01, 0x02, 0x03, 0x04, 0x05};  // Proprietary frame
    
    int len = tcpb_encPropdf(buf, sizeof(buf),
                             payload, sizeof(payload),
                             5, 868100000,
                             0, 1234567890, 0,
                             -50, 9.5, -1,
                             1706100000.0, 1706100000.0);
    
    TCHECK(len > 0);
    TCHECK(len < 80);
    LOG(MOD_SYS|INFO, "propdf encoded size: %d bytes", len);
    
    TDONE();
}

static int test_encode_dntxed(void) {
    TSTART();
    
    u1_t buf[128];
    int len = tcpb_encDntxed(buf, sizeof(buf),
                             123456,                    // diid
                             0x0807060504030201ULL,     // deveui
                             0,                         // rctx
                             1234567890123LL,           // xtime
                             1706100000.123456,         // txtime
                             1234567890000000LL);       // gpstime
    
    TCHECK(len > 0);
    TCHECK(len < 60);
    LOG(MOD_SYS|INFO, "dntxed encoded size: %d bytes", len);
    
    TDONE();
}

static int test_encode_timesync(void) {
    TSTART();
    
    u1_t buf[64];
    int len = tcpb_encTimesync(buf, sizeof(buf), 1706100000.123456);
    
    TCHECK(len > 0);
    TCHECK(len < 20);  // Timesync is very small
    LOG(MOD_SYS|INFO, "timesync encoded size: %d bytes", len);
    
    TDONE();
}

static int test_encode_buffer_overflow(void) {
    TSTART();
    
    u1_t buf[10];  // Too small
    u1_t payload[] = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08};
    
    int len = tcpb_encUpdf(buf, sizeof(buf),
                           0x40, 0x01020304, 0x00, 42,
                           NULL, 0, 1,
                           payload, sizeof(payload),
                           0x12345678,
                           5, 868100000,
                           0, 1234567890, 0,
                           -50, 9.5, -1,
                           1706100000.0, 1706100000.0);
    
    TCHECK(len == -1);  // Should fail
    
    TDONE();
}

// ============================================================================
// Decoding tests
// ============================================================================

// Helper: manually construct a dnmsg protobuf message
static int make_test_dnmsg(u1_t* buf, int bufsize) {
    // This creates a minimal valid dnmsg for testing
    // TcMessage { type: MSG_DNMSG(10), dnmsg: DownlinkMessage {...} }
    int pos = 0;
    
    // Field 1: type = 10 (MSG_DNMSG)
    buf[pos++] = (1 << 3) | 0;  // tag: field 1, varint
    buf[pos++] = 10;            // value: 10
    
    // Field 10: dnmsg submessage
    buf[pos++] = (10 << 3) | 2;  // tag: field 10, length-delimited
    
    // Build submessage in temp buffer
    u1_t sub[128];
    int subpos = 0;
    
    // deveui (field 1, fixed64) - little-endian encoded
    sub[subpos++] = (1 << 3) | 1;  // tag
    // DevEUI 0x0102030405060708 encoded as little-endian fixed64
    sub[subpos++] = 0x08; sub[subpos++] = 0x07; sub[subpos++] = 0x06; sub[subpos++] = 0x05;
    sub[subpos++] = 0x04; sub[subpos++] = 0x03; sub[subpos++] = 0x02; sub[subpos++] = 0x01;
    
    // dc (field 2, varint)
    sub[subpos++] = (2 << 3) | 0;
    sub[subpos++] = 0;  // Class A
    
    // diid (field 3, varint - zigzag)
    sub[subpos++] = (3 << 3) | 0;
    sub[subpos++] = 0xC0; sub[subpos++] = 0xC4; sub[subpos++] = 0x07;  // 123456 zigzag
    
    // pdu (field 4, bytes)
    sub[subpos++] = (4 << 3) | 2;
    sub[subpos++] = 5;  // length
    sub[subpos++] = 0x60; sub[subpos++] = 0x01; sub[subpos++] = 0x02;
    sub[subpos++] = 0x03; sub[subpos++] = 0x04;
    
    // rxdelay (field 5)
    sub[subpos++] = (5 << 3) | 0;
    sub[subpos++] = 1;
    
    // rx1dr (field 6)
    sub[subpos++] = (6 << 3) | 0;
    sub[subpos++] = 5;
    
    // rx1freq (field 7)
    sub[subpos++] = (7 << 3) | 0;
    sub[subpos++] = 0x90; sub[subpos++] = 0xEC; sub[subpos++] = 0x93;
    sub[subpos++] = 0xDB; sub[subpos++] = 0x03;  // 868100000
    
    // Write submessage length and content
    buf[pos++] = (u1_t)subpos;
    memcpy(buf + pos, sub, subpos);
    pos += subpos;
    
    return pos;
}

static int test_decode_dnmsg_basic(void) {
    TSTART();
    
    u1_t buf[256];
    int len = make_test_dnmsg(buf, sizeof(buf));
    TCHECK(len > 0);
    
    tcpb_dnmsg_t msg;
    tcpb_msgtype_t type = tcpb_decode(buf, len, &msg);
    
    TCHECK(type == TCPB_MSG_DNMSG);
    TCHECK(msg.deveui == 0x0102030405060708ULL);
    TCHECK(msg.dclass == 0);
    TCHECK(msg.diid == 123456);
    TCHECK(msg.pdulen == 5);
    TCHECK(msg.pdu != NULL);
    TCHECK(msg.pdu[0] == 0x60);
    TCHECK(msg.rxdelay == 1);
    TCHECK(msg.rx1dr == 5);
    TCHECK(msg.rx1freq == 868100000);
    
    tcpb_freeDnmsg(&msg);
    
    TDONE();
}

static int test_decode_truncated(void) {
    TSTART();
    
    u1_t buf[256];
    int len = make_test_dnmsg(buf, sizeof(buf));
    
    // Truncate the message
    tcpb_dnmsg_t msg;
    tcpb_msgtype_t type = tcpb_decode(buf, len / 2, &msg);
    
    // Should either return error or partial data
    // The key is it shouldn't crash
    if (type == TCPB_MSG_DNMSG) {
        tcpb_freeDnmsg(&msg);
    }
    
    TDONE();
}

static int test_decode_empty(void) {
    TSTART();
    
    tcpb_dnmsg_t msg;
    tcpb_msgtype_t type = tcpb_decode(NULL, 0, &msg);
    
    TCHECK(type == TCPB_MSG_ERROR);
    
    TDONE();
}

// ============================================================================
// Size comparison tests
// ============================================================================

static int test_size_comparison_updf(void) {
    TSTART();
    
    u1_t buf[512];
    u1_t payload[] = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08};
    
    int pb_size = tcpb_encUpdf(buf, sizeof(buf),
                               0x40, 0x01020304, 0x00, 42,
                               NULL, 0, 1,
                               payload, sizeof(payload),
                               -12345678,
                               5, 868100000,
                               0, 1234567890123LL, 1234567890000000LL,
                               -50, 9.5, -1,
                               1706100000.123456, 1706100000.123456);
    
    // Equivalent JSON would be ~270 bytes
    int json_size = 270;
    
    TCHECK(pb_size > 0);
    TCHECK(pb_size < json_size * 0.35);  // At least 65% reduction
    
    LOG(MOD_SYS|INFO, "updf size comparison: protobuf=%d, json~=%d, reduction=%.1f%%",
        pb_size, json_size, 100.0 * (1.0 - (double)pb_size / json_size));
    
    TDONE();
}

static int test_size_comparison_jreq(void) {
    TSTART();
    
    u1_t buf[256];
    int pb_size = tcpb_encJreq(buf, sizeof(buf),
                               0x00,
                               0x0102030405060708ULL,
                               0x0807060504030201ULL,
                               12345, -12345678,
                               5, 868100000,
                               0, 1234567890123LL, 1234567890000000LL,
                               -50, 9.5, -1,
                               1706100000.123456, 1706100000.123456);
    
    // Equivalent JSON would be ~230 bytes
    int json_size = 230;
    
    TCHECK(pb_size > 0);
    TCHECK(pb_size < json_size * 0.35);
    
    LOG(MOD_SYS|INFO, "jreq size comparison: protobuf=%d, json~=%d, reduction=%.1f%%",
        pb_size, json_size, 100.0 * (1.0 - (double)pb_size / json_size));
    
    TDONE();
}

// ============================================================================
// PDU-only mode tests
// ============================================================================

static int test_encode_pdu_only(void) {
    TSTART();
    
    u1_t buf_parsed[512];
    u1_t buf_pdu_only[512];
    
    // Build a 24-byte PDU: MHdr + DevAddr + FCtrl + FCnt + FPort + Payload(11) + MIC
    u1_t pdu[24] = {
        0x40,                               // MHdr
        0x04, 0x03, 0x02, 0x01,            // DevAddr (little-endian)
        0x80,                               // FCtrl
        0xD2, 0x04,                         // FCnt = 1234 (little-endian)
        0x01,                               // FPort
        0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,  // Payload
        0x78, 0x56, 0x34, 0x12             // MIC (little-endian)
    };
    u1_t payload[] = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B};
    
    // Encode in parsed mode
    int len_parsed = tcpb_encUpdf(buf_parsed, sizeof(buf_parsed),
                                   0x40, 0x01020304, 0x80, 1234,
                                   NULL, 0, 1,
                                   payload, sizeof(payload),
                                   0x12345678,
                                   3, 903100000,
                                   0, 0x300000001234LL, 1390852367000000LL,
                                   -95, 7.5, -1,
                                   1706234567.123456, 1706234567.123456);
    
    // Encode in pdu-only mode
    int len_pdu_only = tcpb_encUpdfPduOnly(buf_pdu_only, sizeof(buf_pdu_only),
                                            pdu, sizeof(pdu),
                                            3, 903100000,
                                            0, 0x300000001234LL, 1390852367000000LL,
                                            -95, 7.5, -1,
                                            1706234567.123456, 1706234567.123456);
    
    TCHECK(len_parsed > 0);
    TCHECK(len_pdu_only > 0);
    
    // PDU-only should be smaller (no parsed fields, just raw pdu + metadata)
    LOG(MOD_SYS|INFO, "PDU-only comparison: parsed=%d, pdu_only=%d, diff=%d bytes",
        len_parsed, len_pdu_only, len_parsed - len_pdu_only);
    
    // Both should be much smaller than JSON (~325 bytes)
    TCHECK(len_parsed < 120);
    TCHECK(len_pdu_only < 100);
    
    TDONE();
}

// ============================================================================
// Protocol format tests
// ============================================================================

static int test_protocol_format(void) {
    TSTART();
    
    // Initially should be JSON
    TCHECK(tcpb_protocol_format == TCPROTO_JSON);
    TCHECK(tcpb_enabled() == 0);
    
    // Set to protobuf
    tcpb_setFormat("protobuf");
    TCHECK(tcpb_protocol_format == TCPROTO_PROTOBUF);
    TCHECK(tcpb_enabled() == 1);
    
    // Set to JSON
    tcpb_setFormat("json");
    TCHECK(tcpb_protocol_format == TCPROTO_JSON);
    TCHECK(tcpb_enabled() == 0);
    
    // Unknown format defaults to JSON
    tcpb_setFormat("unknown");
    TCHECK(tcpb_protocol_format == TCPROTO_JSON);
    
    // NULL defaults to JSON
    tcpb_setFormat(NULL);
    TCHECK(tcpb_protocol_format == TCPROTO_JSON);
    
    TDONE();
}

// ============================================================================
// Test runner
// ============================================================================

int selftest_tcpb(void) {
    int errs = 0;
    
    LOG(MOD_SYS|INFO, "Running protobuf TC protocol tests...");
    
    // Encoding tests
    errs += test_encode_updf_minimal();
    errs += test_encode_updf_full();
    errs += test_encode_updf_max_payload();
    errs += test_encode_jreq_basic();
    errs += test_encode_jreq_edge_cases();
    errs += test_encode_propdf();
    errs += test_encode_dntxed();
    errs += test_encode_timesync();
    errs += test_encode_buffer_overflow();
    
    // Decoding tests
    errs += test_decode_dnmsg_basic();
    errs += test_decode_truncated();
    errs += test_decode_empty();
    
    // Size comparison tests
    errs += test_size_comparison_updf();
    errs += test_size_comparison_jreq();
    
    // PDU-only mode tests
    errs += test_encode_pdu_only();
    
    // Protocol format tests
    errs += test_protocol_format();
    
    LOG(MOD_SYS|INFO, "Protobuf TC tests complete: %d errors", errs);
    
    return errs;
}

#endif // CFG_selftests && CFG_protobuf
