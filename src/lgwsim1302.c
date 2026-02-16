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
 * SX1302/SX1303 LoRa Gateway HAL Simulator
 *
 * This is a true SX1302 simulator that uses the native SX1302 HAL API
 * and supports SF5-SF12 spreading factors properly.
 *
 * Key differences from lgwsim.c (SX1301 simulator):
 * - Uses direct SF values (5-12) instead of bitmasks (0x02-0x40)
 * - Full SF5/SF6 support for both uplink and downlink
 * - SX1302-specific structures (rssi_tcomp, ftime, sx1261, etc.)
 * - Additional APIs: lgw_demod_setconf, lgw_ftime_setconf, lgw_sx1261_setconf
 */

#if defined(CFG_lgwsim1302)
// LCOV_EXCL_START
#include <stdio.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>

// Include SX1302 HAL headers directly
#include "lgw/loragw_hal.h"
#include "lgw/loragw_reg.h"

#include "rt.h"
#include "s2e.h"
#include "sys.h"
#include "sys_linux.h"

// LBT return code alias
#ifndef LGW_LBT_ISSUE
#define LGW_LBT_ISSUE LGW_LBT_NOT_ALLOWED
#endif

// Validation macros (may not be in all HAL versions)
#ifndef IS_LORA_DR
#define IS_LORA_DR(dr)  ((dr == DR_LORA_SF5) || (dr == DR_LORA_SF6) || (dr == DR_LORA_SF7) || \
                         (dr == DR_LORA_SF8) || (dr == DR_LORA_SF9) || (dr == DR_LORA_SF10) || \
                         (dr == DR_LORA_SF11) || (dr == DR_LORA_SF12))
#endif

// ============================================================================
// Simulator State
// ============================================================================

#define MAX_CCA_INFOS   10
#define MAGIC_CCA_FREQ  0xCCAFCCAF
#define RX_NPKTS        1000

struct cca_info {
    u4_t freq;
    sL_t beg;
    sL_t end;
};

struct cca_msg {
    u4_t magic;
    struct cca_info infos[MAX_CCA_INFOS];
};

static struct lgw_pkt_tx_s tx_pkt;
static struct lgw_pkt_rx_s rx_pkts[RX_NPKTS+1];
static u1_t     ppsLatched;

static sL_t     timeOffset;
static sL_t     txbeg;
static sL_t     txend;
static int      rxblen  = sizeof(rx_pkts[0])*RX_NPKTS;
static int      rx_ridx = 0;
static int      rx_widx = 0;
static u4_t     rx_dsc = 0;
static aio_t*   aio;
static tmr_t    conn_tmr;
static struct sockaddr_un sockAddr;
static struct cca_msg     cca_msg;

// Configuration state
static struct lgw_conf_board_s  board_conf;
static struct lgw_conf_rxrf_s   rf_chain_conf[LGW_RF_CHAIN_NB];
static struct lgw_conf_rxif_s   if_chain_conf[LGW_IF_CHAIN_NB];
static struct lgw_conf_demod_s  demod_conf;
static struct lgw_tx_gain_lut_s tx_gain_lut[LGW_RF_CHAIN_NB];
static struct lgw_conf_ftime_s  ftime_conf;
static struct lgw_conf_sx1261_s sx1261_conf;

uint8_t lgwx_device_mode = 0;
uint8_t lgwx_beacon_len = 0;
uint8_t lgwx_beacon_sf = 0;
uint8_t lgwx_lbt_mode = 0;

#define rbfree(widx,ridx,len) (widx >= ridx ? len-widx : ridx-widx-1)
#define rbused(widx,ridx,len) (widx >= ridx ? widx-ridx : len-ridx+widx)

// ============================================================================
// Helper Functions
// ============================================================================

static int cca (sL_t txtime, u4_t txfreq) {
    for( int i=0; i<MAX_CCA_INFOS; i++ ) {
        u4_t freq = cca_msg.infos[i].freq;
        if( freq == 0 )
            break;
        if( txfreq == freq &&
            txtime >= cca_msg.infos[i].beg &&
            txtime <= cca_msg.infos[i].end ) {
            return 0;
        }
    }
    return 1;
}

