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

/*
 * Unit tests for s2e.c asymmetric DR handling
 * 
 * This tests the bug where any125kHz(), hasFastLora(), and hasFSK() were using
 * s2e_dr2rps() which only looks at dr_defs[], not dr_defs_up[]/dr_defs_dn[].
 * When asymmetric DRs are configured (DRs_up/DRs_dn), dr_defs[] is empty,
 * causing channel allocation to fail.
 * 
 * TEST METHODOLOGY:
 * 1. Test the ACTUAL production functions via test wrappers (s2e_test_any125kHz, etc.)
 * 2. Also test BUGGY versions (replicated here) to prove the bug pattern exists
 * 3. Compare both to verify the production code is fixed
 * 
 * The test wrappers call the real static functions in s2e.c, ensuring we test
 * the actual production code, not just a replica.
 */

#include "selftests.h"
#include "s2e.h"
#include "rt.h"

#if defined(CFG_selftests)

// Declare test wrappers (defined in s2e.c)
extern bool s2e_test_any125kHz(s2ctx_t* s2ctx, int minDR, int maxDR, rps_t* min_rps, rps_t* max_rps);
extern bool s2e_test_hasFastLora(s2ctx_t* s2ctx, int minDR, int maxDR, rps_t* rpsp);
extern bool s2e_test_hasFSK(s2ctx_t* s2ctx, int minDR, int maxDR);

// Test helper: Initialize s2ctx with symmetric DRs (legacy DRs array)
static void init_symmetric_drs(s2ctx_t* s2ctx) {
    memset(s2ctx, 0, sizeof(*s2ctx));
    s2ctx->asymmetric_drs = 0;
    
    // US915 symmetric DRs: DR0-4 are uplink, DR8-13 are downlink
    // DR0: SF10/BW125, DR1: SF9/BW125, DR2: SF8/BW125, DR3: SF7/BW125, DR4: SF8/BW500
    s2ctx->dr_defs[0] = rps_make(SF10, BW125);  // DR0
    s2ctx->dr_defs[1] = rps_make(SF9, BW125);   // DR1
    s2ctx->dr_defs[2] = rps_make(SF8, BW125);   // DR2
    s2ctx->dr_defs[3] = rps_make(SF7, BW125);   // DR3
    s2ctx->dr_defs[4] = rps_make(SF8, BW500);   // DR4
    for (int i = 5; i < 8; i++) {
        s2ctx->dr_defs[i] = RPS_ILLEGAL;
    }
    // Downlink DRs
    s2ctx->dr_defs[8] = rps_make(SF12, BW500);  // DR8
    s2ctx->dr_defs[9] = rps_make(SF11, BW500);  // DR9
    s2ctx->dr_defs[10] = rps_make(SF10, BW500); // DR10
    s2ctx->dr_defs[11] = rps_make(SF9, BW500);  // DR11
    s2ctx->dr_defs[12] = rps_make(SF8, BW500);  // DR12
    s2ctx->dr_defs[13] = rps_make(SF7, BW500);  // DR13
    for (int i = 14; i < DR_CNT; i++) {
        s2ctx->dr_defs[i] = RPS_ILLEGAL;
    }
}

