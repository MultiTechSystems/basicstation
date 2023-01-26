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

#ifndef _sx130xconf_h_
#define _sx130xconf_h_
#if defined(CFG_lgw1)

#include <stdio.h> // loragw_fpga.h refers to FILE
#include "lgw/loragw_hal.h"
#if !defined(CFG_sx1302)
#include "lgw/loragw_lbt.h"
#include "lgw/loragw_fpga.h"
#endif
#include "s2conf.h"
#include "ral.h" //chdefl_t


#define SX130X_ANT_NIL    0
#define SX130X_ANT_OMNI   1
#define SX130X_ANT_SECTOR 2
#define SX130X_ANT_UNDEF  3


#define TEMP_LUT_SIZE_MAX 13
#define DEFAULT_TEMP_COMP_TYPE "SENSOR"
#define DEFAULT_TEMP_COMP_FILE "/sys/class/hwmon/hwmon0/temp1_input"



/**
@struct lgw_tx_alt_gain_s
@brief Structure containing all gains of Tx chain
*/
struct lgw_tx_alt_gain_s {
    uint8_t pa_gain;    /*!> 2 bits, control of the external PA (SX1301 I/O) */
    uint8_t dac_gain;   /*!> 2 bits, control of the radio DAC */
    uint8_t mix_gain;   /*!> 4 bits, control of the radio mixer */
    uint8_t dig_gain;   /*!> 2 bits, control of the radio DIG */
    int8_t  rf_power;   /*!> measured TX power at the board connector, in dBm */
};

/**
@struct lgw_tx_alt_gain_lut_s
@brief Structure defining the Tx gain LUT
*/
struct lgw_tx_alt_gain_lut_s {
    float                       dig_gain[64];
    int8_t                      temp;
    uint8_t                     size;                       /*!> Number of LUT indexes */
};

/**
@struct lgw_tx_alt_gain_lut_s
@brief Structure defining the Tx gain LUT
*/
struct lgw_tx_temp_lut_s {
    struct lgw_tx_alt_gain_s        lut[TX_GAIN_LUT_SIZE_MAX]; /*!> Array of Tx gain struct */
    struct lgw_tx_alt_gain_lut_s    dig[TEMP_LUT_SIZE_MAX];     /*!> Array of Tx gain struct */
    uint8_t                         size;                       /*!> Number of LUT indexes */
    char temp_comp_type[16];
    uint8_t temp_comp_file_type;
    char temp_comp_file[128];
    int temp_comp_value;
    bool temp_comp_enabled;
};

struct sx130xconf {
    struct lgw_conf_board_s  boardconf;
    struct lgw_tx_gain_lut_s txlut;
    struct lgw_tx_temp_lut_s tx_temp_lut;
    struct lgw_conf_rxrf_s   rfconf[LGW_RF_CHAIN_NB];
    struct lgw_conf_rxif_s   ifconf[LGW_IF_CHAIN_NB];
#if defined(CFG_sx1302)
    struct lgw_conf_ftime_s  ftime; // Fine timestamp structure for SX1302, SX1303.
#else
    struct lgw_conf_lbt_s    lbt;
#endif
    s2_t  txpowAdjust;   // assuming there is only one TX path / SX130X (scaled by TXPOW_SCALE)
    u1_t  pps;           // enable PPS latch of trigger count
    u1_t  antennaType;   // type of antenna
    char  device[MAX_DEVICE_LEN];   // SPI device, FTDI spec etc.
};

extern str_t station_conf_USAGE;

int  sx130xconf_parse_setup (struct sx130xconf* sx130xconf, int slaveIdx, str_t hwspec, char* json, int jsonlen);
int  sx130xconf_challoc (struct sx130xconf* sx130xconf, chdefl_t* upchs);
int  sx130xconf_start (struct sx130xconf* sx130xconf, u4_t region);
int  sx130xconf_parse_tcomp (struct sx130xconf* sx130xconf, int slaveIdx, str_t hwspec, char* json, int jsonlen);


void lookup_power_settings(void* ctx, float tx_pwr, int8_t* rf_power, int8_t* dig_gain);
void update_temp_comp_value(void* ctx);

#endif // defined(CFG_lgw1)
#endif // _sx130xconf_h_
