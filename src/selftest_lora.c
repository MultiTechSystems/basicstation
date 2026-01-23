/*
 * --- Revised 3-Clause BSD License ---
 * Copyright Semtech Corporation 2022. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification,
 * are permitted provided that the following conditions are met:
 *
 *     * Redistributions of source code must retain the above copyright notice,
 *       this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above copyright notice,
 *       this list of conditions and the following disclaimer in the documentation
 *       and/or other materials provided with the distribution.
 *     * Neither the name of the Semtech corporation nor the names of its
 *       contributors may be used to endorse or promote products derived from this
 *       software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
 * ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL SEMTECH CORPORATION. BE LIABLE FOR ANY DIRECT,
 * INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
 * LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
 * OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
 * ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#include "selftests.h"
#include "s2e.h"

#define BUFSZ (2*1024)

static const uL_t euiFilter1[] = { 0xEFCDAB8967452300, 0xEFCDAB8967452300, 0 };
static const uL_t euiFilter2[] = { 0xEFCDAB8967452300, 0xEFCDAB8967452301, 0 };


void selftest_lora () {
    char* jsonbuf = rt_mallocN(char, BUFSZ);

    ujbuf_t B = { .buf = jsonbuf, .bufsize = BUFSZ, .pos = 0 };
    const char* T;
    uL_t joineuiFilter[2*10+2] = { 0, 0 };
    s2e_joineuiFilter = joineuiFilter;

    T = "\x00_______________";  // too short
    TCHECK(!s2e_parse_lora_frame(&B, (const u1_t*)T, 1, NULL));
    T = "\x03_______________";  // bad major version
    TCHECK(!s2e_parse_lora_frame(&B, (const u1_t*)T, 16, NULL));

    B.pos = 0;
    T = "\x20_______________";  // join accept
    TCHECK(s2e_parse_lora_frame(&B, (const u1_t*)T, 16, NULL));
    xeos(&B);
    TCHECK(strcmp("\"msgtype\":\"jacc\",\"FRMPayload\":\"205F5F5F5F5F5F5F5F5F5F5F5F5F5F5F\"", B.buf) == 0);

    B.pos = 0;
    T = "\xE0_______________";  // proprietary frame
    TCHECK(s2e_parse_lora_frame(&B, (const u1_t*)T, 16, NULL));
    xeos(&B);
    TCHECK(strcmp("\"msgtype\":\"propdf\",\"FRMPayload\":\"E05F5F5F5F5F5F5F5F5F5F5F5F5F5F5F\"", B.buf) == 0);

    B.pos = 0;
    const char* Tjreq = "\x00\x01\x23\x45\x67\x89\xAB\xCD\xEF\xF1\xE3\xF5\xE7\xF9\xEB\xFD\xEF\xF0\xF1\xA0\xA1\xA2\xA3";  // jreq
    TCHECK(s2e_parse_lora_frame(&B, (const u1_t*)Tjreq, 23, NULL));
    xeos(&B);
    TCHECK(strcmp("\"msgtype\":\"jreq\",\"MHdr\":0,"
                  "\"JoinEui\":\"EF-CD-AB-89-67-45-23-01\","
                  "\"DevEui\":\"EF-FD-EB-F9-E7-F5-E3-F1\","
                  "\"DevNonce\":61936,\"MIC\":-1549622880", B.buf) == 0);
    // Too short
    B.pos = 0;
    TCHECK(!s2e_parse_lora_frame(&B, (const u1_t*)Tjreq, 22, NULL));
    // Filter enabled
    B.pos = 0;
    memcpy(s2e_joineuiFilter, euiFilter1, sizeof(euiFilter1));  // jreq removed
    TCHECK(!s2e_parse_lora_frame(&B, (const u1_t*)Tjreq, 23, NULL));
    B.pos = 0;
    memcpy(s2e_joineuiFilter, euiFilter2, sizeof(euiFilter2));  // jreq passes
    TCHECK(s2e_parse_lora_frame(&B, (const u1_t*)Tjreq, 23, NULL));
    s2e_joineuiFilter[0] = 0;

    B.pos = 0;
    const char* Tdaup1 = "\x40\xAB\xCD\xEF\xFF\x01\xF3\xF4\xFF\x20\x21\x22\xA0\xA1\xA2\xA3";  // daup
    TCHECK(s2e_parse_lora_frame(&B, (const u1_t*)Tdaup1, 12+1+3, NULL));
    xeos(&B);
    TCHECK(strcmp("\"msgtype\":\"updf\","
                  "\"MHdr\":64,\"DevAddr\":-1061461,\"FCtrl\":1,\"FCnt\":62707,"
                  "\"FOpts\":\"FF\",\"FPort\":32,\"FRMPayload\":\"2122\","
                  "\"MIC\":-1549622880", B.buf) == 0);
    // Too short
    B.pos = 0;
    TCHECK(!s2e_parse_lora_frame(&B, (const u1_t*)Tdaup1, 12, NULL));
    // Filtered
    B.pos = 0;
    s2e_netidFilter[0] = s2e_netidFilter[1] = s2e_netidFilter[2] = s2e_netidFilter[3] = 0;
    TCHECK(!s2e_parse_lora_frame(&B, (const u1_t*)Tdaup1, 12+1+3, NULL));

    // Reset filters for rejoin tests
    s2e_netidFilter[0] = s2e_netidFilter[1] = s2e_netidFilter[2] = s2e_netidFilter[3] = 0xFFFFFFFF;
    s2e_joineuiFilter[0] = 0;

    // ========================================================================
    // Rejoin Request Tests
    // ========================================================================

    // Rejoin Type 0: MHdr(1) + RJType(1) + NetID(3) + DevEUI(8) + RJcount0(2) + MIC(4) = 19 bytes
    B.pos = 0;
    const u1_t Trejoin0[] = {
        0xC0,                                           // MHdr (rejoin)
        0x00,                                           // RJType = 0
        0x01, 0x02, 0x03,                               // NetID (little endian)
        0xF1, 0xE3, 0xF5, 0xE7, 0xF9, 0xEB, 0xFD, 0xEF, // DevEUI
        0x10, 0x20,                                     // RJcount0
        0xA0, 0xA1, 0xA2, 0xA3                          // MIC
    };
    TCHECK(s2e_parse_lora_frame(&B, Trejoin0, 19, NULL));
    xeos(&B);
    TCHECK(strstr(B.buf, "\"msgtype\":\"rejoin\"") != NULL);
    TCHECK(strstr(B.buf, "\"MHdr\":192") != NULL);
    TCHECK(strstr(B.buf, "\"pdu\":\"C00001020") != NULL);  // Starts with MHdr + RJType + NetID start
    TCHECK(strstr(B.buf, "\"MIC\":-1549622880") != NULL);

    // Rejoin Type 1: MHdr(1) + RJType(1) + JoinEUI(8) + DevEUI(8) + RJcount1(2) + MIC(4) = 24 bytes
    B.pos = 0;
    const u1_t Trejoin1[] = {
        0xC0,                                           // MHdr (rejoin)
        0x01,                                           // RJType = 1
        0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF, // JoinEUI
        0xF1, 0xE3, 0xF5, 0xE7, 0xF9, 0xEB, 0xFD, 0xEF, // DevEUI
        0x30, 0x40,                                     // RJcount1
        0xB0, 0xB1, 0xB2, 0xB3                          // MIC
    };
    TCHECK(s2e_parse_lora_frame(&B, Trejoin1, 24, NULL));
    xeos(&B);
    TCHECK(strstr(B.buf, "\"msgtype\":\"rejoin\"") != NULL);
    TCHECK(strstr(B.buf, "\"MHdr\":192") != NULL);
    TCHECK(strstr(B.buf, "\"MIC\":-1280134736") != NULL);

    // Rejoin Type 2: Same format as Type 0, 19 bytes
    B.pos = 0;
    const u1_t Trejoin2[] = {
        0xC0,                                           // MHdr (rejoin)
        0x02,                                           // RJType = 2
        0x04, 0x05, 0x06,                               // NetID
        0xF1, 0xE3, 0xF5, 0xE7, 0xF9, 0xEB, 0xFD, 0xEF, // DevEUI
        0x50, 0x60,                                     // RJcount2
        0xC0, 0xC1, 0xC2, 0xC3                          // MIC
    };
    TCHECK(s2e_parse_lora_frame(&B, Trejoin2, 19, NULL));
    xeos(&B);
    TCHECK(strstr(B.buf, "\"msgtype\":\"rejoin\"") != NULL);

    // Rejoin too short (< 19 bytes) - should be rejected
    B.pos = 0;
    TCHECK(!s2e_parse_lora_frame(&B, Trejoin0, 18, NULL));

    // Rejoin too long (> 24 bytes) - should be rejected
    B.pos = 0;
    u1_t TrejoinLong[25];
    memcpy(TrejoinLong, Trejoin1, 24);
    TrejoinLong[24] = 0xFF;
    TCHECK(!s2e_parse_lora_frame(&B, TrejoinLong, 25, NULL));

    // Rejoin frames are NOT filtered by JoinEUI - always passed to LNS
    // Test that rejoin passes even with JoinEUI filter enabled
    B.pos = 0;
    memcpy(s2e_joineuiFilter, euiFilter1, sizeof(euiFilter1));
    TCHECK(s2e_parse_lora_frame(&B, Trejoin1, 24, NULL));  // Type 1 passes despite filter

    B.pos = 0;
    TCHECK(s2e_parse_lora_frame(&B, Trejoin0, 19, NULL));  // Type 0 passes despite filter

    s2e_joineuiFilter[0] = 0;  // Clear filter

    free(jsonbuf);
}