// Test helper: Initialize s2ctx with asymmetric DRs (RP2 1.0.5 DRs_up/DRs_dn)
static void init_asymmetric_drs(s2ctx_t* s2ctx) {
    memset(s2ctx, 0, sizeof(*s2ctx));
    s2ctx->asymmetric_drs = 1;
    
    // dr_defs[] should be empty/illegal when using asymmetric DRs
    for (int i = 0; i < DR_CNT; i++) {
        s2ctx->dr_defs[i] = RPS_ILLEGAL;
    }
    
    // US915 RP2 1.0.5 uplink DRs
    // DR0: SF10/BW125, DR1: SF9/BW125, DR2: SF8/BW125, DR3: SF7/BW125
    // DR4: SF8/BW500, DR5-6: LR-FHSS (not supported), DR7: SF6/BW125, DR8: SF5/BW125
    s2ctx->dr_defs_up[0] = rps_make(SF10, BW125);  // DR0
    s2ctx->dr_defs_up[1] = rps_make(SF9, BW125);   // DR1
    s2ctx->dr_defs_up[2] = rps_make(SF8, BW125);   // DR2
    s2ctx->dr_defs_up[3] = rps_make(SF7, BW125);   // DR3
    s2ctx->dr_defs_up[4] = rps_make(SF8, BW500);   // DR4 - 500kHz
    s2ctx->dr_defs_up[5] = RPS_ILLEGAL;            // DR5 - LR-FHSS
    s2ctx->dr_defs_up[6] = RPS_ILLEGAL;            // DR6 - LR-FHSS
    s2ctx->dr_defs_up[7] = rps_make(SF6, BW125);   // DR7 - SF6/125 (new)
    s2ctx->dr_defs_up[8] = rps_make(SF5, BW125);   // DR8 - SF5/125 (new)
    for (int i = 9; i < DR_CNT; i++) {
        s2ctx->dr_defs_up[i] = RPS_ILLEGAL;
    }
    
    // US915 RP2 1.0.5 downlink DRs (completely different from uplink)
    s2ctx->dr_defs_dn[0] = rps_make(SF5, BW500);   // DR0 - SF5/500 (new)
    for (int i = 1; i < 8; i++) {
        s2ctx->dr_defs_dn[i] = RPS_ILLEGAL;        // DR1-7 RFU
    }
    s2ctx->dr_defs_dn[8] = rps_make(SF12, BW500);  // DR8
    s2ctx->dr_defs_dn[9] = rps_make(SF11, BW500);  // DR9
    s2ctx->dr_defs_dn[10] = rps_make(SF10, BW500); // DR10
    s2ctx->dr_defs_dn[11] = rps_make(SF9, BW500);  // DR11
    s2ctx->dr_defs_dn[12] = rps_make(SF8, BW500);  // DR12
    s2ctx->dr_defs_dn[13] = rps_make(SF7, BW500);  // DR13
    s2ctx->dr_defs_dn[14] = rps_make(SF6, BW500);  // DR14 - SF6/500 (new)
    s2ctx->dr_defs_dn[15] = RPS_ILLEGAL;           // DR15
}

// ============================================================================
// Test s2e_dr2rps_up() - should use correct table based on asymmetric_drs
// ============================================================================
static void test_dr2rps_up(void) {
    s2ctx_t s2ctx;
    
    // Test with symmetric DRs
    init_symmetric_drs(&s2ctx);
    
    // s2e_dr2rps_up should fall back to dr_defs when asymmetric_drs=0
    TCHECK(s2e_dr2rps_up(&s2ctx, 0) == rps_make(SF10, BW125));  // DR0
    TCHECK(s2e_dr2rps_up(&s2ctx, 3) == rps_make(SF7, BW125));   // DR3
    TCHECK(s2e_dr2rps_up(&s2ctx, 4) == rps_make(SF8, BW500));   // DR4
    TCHECK(s2e_dr2rps_up(&s2ctx, 5) == RPS_ILLEGAL);            // DR5 undefined
    
    // Test with asymmetric DRs
    init_asymmetric_drs(&s2ctx);
    
    // s2e_dr2rps_up should use dr_defs_up when asymmetric_drs=1
    TCHECK(s2e_dr2rps_up(&s2ctx, 0) == rps_make(SF10, BW125));  // DR0
    TCHECK(s2e_dr2rps_up(&s2ctx, 3) == rps_make(SF7, BW125));   // DR3
    TCHECK(s2e_dr2rps_up(&s2ctx, 4) == rps_make(SF8, BW500));   // DR4
    TCHECK(s2e_dr2rps_up(&s2ctx, 7) == rps_make(SF6, BW125));   // DR7 - new SF6
    TCHECK(s2e_dr2rps_up(&s2ctx, 8) == rps_make(SF5, BW125));   // DR8 - new SF5
    
    // Verify that s2e_dr2rps (legacy) returns ILLEGAL for asymmetric DRs
    // This was the bug - helper functions were using s2e_dr2rps instead of s2e_dr2rps_up
    TCHECK(s2e_dr2rps(&s2ctx, 0) == RPS_ILLEGAL);  // dr_defs[0] is ILLEGAL
    TCHECK(s2e_dr2rps(&s2ctx, 3) == RPS_ILLEGAL);  // dr_defs[3] is ILLEGAL
}

