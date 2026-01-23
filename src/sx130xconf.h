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

// Maximum LBT channels - use the larger of the two HAL limits
// SX1301: 8 channels (LBT_CHANNEL_FREQ_NB)
// SX1302/SX1303: 16 channels
#define LBT_MAX_CHANNELS 16

// LBT channel configuration from LNS
struct lbt_channel {
    u4_t freq_hz;        // Channel frequency in Hz
    u2_t scan_time_us;   // Scan time in microseconds
    u1_t bandwidth;      // Bandwidth (BW_125KHZ, BW_250KHZ, BW_500KHZ)
};

// LBT configuration from router_config
struct lbt_config {
    u1_t enabled;                        // LBT enabled flag
    u1_t nb_channel;                     // Number of LBT channels
    s1_t rssi_target;                    // RSSI threshold in dBm
    s1_t rssi_offset;                    // RSSI calibration offset
    u2_t default_scan_time_us;           // Default scan time for all channels
    struct lbt_channel channels[LBT_MAX_CHANNELS];
};
typedef struct lbt_config lbt_config_t;

#if defined(CFG_sx1302)
// SX1302/SX1303 LBT structures - for simulation builds these are defined here;
// for real hardware builds, they come from the SX1302 HAL (loragw_hal.h)
#if defined(CFG_lgwsim)
#define LGW_LBT_CHANNEL_NB_MAX 16

struct lgw_conf_chan_lbt_s {
    uint32_t    freq_hz;            // LBT channel frequency
    uint8_t     bandwidth;          // LBT channel bandwidth
    uint16_t    scan_time_us;       // LBT channel carrier sense time
    uint16_t    transmit_time_ms;   // LBT channel transmission duration when allowed
};

struct lgw_conf_sx1261_lbt_s {
    bool                        enable;             // enable or disable LBT
    int8_t                      rssi_target;        // RSSI threshold in dBm
    uint8_t                     nb_channel;         // number of LBT channels
    struct lgw_conf_chan_lbt_s  channels[LGW_LBT_CHANNEL_NB_MAX];
};

struct lgw_conf_sx1261_s {
    bool                            enable;         // enable or disable SX1261 radio
    char                            spi_path[64];   // Path to SPI device
    int8_t                          rssi_offset;    // RSSI offset in dBm
    struct lgw_conf_sx1261_lbt_s    lbt_conf;       // LBT configuration
};

int lgw_sx1261_setconf(struct lgw_conf_sx1261_s *conf);
#endif // CFG_lgwsim
#endif // CFG_sx1302

struct sx130xconf {
    struct lgw_conf_board_s  boardconf;
    struct lgw_tx_gain_lut_s txlut;
    struct lgw_conf_rxrf_s   rfconf[LGW_RF_CHAIN_NB];
    struct lgw_conf_rxif_s   ifconf[LGW_IF_CHAIN_NB];
#if !defined(CFG_sx1302)
    struct lgw_conf_lbt_s    lbt;
#else
    struct lgw_conf_sx1261_s sx1261_cfg;  // SX1302/SX1303 LBT via SX1261
#endif
    s2_t  txpowAdjust;   // assuming there is only one TX path / SX130X (scaled by TXPOW_SCALE)
    u1_t  pps;           // enable PPS latch of trigger count
    u1_t  antennaType;   // type of antenna
    char  device[MAX_DEVICE_LEN];   // SPI device, FTDI spec etc.
};

extern str_t station_conf_USAGE;

int  sx130xconf_parse_setup (struct sx130xconf* sx130xconf, int slaveIdx, str_t hwspec, char* json, int jsonlen);
int  sx130xconf_challoc (struct sx130xconf* sx130xconf, chdefl_t* upchs);
int  sx130xconf_start (struct sx130xconf* sx130xconf, u4_t cca_region, struct lbt_config* lbt_config);


#endif // defined(CFG_lgw1)
#endif // _sx130xconf_h_