static sL_t xticks () {
    return sys_time() - timeOffset;
}

// Airtime calculation for SX1302 (uses direct SF values)
static u4_t airtime (int datarate, int bandwidth, int plen) {
    int sf, bw;

    // Bandwidth conversion
    switch(bandwidth) {
    case BW_125KHZ: bw = BW125; break;
    case BW_250KHZ: bw = BW250; break;
    case BW_500KHZ: bw = BW500; break;
    default:        bw = BW125; break;
    }

    // Datarate conversion - SX1302 uses direct SF values
    switch(datarate) {
    case DR_LORA_SF5:  sf = SF5;  break;
    case DR_LORA_SF6:  sf = SF6;  break;
    case DR_LORA_SF7:  sf = SF7;  break;
    case DR_LORA_SF8:  sf = SF8;  break;
    case DR_LORA_SF9:  sf = SF9;  break;
    case DR_LORA_SF10: sf = SF10; break;
    case DR_LORA_SF11: sf = SF11; break;
    case DR_LORA_SF12: sf = SF12; break;
    default:           sf = SF7;  break;
    }

    return s2e_calcDnAirTime(rps_make(sf,bw), plen, /*addcrc*/0, /*preamble*/0);
}

// ============================================================================
// Socket Communication
// ============================================================================

static void read_socket (aio_t* aio);
static void write_socket (aio_t* aio);

static void try_connecting (tmr_t* tmr) {
    if( aio ) {
        aio_close(aio);
        aio = NULL;
    }
    int fd;
    if( (fd = socket(PF_UNIX, SOCK_STREAM|SOCK_NONBLOCK, 0)) == -1 ) {
        LOG(MOD_SIM|ERROR, "LGWSIM1302: Failed to open unix domain socket '%s': %d (%s)",
            sockAddr.sun_path, errno, strerror(errno));
        goto retry;
    }
    if( connect(fd, (struct sockaddr*)&sockAddr, sizeof(sockAddr)) == -1 ) {
        LOG(MOD_SIM|ERROR, "LGWSIM1302: Failed to connect to unix domain socket '%s': %d (%s)",
            sockAddr.sun_path, errno, strerror(errno));
        close(fd);
        goto retry;
    }
    aio = aio_open(&conn_tmr, fd, read_socket, write_socket);

    // Send handshake packet
    memset(&tx_pkt, 0, sizeof(tx_pkt));
    tx_pkt.tx_mode = 255;  // Handshake marker
    tx_pkt.count_us = timeOffset;
    tx_pkt.freq_hz = timeOffset>>32;
    tx_pkt.f_dev = max(0, sys_slaveIdx);
    LOG(MOD_SIM|INFO, "LGWSIM1302: Connected txunit#%d timeOffset=0x%lX xticksNow=0x%lX",
        max(0, sys_slaveIdx), timeOffset, xticks());
    write_socket(aio);
    read_socket(aio);
    return;

retry:
    rt_setTimer(tmr, rt_seconds_ahead(1));
}

