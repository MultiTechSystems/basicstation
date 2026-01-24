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

#ifndef _tcpb_h_
#define _tcpb_h_

#if defined(CFG_protobuf)

#include "s2conf.h"
#include "s2e.h"

// Protocol format modes
enum {
    TCPROTO_JSON = 0,     // Default JSON format
    TCPROTO_PROTOBUF = 1  // Binary protobuf format
};

// Global protocol format state (set by router_config)
extern u1_t tcpb_protocol_format;

// Feature capability string for version message
#define TCPB_CAPABILITY "protobuf"

// Initialize protobuf module
void tcpb_ini(void);

// Check if protobuf mode is enabled
#define tcpb_enabled() (tcpb_protocol_format == TCPROTO_PROTOBUF)

// Set protocol format based on router_config
void tcpb_setFormat(const char* format);

// ============================================================================
// Encoding functions - Station -> LNS
// ============================================================================

// Encode uplink data frame (updf) to protobuf
// Returns encoded size, or -1 on error
int tcpb_encUpdf(u1_t* buf, int bufsize,
                 u1_t mhdr, s4_t devaddr, u1_t fctrl, u2_t fcnt,
                 const u1_t* fopts, int foptslen,
                 int fport,
                 const u1_t* payload, int payloadlen,
                 s4_t mic,
                 u1_t dr, u4_t freq,
                 sL_t rctx, sL_t xtime, sL_t gpstime,
                 s2_t rssi, float snr, s4_t fts,
                 double rxtime, double reftime);

// Encode join request (jreq) to protobuf
int tcpb_encJreq(u1_t* buf, int bufsize,
                 u1_t mhdr, uL_t joineui, uL_t deveui,
                 u2_t devnonce, s4_t mic,
                 u1_t dr, u4_t freq,
                 sL_t rctx, sL_t xtime, sL_t gpstime,
                 s2_t rssi, float snr, s4_t fts,
                 double rxtime, double reftime);

// Encode proprietary frame (propdf) to protobuf
int tcpb_encPropdf(u1_t* buf, int bufsize,
                   const u1_t* payload, int payloadlen,
                   u1_t dr, u4_t freq,
                   sL_t rctx, sL_t xtime, sL_t gpstime,
                   s2_t rssi, float snr, s4_t fts,
                   double rxtime, double reftime);

// Encode TX confirmation (dntxed) to protobuf
int tcpb_encDntxed(u1_t* buf, int bufsize,
                   sL_t diid, uL_t deveui,
                   sL_t rctx, sL_t xtime,
                   double txtime, sL_t gpstime);

// Encode timesync request to protobuf
int tcpb_encTimesync(u1_t* buf, int bufsize, double txtime);

// Encode uplink in PDU-only mode (raw PHYPayload without parsing)
// This is more efficient than tcpb_encRawFrame as it doesn't parse LoRaWAN fields
int tcpb_encUpdfPduOnly(u1_t* buf, int bufsize,
                        const u1_t* pdu, int pdulen,
                        u1_t dr, u4_t freq,
                        sL_t rctx, sL_t xtime, sL_t gpstime,
                        s2_t rssi, float snr, s4_t fts,
                        double rxtime, double reftime);

// Encode raw LoRaWAN frame to protobuf (auto-detects frame type)
// Returns encoded size, or -1 on error (invalid frame)
int tcpb_encRawFrame(u1_t* buf, int bufsize,
                     const u1_t* frame, int framelen,
                     u1_t dr, u4_t freq,
                     sL_t rctx, sL_t xtime, sL_t gpstime,
                     s2_t rssi, float snr, s4_t fts,
                     double rxtime, double reftime);

// ============================================================================
// Decoding functions - LNS -> Station
// ============================================================================

// Decoded downlink message structure
typedef struct {
    uL_t   deveui;
    u1_t   dclass;       // 0=A, 1=B, 2=C
    sL_t   diid;
    u1_t*  pdu;
    int    pdulen;
    u1_t   rxdelay;
    u1_t   rx1dr;
    u4_t   rx1freq;
    u1_t   rx2dr;
    u4_t   rx2freq;
    u1_t   priority;
    sL_t   xtime;
    sL_t   rctx;
    sL_t   gpstime;
    u1_t   dr;           // Override for Class B/C
    u4_t   freq;         // Override for Class B/C
    double muxtime;
} tcpb_dnmsg_t;

// Decoded timesync response structure
typedef struct {
    double txtime;    // Original txtime echoed back (for round-trip calculation)
    sL_t gpstime;
    sL_t xtime;
} tcpb_timesync_resp_t;

// Decoded run command structure
typedef struct {
    char*  command;   // Command to execute
    int    argc;      // Number of arguments
    char** argv;      // Arguments array
} tcpb_runcmd_t;

// Decoded remote shell structure
typedef struct {
    char* user;       // User operating the session
    char* term;       // TERM environment variable
    int   start;      // 1 to start session
    int   stop;       // 1 to stop session
    u1_t* data;
    int   datalen;
} tcpb_rmtsh_t;

// Message type returned by decode
typedef enum {
    TCPB_MSG_UNKNOWN = 0,
    TCPB_MSG_DNMSG,
    TCPB_MSG_DNSCHED,
    TCPB_MSG_TIMESYNC_RESP,
    TCPB_MSG_RUNCMD,
    TCPB_MSG_RMTSH,
    TCPB_MSG_ERROR = -1
} tcpb_msgtype_t;

// Decode a protobuf message from LNS
// Returns message type, fills in appropriate structure
tcpb_msgtype_t tcpb_decode(const u1_t* data, int datalen, void* result);

// Free resources allocated during decode
void tcpb_freeDnmsg(tcpb_dnmsg_t* msg);
void tcpb_freeRuncmd(tcpb_runcmd_t* msg);
void tcpb_freeRmtsh(tcpb_rmtsh_t* msg);

#else // !CFG_protobuf

// Stubs when protobuf is disabled
#define tcpb_protocol_format 0
#define tcpb_enabled() 0
#define tcpb_ini()
#define tcpb_setFormat(f)

#endif // CFG_protobuf

#endif // _tcpb_h_
