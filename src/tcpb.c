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

#if defined(CFG_protobuf)

#include "tcpb.h"
#include "tc.pb.h"
#include "rt.h"
#include "pb_encode.h"
#include "pb_decode.h"
#include <string.h>

// Global protocol format
u1_t tcpb_protocol_format = TCPROTO_JSON;

void tcpb_ini(void) {
    tcpb_protocol_format = TCPROTO_JSON;
}

void tcpb_setFormat(const char* format) {
    if (format && strcmp(format, "protobuf") == 0) {
        tcpb_protocol_format = TCPROTO_PROTOBUF;
        LOG(MOD_S2E|INFO, "TC protocol format set to PROTOBUF");
    } else {
        tcpb_protocol_format = TCPROTO_JSON;
        LOG(MOD_S2E|INFO, "TC protocol format set to JSON");
    }
}

// ============================================================================
// Helper to fill RadioMetadata
// ============================================================================

static void fill_radio_metadata(basicstation_RadioMetadata* rm,
                                u1_t dr, u4_t freq,
                                sL_t rctx, sL_t xtime, sL_t gpstime,
                                s2_t rssi, float snr, s4_t fts,
                                double rxtime) {
    rm->dr = dr;
    rm->freq = freq;
    rm->rctx = rctx;
    rm->xtime = xtime;
    rm->gpstime = gpstime;
    rm->rssi = rssi;
    rm->snr = snr;
    rm->fts = fts;
    rm->rxtime = rxtime;
}

// ============================================================================
// Encoding functions - Station -> LNS
// ============================================================================

int tcpb_encUpdf(u1_t* buf, int bufsize,
                 u1_t mhdr, s4_t devaddr, u1_t fctrl, u2_t fcnt,
                 const u1_t* fopts, int foptslen,
                 int fport,
                 const u1_t* payload, int payloadlen,
                 s4_t mic,
                 u1_t dr, u4_t freq,
                 sL_t rctx, sL_t xtime, sL_t gpstime,
                 s2_t rssi, float snr, s4_t fts,
                 double rxtime, double reftime) {
    
    basicstation_TcMessage msg = basicstation_TcMessage_init_zero;
    
    msg.msg_type = basicstation_MsgType_MSG_UPDF;
    msg.which_payload = basicstation_TcMessage_updf_tag;
    
    basicstation_UplinkDataFrame* updf = &msg.payload.updf;
    updf->mhdr = mhdr;
    updf->dev_addr = devaddr;
    updf->fctrl = fctrl;
    updf->fcnt = fcnt;
    updf->fport = fport;
    updf->mic = mic;
    updf->ref_time = reftime;
    
    // Copy fopts
    if (fopts && foptslen > 0) {
        int copylen = foptslen < (int)sizeof(updf->fopts.bytes) ? foptslen : (int)sizeof(updf->fopts.bytes);
        memcpy(updf->fopts.bytes, fopts, copylen);
        updf->fopts.size = copylen;
    }
    
    // Copy payload
    if (payload && payloadlen > 0) {
        int copylen = payloadlen < (int)sizeof(updf->frm_payload.bytes) ? payloadlen : (int)sizeof(updf->frm_payload.bytes);
        memcpy(updf->frm_payload.bytes, payload, copylen);
        updf->frm_payload.size = copylen;
    }
    
    // Radio metadata
    updf->has_upinfo = true;
    fill_radio_metadata(&updf->upinfo, dr, freq, rctx, xtime, gpstime, rssi, snr, fts, rxtime);
    
    // Encode
    pb_ostream_t stream = pb_ostream_from_buffer(buf, bufsize);
    if (!pb_encode(&stream, basicstation_TcMessage_fields, &msg)) {
        LOG(MOD_S2E|ERROR, "Failed to encode updf: %s", PB_GET_ERROR(&stream));
        return -1;
    }
    
    return stream.bytes_written;
}