static void read_socket (aio_t* aio) {
    while(1) {
        u1_t * rxbuf = &((u1_t*)rx_pkts)[rx_widx];
        int rxlen = 4;
        if( rx_dsc ) {
            if( rx_dsc % sizeof(rx_pkts[0]) == 0 ) {
                LOG(MOD_SIM|ERROR, "LGWSIM1302(%s): RX buffer full. Dropping frame.", sockAddr.sun_path);
                rx_dsc = 0;
                continue;
            } else {
                rxlen = sizeof(rx_pkts[0]) - rx_dsc;
            }
        } else if( (rxlen = rbfree(rx_widx, rx_ridx, rxblen)) == 0 ) {
            rx_dsc = rx_widx % sizeof(rx_pkts[0]);
            rx_widx -= rx_dsc;
            rxbuf = &((u1_t*)rx_pkts)[rx_widx];
            rxlen = sizeof(rx_pkts[0]) - rx_dsc;
        }
        int n = read(aio->fd, rxbuf, rxlen);
        if( n == 0 ) {
            LOG(MOD_SIM|ERROR, "LGWSIM1302(%s) closed (recv)", sockAddr.sun_path);
            rt_yieldTo(&conn_tmr, try_connecting);
            return;
        }
        if( n==-1 ) {
            if( errno == EAGAIN )
                return;
            LOG(MOD_SIM|ERROR, "LGWSIM1302(%s): Recv error: %d (%s)", sockAddr.sun_path, errno, strerror(errno));
            rt_yieldTo(&conn_tmr, try_connecting);
            return;
        }

        if( rx_dsc || rbfree(rx_widx, rx_ridx, rxblen) == 0 ) {
            rx_dsc += n;
            continue;
        } else {
            rx_widx = (rx_widx+n) % rxblen;
        }

        if( rbused(rx_widx, rx_ridx, rxblen) >= sizeof(rx_pkts[0]) &&
            rx_pkts[rx_ridx/sizeof(rx_pkts[0])].freq_hz == MAGIC_CCA_FREQ ) {
            cca_msg = *(struct cca_msg*)&rx_pkts[rx_ridx/sizeof(rx_pkts[0])];
            rx_ridx = (rx_ridx+sizeof(rx_pkts[0])) % rxblen;
        }
    }
}

static void write_socket (aio_t* aio) {
    int n = write(aio->fd, &tx_pkt, sizeof(tx_pkt));
    if( n == 0 ) {
        LOG(MOD_SIM|ERROR, "LGWSIM1302(%s) closed (send)", sockAddr.sun_path);
        rt_yieldTo(&conn_tmr, try_connecting);
        return;
    }
    if( n==-1 ) {
        if( errno == EAGAIN )
            return;
        LOG(MOD_SIM|ERROR, "LGWSIM1302(%s): Send error: %d (%s)", sockAddr.sun_path, errno, strerror(errno));
        rt_yieldTo(&conn_tmr, try_connecting);
        return;
    }
    assert(n == sizeof(tx_pkt));
    aio_set_wrfn(aio, NULL);
}

// ============================================================================
// SX1302 HAL API Implementation
// ============================================================================

int lgw_receive (uint8_t max_pkt, struct lgw_pkt_rx_s *pkt_data) {
    int npkts = 0;
    while( npkts < max_pkt && rbused(rx_widx, rx_ridx, rxblen) >= sizeof(rx_pkts[0]) ) {
        pkt_data[npkts] = rx_pkts[rx_ridx/sizeof(rx_pkts[0])];
        rx_ridx = (rx_ridx+sizeof(rx_pkts[0])) % rxblen;
        npkts += 1;
    }
    if( npkts )
        LOG(MOD_SIM|DEBUG, "LGWSIM1302(%s): received %d packets", sockAddr.sun_path, npkts);
    return npkts;
}

int lgw_send (struct lgw_pkt_tx_s *pkt_data) {
    if( pkt_data == NULL )
        return LGW_HAL_ERROR;

    sL_t t = xticks();
    txbeg = t + (s4_t)((u4_t)pkt_data->count_us - (u4_t)t);
    txend = txbeg + airtime(pkt_data->datarate, pkt_data->bandwidth, pkt_data->size);

    // Validate SF5/SF6 for LoRa modulation
    if( pkt_data->modulation == MOD_LORA ) {
        if( !IS_LORA_DR(pkt_data->datarate) ) {
            LOG(MOD_SIM|ERROR, "LGWSIM1302: Invalid LoRa datarate %u (expected SF5-SF12)", pkt_data->datarate);
            return LGW_HAL_ERROR;
        }
        LOG(MOD_SIM|DEBUG, "LGWSIM1302: TX SF%d BW%d freq=%u size=%d",
            pkt_data->datarate, pkt_data->bandwidth == BW_125KHZ ? 125 :
                                pkt_data->bandwidth == BW_250KHZ ? 250 : 500,
            pkt_data->freq_hz, pkt_data->size);
    }

    if( !cca(txbeg, pkt_data->freq_hz) )
        return LGW_LBT_ISSUE;

    tx_pkt = *pkt_data;
    if( !aio || aio->ctx == NULL || aio->fd == 0 )
        return LGW_HAL_ERROR;
    aio_set_wrfn(aio, write_socket);
    write_socket(aio);
    return LGW_HAL_SUCCESS;
}