// ============================================================================
// Test s2e_dr2rps_dn() - should use correct table for downlink
// ============================================================================
static void test_dr2rps_dn(void) {
    s2ctx_t s2ctx;
    
    // Test with asymmetric DRs
    init_asymmetric_drs(&s2ctx);
    
    // s2e_dr2rps_dn should use dr_defs_dn when asymmetric_drs=1
    TCHECK(s2e_dr2rps_dn(&s2ctx, 0) == rps_make(SF5, BW500));   // DR0 - different from uplink!
    TCHECK(s2e_dr2rps_dn(&s2ctx, 8) == rps_make(SF12, BW500));  // DR8
    TCHECK(s2e_dr2rps_dn(&s2ctx, 13) == rps_make(SF7, BW500));  // DR13
    TCHECK(s2e_dr2rps_dn(&s2ctx, 14) == rps_make(SF6, BW500));  // DR14 - new SF6/500
    
    // Verify uplink and downlink DR0 are different in asymmetric mode
    TCHECK(s2e_dr2rps_up(&s2ctx, 0) != s2e_dr2rps_dn(&s2ctx, 0));
}

// ============================================================================
// Test channel bandwidth detection with asymmetric DRs
// This is the core bug: any125kHz() must work with asymmetric DRs
// ============================================================================

// Replicate the BUGGY any125kHz logic that uses s2e_dr2rps (before fix)
// This proves the bug pattern exists and would fail with asymmetric DRs
static bool test_any125kHz_buggy(s2ctx_t* s2ctx, int minDR, int maxDR) {
    for (int dr = minDR; dr <= maxDR; dr++) {
        rps_t rps = s2e_dr2rps(s2ctx, dr);  // BUG: uses dr_defs instead of dr_defs_up
        if (rps != RPS_FSK && rps_bw(rps) == BW125) {
            return true;
        }
    }
    return false;
}

static void test_any125kHz_asymmetric(void) {
    s2ctx_t s2ctx;
    rps_t min_rps, max_rps;
    
    // Test with symmetric DRs - both production and buggy should work
    init_symmetric_drs(&s2ctx);
    
    // US915 upchannels use DR0-5, which includes 125kHz channels
    bool sym_production = s2e_test_any125kHz(&s2ctx, 0, 5, &min_rps, &max_rps);
    bool sym_buggy = test_any125kHz_buggy(&s2ctx, 0, 5);
    fprintf(stderr, "Symmetric DRs: production=%d, buggy=%d (both should be 1)\n",
            sym_production, sym_buggy);
    TCHECK(sym_production == true);   // Production: DR0-3 are 125kHz
    TCHECK(sym_buggy == true);        // Buggy also works with symmetric
    
    // Test with asymmetric DRs - this is where the bug manifests
    init_asymmetric_drs(&s2ctx);
    
    // US915 RP2 upchannels use DR0-8, which includes 125kHz channels (DR0-3, DR7-8)
    bool asym_production = s2e_test_any125kHz(&s2ctx, 0, 8, &min_rps, &max_rps);
    bool asym_buggy = test_any125kHz_buggy(&s2ctx, 0, 8);
    fprintf(stderr, "Asymmetric DRs: production=%d, buggy=%d (production=1, buggy=0)\n",
            asym_production, asym_buggy);
    fprintf(stderr, "  -> BUG: buggy returns 0 because dr_defs[] is empty with asymmetric DRs\n");
    fprintf(stderr, "  -> This causes bw to stay BWNIL, channels not allocated, radios disabled\n");
    
    // PRODUCTION CODE (after fix): finds 125kHz DRs correctly
    TCHECK(asym_production == true);
    
    // BUGGY VERSION: fails to find 125kHz because dr_defs[] is all ILLEGAL
    TCHECK(asym_buggy == false);
    
    // If production == buggy, the fix is missing!
    if (asym_production == asym_buggy) {
        fprintf(stderr, "  -> FAIL: Production code matches buggy behavior - fix not applied!\n");
    }
    TCHECK(asym_production != asym_buggy);  // Production must differ from buggy
}

// ============================================================================
// Test 500kHz (FastLora) detection with asymmetric DRs
// ============================================================================

static bool test_hasFastLora_buggy(s2ctx_t* s2ctx, int minDR, int maxDR) {
    for (int dr = minDR; dr <= maxDR; dr++) {
        rps_t rps = s2e_dr2rps(s2ctx, dr);  // BUG: uses dr_defs instead of dr_defs_up
        if (rps_bw(rps) == BW250 || rps_bw(rps) == BW500) {
            return true;
        }
    }
    return false;
}