int tcpb_encJreq(u1_t* buf, int bufsize,
                 u1_t mhdr, uL_t joineui, uL_t deveui,
                 u2_t devnonce, s4_t mic,
                 u1_t dr, u4_t freq,
                 sL_t rctx, sL_t xtime, sL_t gpstime,
                 s2_t rssi, float snr, s4_t fts,
                 double rxtime, double reftime) {
    
    basicstation_TcMessage msg = basicstation_TcMessage_init_zero;
    
    msg.msg_type = basicstation_MsgType_MSG_JREQ;
    msg.which_payload = basicstation_TcMessage_jreq_tag;
    
    basicstation_JoinRequest* jreq = &msg.payload.jreq;
    jreq->mhdr = mhdr;
    jreq->join_eui = joineui;
    jreq->dev_eui = deveui;
    jreq->dev_nonce = devnonce;
    jreq->mic = mic;
    jreq->ref_time = reftime;
    
    // Radio metadata
    jreq->has_upinfo = true;
    fill_radio_metadata(&jreq->upinfo, dr, freq, rctx, xtime, gpstime, rssi, snr, fts, rxtime);
    
    // Encode
    pb_ostream_t stream = pb_ostream_from_buffer(buf, bufsize);
    if (!pb_encode(&stream, basicstation_TcMessage_fields, &msg)) {
        LOG(MOD_S2E|ERROR, "Failed to encode jreq: %s", PB_GET_ERROR(&stream));
        return -1;
    }
    
    return stream.bytes_written;
}

int tcpb_encPropdf(u1_t* buf, int bufsize,
                   const u1_t* payload, int payloadlen,
                   u1_t dr, u4_t freq,
                   sL_t rctx, sL_t xtime, sL_t gpstime,
                   s2_t rssi, float snr, s4_t fts,
                   double rxtime, double reftime) {
    
    basicstation_TcMessage msg = basicstation_TcMessage_init_zero;
    
    msg.msg_type = basicstation_MsgType_MSG_PROPDF;
    msg.which_payload = basicstation_TcMessage_propdf_tag;
    
    basicstation_ProprietaryFrame* propdf = &msg.payload.propdf;
    propdf->ref_time = reftime;
    
    // Copy payload
    if (payload && payloadlen > 0) {
        int copylen = payloadlen < (int)sizeof(propdf->frm_payload.bytes) ? payloadlen : (int)sizeof(propdf->frm_payload.bytes);
        memcpy(propdf->frm_payload.bytes, payload, copylen);
        propdf->frm_payload.size = copylen;
    }
    
    // Radio metadata
    propdf->has_upinfo = true;
    fill_radio_metadata(&propdf->upinfo, dr, freq, rctx, xtime, gpstime, rssi, snr, fts, rxtime);
    
    // Encode
    pb_ostream_t stream = pb_ostream_from_buffer(buf, bufsize);
    if (!pb_encode(&stream, basicstation_TcMessage_fields, &msg)) {
        LOG(MOD_S2E|ERROR, "Failed to encode propdf: %s", PB_GET_ERROR(&stream));
        return -1;
    }
    
    return stream.bytes_written;
}

int tcpb_encDntxed(u1_t* buf, int bufsize,
                   sL_t diid, uL_t deveui,
                   sL_t rctx, sL_t xtime,
                   double txtime, sL_t gpstime) {
    
    basicstation_TcMessage msg = basicstation_TcMessage_init_zero;
    
    msg.msg_type = basicstation_MsgType_MSG_DNTXED;
    msg.which_payload = basicstation_TcMessage_dntxed_tag;
    
    basicstation_TxConfirmation* dntxed = &msg.payload.dntxed;
    dntxed->diid = diid;
    dntxed->dev_eui = deveui;
    dntxed->rctx = rctx;
    dntxed->xtime = xtime;
    dntxed->txtime = txtime;
    dntxed->gpstime = gpstime;
    
    // Encode
    pb_ostream_t stream = pb_ostream_from_buffer(buf, bufsize);
    if (!pb_encode(&stream, basicstation_TcMessage_fields, &msg)) {
        LOG(MOD_S2E|ERROR, "Failed to encode dntxed: %s", PB_GET_ERROR(&stream));
        return -1;
    }
    
    return stream.bytes_written;
}

int tcpb_encTimesync(u1_t* buf, int bufsize, double txtime) {
    basicstation_TcMessage msg = basicstation_TcMessage_init_zero;
    
    msg.msg_type = basicstation_MsgType_MSG_TIMESYNC;
    msg.which_payload = basicstation_TcMessage_timesync_tag;
    
    msg.payload.timesync.txtime = txtime;
    
    // Encode
    pb_ostream_t stream = pb_ostream_from_buffer(buf, bufsize);
    if (!pb_encode(&stream, basicstation_TcMessage_fields, &msg)) {
        LOG(MOD_S2E|ERROR, "Failed to encode timesync: %s", PB_GET_ERROR(&stream));
        return -1;
    }
    
    return stream.bytes_written;
}