int lgw_status (uint8_t rf_chain, uint8_t select, uint8_t *code) {
    (void)rf_chain;  // SX1302 has per-chain status, but simulation uses global state
    (void)select;
    sL_t t = xticks();
    if( t <= txbeg )
        *code = TX_SCHEDULED;
    else if( t <= txend )
        *code = TX_EMITTING;
    else
        *code = TX_FREE;
    return LGW_HAL_SUCCESS;
}

int lgw_abort_tx (uint8_t rf_chain) {
    (void)rf_chain;  // SX1302 has per-chain abort, but simulation uses global state
    txbeg = txend = 0;
    return LGW_HAL_SUCCESS;
}

int lgw_stop (void) {
    rt_clrTimer(&conn_tmr);
    txbeg = txend = 0;
    aio_close(aio);
    aio = NULL;
    return LGW_HAL_SUCCESS;
}

int lgw_get_instcnt(uint32_t* inst_cnt_us) {
    inst_cnt_us[0] = xticks();
    return LGW_HAL_SUCCESS;
}

int lgw_get_trigcnt(uint32_t* trig_cnt_us) {
    sL_t t = xticks();
    if( ppsLatched )
        t -= sys_utc()%1000000;
    trig_cnt_us[0] = t;
    return LGW_HAL_SUCCESS;
}

int lgw_start (void) {
    const char* sockPath = getenv("LORAGW_SPI");
    if( aio )
        return LGW_HAL_ERROR;
    memset(&cca_msg, 0, sizeof(cca_msg));
    memset(&sockAddr, 0, sizeof(sockAddr));
    timeOffset = sys_time() - 0x10000000;
    sockAddr.sun_family = AF_UNIX;
    snprintf(sockAddr.sun_path, sizeof(sockAddr.sun_path), "%s", sockPath);
    LOG(MOD_SIM|INFO, "LGWSIM1302: Starting with socket %s", sockPath);
    rt_yieldTo(&conn_tmr, try_connecting);
    return LGW_HAL_SUCCESS;
}

int lgw_board_setconf (struct lgw_conf_board_s *conf) {
    if( conf == NULL )
        return LGW_HAL_ERROR;
    board_conf = *conf;
    LOG(MOD_SIM|INFO, "LGWSIM1302: Board config: lorawan_public=%d clksrc=%d full_duplex=%d",
        conf->lorawan_public, conf->clksrc, conf->full_duplex);
    return LGW_HAL_SUCCESS;
}

int lgw_rxrf_setconf (uint8_t rf_chain, struct lgw_conf_rxrf_s *conf) {
    if( rf_chain >= LGW_RF_CHAIN_NB || conf == NULL ) {
        LOG(MOD_SIM|ERROR, "LGWSIM1302: Invalid RF chain %d", rf_chain);
        return LGW_HAL_ERROR;
    }

    // SX1302 supports SX1250 radios (in addition to SX1255/SX1257)
    if( conf->type != LGW_RADIO_TYPE_SX1255 &&
        conf->type != LGW_RADIO_TYPE_SX1257 &&
        conf->type != LGW_RADIO_TYPE_SX1250 ) {
        LOG(MOD_SIM|ERROR, "LGWSIM1302: Unsupported radio type %d", conf->type);
        return LGW_HAL_ERROR;
    }

    rf_chain_conf[rf_chain] = *conf;
    LOG(MOD_SIM|INFO, "LGWSIM1302: RF chain %d: en=%d freq=%u type=%d tx_en=%d",
        rf_chain, conf->enable, conf->freq_hz, conf->type, conf->tx_enable);
    return LGW_HAL_SUCCESS;
}