static void test_hasFastLora_asymmetric(void) {
    s2ctx_t s2ctx;
    rps_t rps;
    
    // Test with asymmetric DRs
    init_asymmetric_drs(&s2ctx);
    
    // DR4 is SF8/BW500 in both symmetric and asymmetric US915
    bool production = s2e_test_hasFastLora(&s2ctx, 0, 8, &rps);
    bool buggy = test_hasFastLora_buggy(&s2ctx, 0, 8);
    
    fprintf(stderr, "hasFastLora asymmetric: production=%d, buggy=%d\n", production, buggy);
    
    TCHECK(production == true);   // PRODUCTION (fixed): finds DR4
    TCHECK(buggy == false);       // BUGGY: fails
    TCHECK(production != buggy);  // Production must differ from buggy
}

// ============================================================================
// Test FSK detection with asymmetric DRs
// ============================================================================

static bool test_hasFSK_buggy(s2ctx_t* s2ctx, int minDR, int maxDR) {
    for (int dr = minDR; dr <= maxDR; dr++) {
        rps_t rps = s2e_dr2rps(s2ctx, dr);  // BUG: uses dr_defs instead of dr_defs_up
        if (rps == RPS_FSK) {
            return true;
        }
    }
    return false;
}

// Helper to add FSK DR for testing
static void add_fsk_dr(s2ctx_t* s2ctx, int dr) {
    if (s2ctx->asymmetric_drs) {
        s2ctx->dr_defs_up[dr] = RPS_FSK;
    } else {
        s2ctx->dr_defs[dr] = RPS_FSK;
    }
}

static void test_hasFSK_asymmetric(void) {
    s2ctx_t s2ctx;
    
    // Test with asymmetric DRs including FSK (EU868 style)
    init_asymmetric_drs(&s2ctx);
    add_fsk_dr(&s2ctx, 9);  // Add FSK at DR9 in uplink table
    
    bool production = s2e_test_hasFSK(&s2ctx, 0, 15);
    bool buggy = test_hasFSK_buggy(&s2ctx, 0, 15);
    
    fprintf(stderr, "hasFSK asymmetric: production=%d, buggy=%d\n", production, buggy);
    
    TCHECK(production == true);   // PRODUCTION (fixed): finds FSK
    TCHECK(buggy == false);       // BUGGY: dr_defs[9] is ILLEGAL, not FSK
    TCHECK(production != buggy);  // Production must differ from buggy
}

// ============================================================================
// Test downlink airtime calculation with asymmetric DRs
// Bug: updateAirtimeTxpow() was using s2e_dr2rps() instead of s2e_dr2rps_dn()
// ============================================================================

static void test_dn_airtime_asymmetric(void) {
    s2ctx_t s2ctx;
    init_asymmetric_drs(&s2ctx);
    
    // In asymmetric mode, downlink DR0 is SF5/BW500 (very fast)
    // Uplink DR0 is SF10/BW125 (much slower)
    // If we use the wrong table, airtime calculation will be wildly wrong
    
    rps_t up_rps = s2e_dr2rps_up(&s2ctx, 0);
    rps_t dn_rps = s2e_dr2rps_dn(&s2ctx, 0);
    rps_t buggy_rps = s2e_dr2rps(&s2ctx, 0);
    
    fprintf(stderr, "Asymmetric DR0: uplink=%d (SF10/BW125), downlink=%d (SF5/BW500), buggy=%d (ILLEGAL)\n",
            up_rps, dn_rps, buggy_rps);
    
    // Fixed version gets correct downlink RPS
    TCHECK(dn_rps == rps_make(SF5, BW500));
    
    // Buggy version gets ILLEGAL (would break airtime calculation)
    TCHECK(buggy_rps == RPS_ILLEGAL);
    
    // Uplink and downlink are different for DR0 in asymmetric mode
    TCHECK(up_rps != dn_rps);
    
    // Test a downlink-only DR (DR8-13 in US915)
    // These exist in both uplink and downlink tables but may differ
    rps_t dn_dr8 = s2e_dr2rps_dn(&s2ctx, 8);
    rps_t up_dr8 = s2e_dr2rps_up(&s2ctx, 8);
    
    fprintf(stderr, "Asymmetric DR8: uplink=%d (SF5/BW125), downlink=%d (SF12/BW500)\n",
            up_dr8, dn_dr8);
    
    // In US915 RP2, uplink DR8 is SF5/BW125, downlink DR8 is SF12/BW500
    TCHECK(up_dr8 == rps_make(SF5, BW125));
    TCHECK(dn_dr8 == rps_make(SF12, BW500));
    TCHECK(up_dr8 != dn_dr8);  // Must use correct table for TX!
}