// ============================================================================
// PDU-only mode encoding
// ============================================================================

int tcpb_encUpdfPduOnly(u1_t* buf, int bufsize,
                        const u1_t* pdu, int pdulen,
                        u1_t dr, u4_t freq,
                        sL_t rctx, sL_t xtime, sL_t gpstime,
                        s2_t rssi, float snr, s4_t fts,
                        double rxtime, double reftime) {
    
    basicstation_TcMessage msg = basicstation_TcMessage_init_zero;
    msg.msg_type = basicstation_MsgType_MSG_UPDF;
    msg.which_payload = basicstation_TcMessage_updf_tag;
    
    basicstation_UplinkDataFrame* updf = &msg.payload.updf;
    
    // Only set the pdu field, leave parsed fields at zero/default
    if (pdulen > 0 && pdulen <= sizeof(updf->pdu.bytes)) {
        memcpy(updf->pdu.bytes, pdu, pdulen);
        updf->pdu.size = pdulen;
    }
    
    // Fill radio metadata
    fill_radio_metadata(&updf->upinfo, dr, freq, rctx, xtime, gpstime, rssi, snr, fts, rxtime);
    updf->has_upinfo = true;
    updf->ref_time = reftime;
    
    // Encode
    pb_ostream_t stream = pb_ostream_from_buffer(buf, bufsize);
    if (!pb_encode(&stream, basicstation_TcMessage_fields, &msg)) {
        return -1;
    }
    
    return stream.bytes_written;
}

// ============================================================================
// Raw frame encoding (auto-detect frame type)
// ============================================================================

// LoRaWAN frame type definitions
#define MHDR_FTYPE  0xE0
#define MHDR_MAJOR  0x03
#define MAJOR_V1    0x00

#define FRMTYPE_JREQ   0x00
#define FRMTYPE_JACC   0x20
#define FRMTYPE_DAUP   0x40
#define FRMTYPE_DADN   0x60
#define FRMTYPE_DCUP   0x80
#define FRMTYPE_DCDN   0xA0
#define FRMTYPE_REJN   0xC0
#define FRMTYPE_PROP   0xE0

int tcpb_encRawFrame(u1_t* buf, int bufsize,
                     const u1_t* frame, int framelen,
                     u1_t dr, u4_t freq,
                     sL_t rctx, sL_t xtime, sL_t gpstime,
                     s2_t rssi, float snr, s4_t fts,
                     double rxtime, double reftime) {
    
    if (framelen == 0) {
        return -1;
    }
    
    u1_t mhdr = frame[0];
    u1_t ftype = mhdr & MHDR_FTYPE;
    
    // Proprietary frames
    if (ftype == FRMTYPE_PROP || ftype == FRMTYPE_JACC) {
        return tcpb_encPropdf(buf, bufsize, frame, framelen,
                              dr, freq, rctx, xtime, gpstime,
                              rssi, snr, fts, rxtime, reftime);
    }
    
    // Join request: MHDR(1) + JoinEUI(8) + DevEUI(8) + DevNonce(2) + MIC(4) = 23 bytes
    if (ftype == FRMTYPE_JREQ) {
        if (framelen < 23) {
            return -1;
        }
        
        uL_t joineui = rt_rlsbf8(&frame[1]);
        uL_t deveui = rt_rlsbf8(&frame[9]);
        u2_t devnonce = rt_rlsbf2(&frame[17]);
        s4_t mic = rt_rlsbf4(&frame[19]);
        
        return tcpb_encJreq(buf, bufsize, mhdr, joineui, deveui, devnonce, mic,
                            dr, freq, rctx, xtime, gpstime,
                            rssi, snr, fts, rxtime, reftime);
    }
    
    // Data frames (uplink): MHDR(1) + DevAddr(4) + FCtrl(1) + FCnt(2) + [FOpts] + [FPort] + [Payload] + MIC(4)
    if (ftype == FRMTYPE_DAUP || ftype == FRMTYPE_DCUP) {
        if (framelen < 12) {  // Minimum: MHDR + DevAddr + FCtrl + FCnt + MIC
            return -1;
        }
        
        s4_t devaddr = rt_rlsbf4(&frame[1]);
        u1_t fctrl = frame[5];
        u2_t fcnt = rt_rlsbf2(&frame[6]);
        int foptslen = fctrl & 0x0F;
        
        if (framelen < 8 + foptslen + 4) {
            return -1;
        }
        
        const u1_t* fopts = foptslen > 0 ? &frame[8] : NULL;
        int portoff = 8 + foptslen;
        s4_t mic = rt_rlsbf4(&frame[framelen - 4]);
        
        // Check if there's a port and payload
        int fport = -1;
        const u1_t* payload = NULL;
        int payloadlen = 0;
        
        if (portoff < framelen - 4) {
            fport = frame[portoff];
            if (portoff + 1 < framelen - 4) {
                payload = &frame[portoff + 1];
                payloadlen = framelen - 4 - portoff - 1;
            }
        }
        
        return tcpb_encUpdf(buf, bufsize,
                           mhdr, devaddr, fctrl, fcnt,
                           fopts, foptslen,
                           fport,
                           payload, payloadlen,
                           mic,
                           dr, freq, rctx, xtime, gpstime,
                           rssi, snr, fts, rxtime, reftime);
    }
    
    // Unknown frame type - encode as proprietary
    return tcpb_encPropdf(buf, bufsize, frame, framelen,
                          dr, freq, rctx, xtime, gpstime,
                          rssi, snr, fts, rxtime, reftime);
}