int lgw_rxif_setconf (uint8_t if_chain, struct lgw_conf_rxif_s *conf) {
    if( if_chain >= LGW_IF_CHAIN_NB || conf == NULL ) {
        LOG(MOD_SIM|ERROR, "LGWSIM1302: Invalid IF chain %d", if_chain);
        return LGW_HAL_ERROR;
    }

    if( !conf->enable ) {
        if_chain_conf[if_chain].enable = false;
        return LGW_HAL_SUCCESS;
    }

    if( conf->rf_chain >= LGW_RF_CHAIN_NB ) {
        LOG(MOD_SIM|ERROR, "LGWSIM1302: Invalid RF chain %d for IF chain %d", conf->rf_chain, if_chain);
        return LGW_HAL_ERROR;
    }

    if_chain_conf[if_chain] = *conf;
    LOG(MOD_SIM|INFO, "LGWSIM1302: IF chain %d: en=%d rf=%d freq=%d bw=%d dr=%u",
        if_chain, conf->enable, conf->rf_chain, conf->freq_hz, conf->bandwidth, conf->datarate);
    return LGW_HAL_SUCCESS;
}

int lgw_demod_setconf (struct lgw_conf_demod_s *conf) {
    if( conf == NULL )
        return LGW_HAL_ERROR;
    demod_conf = *conf;
    // multisf_datarate is a bitmask for SF5-SF12 (bit 0 = SF12, bit 7 = SF5)
    LOG(MOD_SIM|INFO, "LGWSIM1302: Demod config: multisf_datarate=0x%02X (SF mask: %s%s%s%s%s%s%s%s)",
        conf->multisf_datarate,
        (conf->multisf_datarate & 0x80) ? "SF5 " : "",
        (conf->multisf_datarate & 0x40) ? "SF6 " : "",
        (conf->multisf_datarate & 0x20) ? "SF7 " : "",
        (conf->multisf_datarate & 0x10) ? "SF8 " : "",
        (conf->multisf_datarate & 0x08) ? "SF9 " : "",
        (conf->multisf_datarate & 0x04) ? "SF10 " : "",
        (conf->multisf_datarate & 0x02) ? "SF11 " : "",
        (conf->multisf_datarate & 0x01) ? "SF12" : "");
    return LGW_HAL_SUCCESS;
}

int lgw_txgain_setconf (uint8_t rf_chain, struct lgw_tx_gain_lut_s *conf) {
    if( rf_chain >= LGW_RF_CHAIN_NB || conf == NULL ) {
        LOG(MOD_SIM|ERROR, "LGWSIM1302: Invalid RF chain %d for TX gain", rf_chain);
        return LGW_HAL_ERROR;
    }

    if( conf->size < 1 || conf->size > TX_GAIN_LUT_SIZE_MAX ) {
        LOG(MOD_SIM|ERROR, "LGWSIM1302: Invalid TX gain LUT size %d", conf->size);
        return LGW_HAL_ERROR;
    }

    tx_gain_lut[rf_chain] = *conf;
    LOG(MOD_SIM|INFO, "LGWSIM1302: TX gain LUT for RF chain %d: %d entries", rf_chain, conf->size);
    return LGW_HAL_SUCCESS;
}

int lgw_ftime_setconf (struct lgw_conf_ftime_s *conf) {
    if( conf == NULL )
        return LGW_HAL_ERROR;
    ftime_conf = *conf;
    LOG(MOD_SIM|INFO, "LGWSIM1302: Fine timestamp: en=%d mode=%d (%s)",
        conf->enable, conf->mode,
        conf->mode == LGW_FTIME_MODE_HIGH_CAPACITY ? "SF5-SF10" : "SF5-SF12");
    return LGW_HAL_SUCCESS;
}

int lgw_sx1261_setconf (struct lgw_conf_sx1261_s *conf) {
    if( conf == NULL )
        return LGW_HAL_ERROR;
    sx1261_conf = *conf;
    if( conf->enable ) {
        LOG(MOD_SIM|INFO, "LGWSIM1302: SX1261 LBT: en=%d rssi_target=%d nb_channel=%d",
            conf->lbt_conf.enable, conf->lbt_conf.rssi_target, conf->lbt_conf.nb_channel);
    }
    return LGW_HAL_SUCCESS;
}

int lgw_reg_w (uint16_t register_id, int32_t reg_value) {
    (void)register_id;
    // For simulation, we only care about GPS_EN register
    ppsLatched = (reg_value != 0);
    return LGW_HAL_SUCCESS;
}