// ============================================================================
// Test TX RPS conversion with asymmetric DRs
// Bug: ral_lgw.c and ral_master.c were using s2e_dr2rps() for TX
// ============================================================================

static void test_tx_rps_asymmetric(void) {
    s2ctx_t s2ctx;
    init_asymmetric_drs(&s2ctx);
    
    // Simulate a class A downlink on DR13 (typical US915 RX2)
    int tx_dr = 13;
    
    rps_t fixed_rps = s2e_dr2rps_dn(&s2ctx, tx_dr);
    rps_t buggy_rps = s2e_dr2rps(&s2ctx, tx_dr);
    
    fprintf(stderr, "TX DR13: fixed=%d (SF7/BW500), buggy=%d (ILLEGAL)\n",
            fixed_rps, buggy_rps);
    
    // Fixed: correct downlink RPS for transmission
    TCHECK(fixed_rps == rps_make(SF7, BW500));
    TCHECK(rps_sf(fixed_rps) == SF7);
    TCHECK(rps_bw(fixed_rps) == BW500);
    
    // Buggy: ILLEGAL RPS would cause TX to fail or use wrong parameters
    TCHECK(buggy_rps == RPS_ILLEGAL);
    
    // Test new RP2 downlink DR14 (SF6/BW500)
    rps_t dr14_dn = s2e_dr2rps_dn(&s2ctx, 14);
    fprintf(stderr, "TX DR14: fixed=%d (SF6/BW500) - new RP2 DR\n", dr14_dn);
    TCHECK(dr14_dn == rps_make(SF6, BW500));
}

// ============================================================================
// Test RX logging RPS with asymmetric DRs
// Bug: RX logging was using s2e_dr2rps() instead of s2e_dr2rps_up()
// ============================================================================

static void test_rx_rps_asymmetric(void) {
    s2ctx_t s2ctx;
    init_asymmetric_drs(&s2ctx);
    
    // Received uplink on DR3 (typical US915 125kHz uplink)
    int rx_dr = 3;
    
    rps_t fixed_rps = s2e_dr2rps_up(&s2ctx, rx_dr);
    rps_t buggy_rps = s2e_dr2rps(&s2ctx, rx_dr);
    
    fprintf(stderr, "RX DR3: fixed=%d (SF7/BW125), buggy=%d (ILLEGAL)\n",
            fixed_rps, buggy_rps);
    
    // Fixed: correct uplink RPS for logging
    TCHECK(fixed_rps == rps_make(SF7, BW125));
    
    // Buggy: ILLEGAL would show wrong RPS in logs
    TCHECK(buggy_rps == RPS_ILLEGAL);
    
    // Test new RP2 uplink DR7 and DR8 (SF6, SF5)
    rps_t dr7_up = s2e_dr2rps_up(&s2ctx, 7);
    rps_t dr8_up = s2e_dr2rps_up(&s2ctx, 8);
    
    fprintf(stderr, "RX DR7: %d (SF6/BW125), DR8: %d (SF5/BW125) - new RP2 DRs\n",
            dr7_up, dr8_up);
    
    TCHECK(dr7_up == rps_make(SF6, BW125));
    TCHECK(dr8_up == rps_make(SF5, BW125));
}

// ============================================================================
// Main test entry point
// ============================================================================
void selftest_s2e(void) {
    test_dr2rps_up();
    test_dr2rps_dn();
    test_any125kHz_asymmetric();
    test_hasFastLora_asymmetric();
    test_hasFSK_asymmetric();
    test_dn_airtime_asymmetric();
    test_tx_rps_asymmetric();
    test_rx_rps_asymmetric();
}

#else // !defined(CFG_selftests)

void selftest_s2e(void) {}

#endif // !defined(CFG_selftests)