// ============================================================================
// Decoding functions - LNS -> Station
// ============================================================================

// Union for decoded message result
typedef union {
    tcpb_dnmsg_t dnmsg;
    tcpb_timesync_resp_t timesync;
    tcpb_runcmd_t runcmd;
    tcpb_rmtsh_t rmtsh;
} tcpb_decoded_t;

tcpb_msgtype_t tcpb_decode(const u1_t* data, int datalen, void* result) {
    basicstation_TcMessage msg = basicstation_TcMessage_init_zero;
    
    pb_istream_t stream = pb_istream_from_buffer(data, datalen);
    if (!pb_decode(&stream, basicstation_TcMessage_fields, &msg)) {
        LOG(MOD_S2E|ERROR, "Failed to decode protobuf message: %s", PB_GET_ERROR(&stream));
        return TCPB_MSG_ERROR;
    }
    
    switch (msg.msg_type) {
    case basicstation_MsgType_MSG_DNMSG: {
        if (msg.which_payload != basicstation_TcMessage_dnmsg_tag) {
            return TCPB_MSG_ERROR;
        }
        
        tcpb_dnmsg_t* dnmsg = (tcpb_dnmsg_t*)result;
        basicstation_DownlinkMessage* src = &msg.payload.dnmsg;
        
        dnmsg->deveui = src->dev_eui;
        dnmsg->dclass = (u1_t)src->dc;
        dnmsg->diid = src->diid;
        dnmsg->rxdelay = src->rx_delay;
        dnmsg->rx1dr = src->rx1_dr;
        dnmsg->rx1freq = src->rx1_freq;
        dnmsg->rx2dr = src->rx2_dr;
        dnmsg->rx2freq = src->rx2_freq;
        dnmsg->priority = src->priority;
        dnmsg->xtime = src->xtime;
        dnmsg->rctx = src->rctx;
        dnmsg->gpstime = src->gpstime;
        dnmsg->dr = src->dr;
        dnmsg->freq = src->freq;
        dnmsg->muxtime = src->mux_time;
        
        // Copy PDU - allocate memory
        if (src->pdu.size > 0) {
            dnmsg->pdu = rt_mallocN(u1_t, src->pdu.size);
            if (dnmsg->pdu) {
                memcpy(dnmsg->pdu, src->pdu.bytes, src->pdu.size);
                dnmsg->pdulen = src->pdu.size;
            } else {
                dnmsg->pdulen = 0;
            }
        } else {
            dnmsg->pdu = NULL;
            dnmsg->pdulen = 0;
        }
        
        return TCPB_MSG_DNMSG;
    }
    
    case basicstation_MsgType_MSG_TIMESYNC_RESP: {
        if (msg.which_payload != basicstation_TcMessage_timesync_tag) {
            return TCPB_MSG_ERROR;
        }
        
        tcpb_timesync_resp_t* ts = (tcpb_timesync_resp_t*)result;
        ts->txtime = msg.payload.timesync.txtime;
        ts->gpstime = msg.payload.timesync.gpstime;
        ts->xtime = msg.payload.timesync.xtime;
        
        return TCPB_MSG_TIMESYNC_RESP;
    }
    
    case basicstation_MsgType_MSG_RUNCMD: {
        if (msg.which_payload != basicstation_TcMessage_runcmd_tag) {
            return TCPB_MSG_ERROR;
        }
        
        tcpb_runcmd_t* cmd = (tcpb_runcmd_t*)result;
        basicstation_RunCommand* src = &msg.payload.runcmd;
        
        // Copy command string
        int cmdlen = strlen(src->command);
        if (cmdlen > 0) {
            cmd->command = rt_mallocN(char, cmdlen + 1);
            if (cmd->command) {
                strcpy(cmd->command, src->command);
            }
        } else {
            cmd->command = NULL;
        }
        
        // Copy arguments
        cmd->argc = src->arguments_count;
        if (cmd->argc > 0) {
            cmd->argv = rt_mallocN(char*, cmd->argc);
            if (cmd->argv) {
                for (int i = 0; i < cmd->argc; i++) {
                    int len = strlen(src->arguments[i]);
                    cmd->argv[i] = rt_mallocN(char, len + 1);
                    if (cmd->argv[i]) {
                        strcpy(cmd->argv[i], src->arguments[i]);
                    }
                }
            }
        } else {
            cmd->argv = NULL;
        }
        
        return TCPB_MSG_RUNCMD;
    }
    
    case basicstation_MsgType_MSG_RMTSH: {
        if (msg.which_payload != basicstation_TcMessage_rmtsh_tag) {
            return TCPB_MSG_ERROR;
        }
        
        tcpb_rmtsh_t* rmtsh = (tcpb_rmtsh_t*)result;
        basicstation_RemoteShell* src = &msg.payload.rmtsh;
        
        // Copy user string
        int userlen = strlen(src->user);
        if (userlen > 0) {
            rmtsh->user = rt_mallocN(char, userlen + 1);
            if (rmtsh->user) {
                strcpy(rmtsh->user, src->user);
            }
        } else {
            rmtsh->user = NULL;
        }
        
        // Copy term string
        int termlen = strlen(src->term);
        if (termlen > 0) {
            rmtsh->term = rt_mallocN(char, termlen + 1);
            if (rmtsh->term) {
                strcpy(rmtsh->term, src->term);
            }
        } else {
            rmtsh->term = NULL;
        }
        
        rmtsh->start = src->start ? 1 : 0;
        rmtsh->stop = src->stop ? 1 : 0;
        
        if (src->data.size > 0) {
            rmtsh->data = rt_mallocN(u1_t, src->data.size);
            if (rmtsh->data) {
                memcpy(rmtsh->data, src->data.bytes, src->data.size);
                rmtsh->datalen = src->data.size;
            } else {
                rmtsh->datalen = 0;
            }
        } else {
            rmtsh->data = NULL;
            rmtsh->datalen = 0;
        }
        
        return TCPB_MSG_RMTSH;
    }
    
    default:
        LOG(MOD_S2E|WARNING, "Unknown protobuf message type: %d", msg.msg_type);
        return TCPB_MSG_UNKNOWN;
    }
}

// ============================================================================
// Memory cleanup functions
// ============================================================================

void tcpb_freeDnmsg(tcpb_dnmsg_t* msg) {
    if (msg && msg->pdu) {
        rt_free(msg->pdu);
        msg->pdu = NULL;
        msg->pdulen = 0;
    }
}

void tcpb_freeRuncmd(tcpb_runcmd_t* msg) {
    if (msg) {
        if (msg->command) {
            rt_free(msg->command);
            msg->command = NULL;
        }
        if (msg->argv) {
            for (int i = 0; i < msg->argc; i++) {
                if (msg->argv[i]) {
                    rt_free(msg->argv[i]);
                }
            }
            rt_free(msg->argv);
            msg->argv = NULL;
        }
        msg->argc = 0;
    }
}

void tcpb_freeRmtsh(tcpb_rmtsh_t* msg) {
    if (msg) {
        if (msg->user) {
            rt_free(msg->user);
            msg->user = NULL;
        }
        if (msg->term) {
            rt_free(msg->term);
            msg->term = NULL;
        }
        if (msg->data) {
            rt_free(msg->data);
            msg->data = NULL;
        }
        msg->datalen = 0;
    }
}

#endif // CFG_protobuf