const char* lgw_version_info (void) {
    return "SX1302 HAL Simulation v2.1.0 (SF5-SF12 support)";
}

// Temperature reading (simulated)
int lgw_get_temperature (float *temp) {
    if( temp == NULL )
        return LGW_HAL_ERROR;
    *temp = 25.0f;  // Simulated room temperature
    return LGW_HAL_SUCCESS;
}

// RSSI offset calibration (simulated)
int lgw_calibrate_sx1261_rssi_offset(int8_t *rssi_offset) {
    if( rssi_offset == NULL )
        return LGW_HAL_ERROR;
    *rssi_offset = 0;
    return LGW_HAL_SUCCESS;
}

// Debug configuration (stub)
int lgw_debug_setconf(struct lgw_conf_debug_s *conf) {
    (void)conf;
    return LGW_HAL_SUCCESS;
}

// SX1302-specific GPS enable function
int sx1302_gps_enable(bool enable) {
    ppsLatched = enable ? 1 : 0;
    LOG(MOD_SIM|INFO, "LGWSIM1302: GPS/PPS %s", enable ? "enabled" : "disabled");
    return LGW_REG_SUCCESS;
}

// Reset and start helper (for some platforms)
int reset_lgw_start(void) {
    LOG(MOD_SIM|DEBUG, "LGWSIM1302: reset_lgw_start called");
    return LGW_HAL_SUCCESS;
}

// LBT set conf (SX1301 style - not used for SX1302, but keep for compatibility)
int lgw_lbt_setconf(void* conf) {
    (void)conf;
    LOG(MOD_SIM|DEBUG, "LGWSIM1302: lgw_lbt_setconf called (ignored for SX1302)");
    return LGW_HAL_SUCCESS;
}

// ============================================================================
// SX1302-specific symbols required by ral_lgw.c and sx130xconf.c
// ============================================================================

// Timestamp counter structure (simplified for simulation)
typedef struct {
    uint32_t counter_us_27bits_ref;
    uint8_t  counter_us_27bits_wrap;
} timestamp_counter_t;

// Global counter structure (referenced by ral_lgw.c)
timestamp_counter_t counter_us;

// Get timestamp counter values
int timestamp_counter_get(timestamp_counter_t *self, uint32_t *inst, uint32_t *pps) {
    if( self == NULL )
        return -1;
    uint32_t t = xticks();
    if( inst != NULL )
        *inst = t;
    if( pps != NULL )
        *pps = ppsLatched ? (t - sys_utc()%1000000) : t;
    return 0;
}

// IF chain modem configuration (SX1302 defines: 0=LORA_MULTI, 1=LORA_SERVICE, 2=FSK)
// For SX1302: IF0-7 are LORA_MULTI (0), IF8 is LORA_SERVICE (1), IF9 is FSK (2)
#define IF_LORA_MULTI   0
#define IF_LORA_SERVICE 1
#define IF_FSK          2

// Note: SX1302 uses different naming than SX1301 (IF_LORA_STD -> IF_LORA_SERVICE)
static const uint8_t ifmod_config_1302[LGW_IF_CHAIN_NB] = {
    IF_LORA_MULTI,   // IF0
    IF_LORA_MULTI,   // IF1
    IF_LORA_MULTI,   // IF2
    IF_LORA_MULTI,   // IF3
    IF_LORA_MULTI,   // IF4
    IF_LORA_MULTI,   // IF5
    IF_LORA_MULTI,   // IF6
    IF_LORA_MULTI,   // IF7
    IF_LORA_SERVICE, // IF8 - LoRa service channel (single SF)
    IF_FSK           // IF9 - FSK channel
};

// Exported as ifmod_config for compatibility with code that expects this name
const uint8_t *ifmod_config = ifmod_config_1302;

// Get IF modem config by chain index
uint8_t sx1302_get_ifmod_config(uint8_t if_chain) {
    if( if_chain >= LGW_IF_CHAIN_NB )
        return IF_LORA_MULTI;  // Default
    return ifmod_config_1302[if_chain];
}

// LCOV_EXCL_STOP
#endif // CFG_lgwsim1302
