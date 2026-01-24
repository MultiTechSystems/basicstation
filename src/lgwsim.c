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

#if defined(CFG_lgwsim)
// LCOV_EXCL_START
#include <stdio.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/un.h>

#include "lgw/loragw_reg.h"
#include "lgw/loragw_hal.h"
#include "lgw/loragw_fpga.h"
#include "lgw/loragw_lbt.h"

#include "rt.h"
#include "s2e.h"
#include "sys.h"
#include "sx130xconf.h"

#include "sys_linux.h"

#define MAX_CCA_INFOS   10
#define MAGIC_CCA_FREQ  0xCCAFCCAF

#define RX_NPKTS 1000

struct cca_info {
    u4_t freq;
    sL_t beg;
    sL_t end;
};

struct cca_msg {
    u4_t magic;    // corresponds to freq_hz in struct lgw_pkt_rx_s
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

uint8_t lgwx_device_mode = 0;
uint8_t lgwx_beacon_len = 0;
uint8_t lgwx_beacon_sf = 0;
uint8_t lgwx_lbt_mode = 0;


#define rbfree(widx,ridx,len) (widx >= ridx ? len-widx : ridx-widx-1)
#define rbused(widx,ridx,len) (widx >= ridx ? widx-ridx : len-ridx+widx)

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
    // Make it different from ustime_t to increase test coverage
    return sys_time() - timeOffset;
}


static u4_t airtime (int datarate, int bandwidth, int plen) {
    int sf, bw;
    switch(bandwidth) {
    case BW_125KHZ: bw = BW125; break;
    case BW_250KHZ: bw = BW250; break;
    case BW_500KHZ: bw = BW500; break;
    }
    switch(datarate) {
    case DR_LORA_SF12: sf = SF12; break;
    case DR_LORA_SF11: sf = SF11; break;
    case DR_LORA_SF10: sf = SF10; break;
    case DR_LORA_SF9 : sf = SF9 ; break;
    case DR_LORA_SF8 : sf = SF8 ; break;
    case DR_LORA_SF7 : sf = SF7 ; break;
    }
    return s2e_calcDnAirTime(rps_make(sf,bw), plen, /*addcrc*/0, /*preamble*/0);
}


static void read_socket (aio_t* aio);
static void write_socket (aio_t* aio);

static void try_connecting (tmr_t* tmr) {
    if( aio ) {
        aio_close(aio);
        aio = NULL;
    }
    int fd;
    // Would like to use SOCK_DGRAM but this only works in python/asyncio 3.7 (currently at 3.6.5)
    if( (fd = socket(PF_UNIX, SOCK_STREAM|SOCK_NONBLOCK, 0)) == -1 ) {
        LOG(MOD_SIM|ERROR, "LGWSIM: Failed to open unix domain socket '%s': %d (%s)", sockAddr.sun_path, errno, strerror(errno));
        goto retry;
    }
    if( connect(fd, (struct sockaddr*)&sockAddr, sizeof(sockAddr)) == -1 ) {
        LOG(MOD_SIM|ERROR, "LGWSIM: Failed to connect to unix domain socket '%s': %d (%s)", sockAddr.sun_path, errno, strerror(errno));
        close(fd);
        goto retry;
    }
    aio = aio_open(&conn_tmr, fd, read_socket, write_socket);
    // Send a fake packet with our socket
    tx_pkt.tx_mode = 255;
    tx_pkt.count_us = timeOffset;
    tx_pkt.freq_hz = timeOffset>>32;
    tx_pkt.f_dev = max(0, sys_slaveIdx);
    LOG(MOD_SIM|INFO, "LGWSIM: Connected txunit#%d timeOffset=0x%lX xticksNow=0x%lX", max(0, sys_slaveIdx), timeOffset, xticks());
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
        if( rx_dsc ) { // Currently discarding bytes until next packet boundary
            if( rx_dsc % sizeof(rx_pkts[0]) == 0 ) { // Packet boundary
                LOG(MOD_SIM|ERROR, "LGWSIM(%s): RX buffer full. Dropping frame.", sockAddr.sun_path);
                rx_dsc = 0;
                continue;
            } else {
                rxlen = sizeof(rx_pkts[0]) - rx_dsc;
            }
        } else if( (rxlen = rbfree(rx_widx, rx_ridx, rxblen)) == 0 ) {
            rx_dsc = rx_widx  % sizeof(rx_pkts[0]);
            rx_widx -= rx_dsc;
            rxbuf = &((u1_t*)rx_pkts)[rx_widx];
            rxlen = sizeof(rx_pkts[0]) - rx_dsc;
        }
        int n = read(aio->fd, rxbuf, rxlen);
        if( n == 0 ) {
            LOG(MOD_SIM|ERROR, "LGWSIM(%s) closed (recv)", sockAddr.sun_path);
            rt_yieldTo(&conn_tmr, try_connecting);
            return;
        }
        if( n==-1 ) {
            if( errno == EAGAIN )
                return;
            LOG(MOD_SIM|ERROR, "LGWSIM(%s): Recv error: %d (%s)", sockAddr.sun_path, errno, strerror(errno));
            rt_yieldTo(&conn_tmr, try_connecting);
            return;
        }

        if( rx_dsc || rbfree(rx_widx, rx_ridx, rxblen) == 0 ) {
            rx_dsc += n;
            continue;
        } else {
            rx_widx = (rx_widx+n) % rxblen;
        }

        if( rbused(rx_widx, rx_ridx, rxblen) >= sizeof(rx_pkts[0]) && rx_pkts[rx_ridx/sizeof(rx_pkts[0])].freq_hz == MAGIC_CCA_FREQ ){
            cca_msg = *(struct cca_msg*)&rx_pkts[rx_ridx/sizeof(rx_pkts[0])];
            rx_ridx = (rx_ridx+sizeof(rx_pkts[0])) % rxblen;
        }
    }
}


static void write_socket (aio_t* aio) {
    int n = write(aio->fd, &tx_pkt, sizeof(tx_pkt));
    if( n == 0 ) {
        LOG(MOD_SIM|ERROR, "LGWSIM(%s) closed (send)", sockAddr.sun_path);
        rt_yieldTo(&conn_tmr, try_connecting);
        return;
    }
    if( n==-1 ) {
        if( errno == EAGAIN )
            return;
        LOG(MOD_SIM|ERROR, "LGWSIM(%s): Send error: %d (%s)", sockAddr.sun_path, errno, strerror(errno));
        rt_yieldTo(&conn_tmr, try_connecting);
        return;
    }
    assert(n == sizeof(tx_pkt));
    aio_set_wrfn(aio, NULL);
}

/* **********************************************
   ****         LGW Simulation               ****
   ********************************************** */

int lgw_receive (uint8_t max_pkt, struct lgw_pkt_rx_s *pkt_data) {
    int npkts = 0;
    while( npkts < max_pkt && rbused(rx_widx, rx_ridx, rxblen) >= sizeof(rx_pkts[0]) ){
        pkt_data[npkts] = rx_pkts[rx_ridx/sizeof(rx_pkts[0])];
        rx_ridx = (rx_ridx+sizeof(rx_pkts[0])) % rxblen;
        npkts += 1;
    }
    if( npkts )
        LOG(MOD_SIM|DEBUG, "LGWSIM(%s): received %d packets", sockAddr.sun_path, npkts);
    return npkts;
}


int lgw_send (struct lgw_pkt_tx_s pkt_data) {
    sL_t t = xticks();
    txbeg = t + (s4_t)((u4_t)pkt_data.count_us - (u4_t)t);
    txend = txbeg + airtime(pkt_data.datarate, pkt_data.bandwidth, pkt_data.size);
    if( !cca(txbeg, pkt_data.freq_hz) )
        return LGW_LBT_ISSUE;
    tx_pkt = pkt_data;
    if( !aio || aio->ctx == NULL || aio->fd == 0 )
        return LGW_HAL_ERROR;
    aio_set_wrfn(aio, write_socket);
    write_socket(aio);
    return LGW_HAL_SUCCESS;
}


int lgw_status (uint8_t select, uint8_t *code) {
    sL_t t = xticks();
    if( t <= txbeg )
        *code = TX_SCHEDULED;
    else if( t <= txend )
        *code = TX_EMITTING;
    else
        *code = TX_FREE;
    return LGW_HAL_SUCCESS;
}


int lgw_abort_tx (void) {
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


int lgw_get_trigcnt(uint32_t* trig_cnt_us) {
    sL_t t = xticks();
    if( ppsLatched )
        t -= sys_utc()%1000000;
    trig_cnt_us[0] = t;
    return LGW_HAL_SUCCESS;
}


int lgw_start () {
    const char* sockPath = getenv("LORAGW_SPI");
    if( aio )
        return LGW_HAL_ERROR;
    memset(&cca_msg, 0, sizeof(cca_msg));
    memset(&sockAddr, 0, sizeof(sockAddr));
    // Make xticks different from ustime to cover more test ground.
    // xticks start at ~(1<<28) whenever a radio simulation starts.
    timeOffset = sys_time() - 0x10000000;
    sockAddr.sun_family = AF_UNIX;
    snprintf(sockAddr.sun_path, sizeof(sockAddr.sun_path), "%s", sockPath);
    rt_yieldTo(&conn_tmr, try_connecting);
    return LGW_HAL_SUCCESS;
}


int lgw_reg_w (uint16_t register_id, int32_t reg_value) {
    assert(register_id == LGW_GPS_EN);
    ppsLatched = reg_value;
    return LGW_HAL_SUCCESS;
}


int lgw_board_setconf (struct lgw_conf_board_s conf) {
    return LGW_HAL_SUCCESS;
}


int lgw_rxrf_setconf (uint8_t rf_chain, struct lgw_conf_rxrf_s conf) {
    /* check input range (segfault prevention) */
    if (rf_chain >= LGW_RF_CHAIN_NB) {
        LOG(MOD_SIM|ERROR, "ERROR: NOT A VALID RF_CHAIN NUMBER\n");
        return LGW_HAL_ERROR;
    }

    /* check if radio type is supported */
    if ((conf.type != LGW_RADIO_TYPE_SX1255) && (conf.type != LGW_RADIO_TYPE_SX1257)) {
        LOG(MOD_SIM|ERROR, "ERROR: NOT A VALID RADIO TYPE\n");
        return LGW_HAL_ERROR;
    }

    /* check if TX notch filter frequency is supported */
    if ((conf.tx_enable == true) && ((conf.tx_notch_freq < LGW_MIN_NOTCH_FREQ) || (conf.tx_notch_freq > LGW_MAX_NOTCH_FREQ))) {
        LOG(MOD_SIM|ERROR, "WARNING: NOT A VALID TX NOTCH FILTER FREQUENCY [%u..%u]Hz\n", LGW_MIN_NOTCH_FREQ, LGW_MAX_NOTCH_FREQ);
        conf.tx_notch_freq = 0;
    }

    /* set internal config according to parameters */
    // rf_enable[rf_chain] = conf.enable;
    // rf_rx_freq[rf_chain] = conf.freq_hz;
    // rf_rssi_offset[rf_chain] = conf.rssi_offset;
    // rf_radio_type[rf_chain] = conf.type;
    // rf_tx_enable[rf_chain] = conf.tx_enable;
    // rf_tx_notch_freq[rf_chain] = conf.tx_notch_freq;

    LOG(MOD_SIM|INFO, "Note: rf_chain %d configuration; en:%d freq:%d rssi_offset:%f radio_type:%d tx_enable:%d tx_notch_freq:%u\n",
        rf_chain, conf.enable, conf.freq_hz, conf.rssi_offset, conf.type, conf.tx_enable, conf.tx_notch_freq);

    return LGW_HAL_SUCCESS;
}

const uint8_t ifmod_config[LGW_IF_CHAIN_NB] = LGW_IFMODEM_CONFIG;

#define LGW_RF_RX_BANDWIDTH_125KHZ  925000      /* for 125KHz channels */
#define LGW_RF_RX_BANDWIDTH_250KHZ  1000000     /* for 250KHz channels */
#define LGW_RF_RX_BANDWIDTH_500KHZ 1100000 /* for 500KHz channels */

int32_t lgw_bw_getval(int x) {
    switch (x) {
        case BW_500KHZ: return 500000;
        case BW_250KHZ: return 250000;
        case BW_125KHZ: return 125000;
        case BW_62K5HZ: return 62500;
        case BW_31K2HZ: return 31200;
        case BW_15K6HZ: return 15600;
        case BW_7K8HZ : return 7800;
        default: return -1;
    }
}

int lgw_rxif_setconf (uint8_t if_chain, struct lgw_conf_rxif_s conf) {
    int32_t bw_hz;
    uint32_t rf_rx_bandwidth;
    uint8_t ifmod_config[LGW_IF_CHAIN_NB] = LGW_IFMODEM_CONFIG;
    // uint8_t fsk_sync_word_size = 3; /* default number of bytes for FSK sync word */
    uint64_t fsk_sync_word = 0xC194C1; /* default FSK sync word (ALIGNED RIGHT, MSbit first) */

    /* check input range (segfault prevention) */
    if (if_chain >= LGW_IF_CHAIN_NB) {
        LOG(MOD_SIM|ERROR, "ERROR: %d NOT A VALID IF_CHAIN NUMBER\n", if_chain);
        return LGW_HAL_ERROR;
    }

    /* if chain is disabled, don't care about most parameters */
    if (conf.enable == false) {
        LOG(MOD_SIM|INFO, "Note: if_chain %d disabled\n", if_chain);
        return LGW_HAL_SUCCESS;
    }

    if (conf.rf_chain >= LGW_RF_CHAIN_NB) {
        LOG(MOD_SIM|ERROR, "ERROR: INVALID RF_CHAIN TO ASSOCIATE WITH A LORA_STD IF CHAIN\n");
        return LGW_HAL_ERROR;
    }
    /* check if IF frequency is optimal based on channel and radio bandwidths */
    switch (conf.bandwidth) {
        case BW_250KHZ:
            rf_rx_bandwidth = LGW_RF_RX_BANDWIDTH_250KHZ; /* radio bandwidth */
            break;
        case BW_500KHZ:
            rf_rx_bandwidth = LGW_RF_RX_BANDWIDTH_500KHZ; /* radio bandwidth */
            break;
        default:
            /* For 125KHz and below */
            rf_rx_bandwidth = LGW_RF_RX_BANDWIDTH_125KHZ; /* radio bandwidth */
            break;
    }
    bw_hz = lgw_bw_getval(conf.bandwidth); /* channel bandwidth */
    if ((conf.freq_hz + ((bw_hz==-1)?LGW_REF_BW:bw_hz)/2) > ((int32_t)rf_rx_bandwidth/2)) {
        LOG(MOD_SIM|ERROR, "ERROR: IF FREQUENCY %d TOO HIGH\n", conf.freq_hz);
        return LGW_HAL_ERROR;
    } else if ((conf.freq_hz - ((bw_hz==-1)?LGW_REF_BW:bw_hz)/2) < -((int32_t)rf_rx_bandwidth/2)) {
        LOG(MOD_SIM|ERROR, "ERROR: IF FREQUENCY %d TOO LOW\n", conf.freq_hz);
        return LGW_HAL_ERROR;
    }

    /* check parameters according to the type of IF chain + modem,
    fill default if necessary, and commit configuration if everything is OK */
    switch (ifmod_config[if_chain]) {
        case IF_LORA_STD:
            /* fill default parameters if needed */
            if (conf.bandwidth == BW_UNDEFINED) {
                conf.bandwidth = BW_250KHZ;
            }
            if (conf.datarate == DR_UNDEFINED) {
                conf.datarate = DR_LORA_SF9;
            }
            /* check BW & DR */
            if (!IS_LORA_BW(conf.bandwidth)) {
                LOG(MOD_SIM|ERROR, "ERROR: BANDWIDTH NOT SUPPORTED BY LORA_STD IF CHAIN\n");
                return LGW_HAL_ERROR;
            }
            if (!IS_LORA_STD_DR(conf.datarate)) {
                LOG(MOD_SIM|ERROR, "ERROR: DATARATE NOT SUPPORTED BY LORA_STD IF CHAIN\n");
                return LGW_HAL_ERROR;
            }
            /* set internal configuration  */
            // if_enable[if_chain] = conf.enable;
            // if_rf_chain[if_chain] = conf.rf_chain;
            // if_freq[if_chain] = conf.freq_hz;
            // lora_rx_bw = conf.bandwidth;
            // lora_rx_sf = (uint8_t)(DR_LORA_MULTI & conf.datarate); /* filter SF out of the 7-12 range */
            // if (SET_PPM_ON(conf.bandwidth, conf.datarate)) {
            //     lora_rx_ppm_offset = true;
            // } else {
            //     lora_rx_ppm_offset = false;
            // }
            LOG(MOD_SIM|INFO, "Note: LoRa 'std' if_chain %d configuration; en:%d rf_chain:%d freq:%d bw:%d dr:%d\n",
                if_chain, conf.enable, conf.rf_chain, conf.freq_hz, conf.bandwidth, (uint8_t)(DR_LORA_MULTI & conf.datarate));
            break;

        case IF_LORA_MULTI:
            /* fill default parameters if needed */
            if (conf.bandwidth == BW_UNDEFINED) {
                conf.bandwidth = BW_125KHZ;
            }
            if (conf.datarate == DR_UNDEFINED) {
                conf.datarate = DR_LORA_MULTI;
            }
            /* check BW & DR */
            if (conf.bandwidth != BW_125KHZ) {
                LOG(MOD_SIM|ERROR, "ERROR: BANDWIDTH NOT SUPPORTED BY LORA_MULTI IF CHAIN\n");
                return LGW_HAL_ERROR;
            }
            if (!IS_LORA_MULTI_DR(conf.datarate)) {
                LOG(MOD_SIM|ERROR, "ERROR: DATARATE(S) NOT SUPPORTED BY LORA_MULTI IF CHAIN\n");
                return LGW_HAL_ERROR;
            }
            /* set internal configuration  */
            // if_enable[if_chain] = conf.enable;
            // if_rf_chain[if_chain] = conf.rf_chain;
            // if_freq[if_chain] = conf.freq_hz;
            // lora_multi_sfmask[if_chain] = (uint8_t)(DR_LORA_MULTI & conf.datarate); /* filter SF out of the 7-12 range */
            LOG(MOD_SIM|INFO, "Note: LoRa 'multi' if_chain %d configuration; en:%d rf_chain:%d freq:%d SF_mask:0x%02x\n",
                if_chain, conf.enable, conf.rf_chain, conf.freq_hz, (uint8_t)(DR_LORA_MULTI & conf.datarate));
            break;

        case IF_FSK_STD:
            /* fill default parameters if needed */
            if (conf.bandwidth == BW_UNDEFINED) {
                conf.bandwidth = BW_250KHZ;
            }
            if (conf.datarate == DR_UNDEFINED) {
                conf.datarate = 64000; /* default datarate */
            }
            /* check BW & DR */
            if(!IS_FSK_BW(conf.bandwidth)) {
                LOG(MOD_SIM|ERROR, "ERROR: BANDWIDTH NOT SUPPORTED BY FSK IF CHAIN\n");
                return LGW_HAL_ERROR;
            }
            if(!IS_FSK_DR(conf.datarate)) {
                LOG(MOD_SIM|ERROR, "ERROR: DATARATE NOT SUPPORTED BY FSK IF CHAIN\n");
                return LGW_HAL_ERROR;
            }
            /* set internal configuration  */
            // if_enable[if_chain] = conf.enable;
            // if_rf_chain[if_chain] = conf.rf_chain;
            // if_freq[if_chain] = conf.freq_hz;
            // fsk_rx_bw = conf.bandwidth;
            // fsk_rx_dr = conf.datarate;
            if (conf.sync_word > 0) {
                // fsk_sync_word_size = conf.sync_word_size;
                fsk_sync_word = conf.sync_word;
            }
            LOG(MOD_SIM|INFO, "Note: FSK if_chain %d configuration; en:%d rf_chain:%d freq:%d bw:%d dr:%d (%d real dr) sync:0x%0X\n",
                if_chain, conf.enable, conf.rf_chain, conf.freq_hz, conf.bandwidth, conf.datarate, LGW_XTAL_FREQU/(LGW_XTAL_FREQU/conf.datarate), fsk_sync_word);
            break;

        default:
            LOG(MOD_SIM|ERROR, "ERROR: IF CHAIN %d TYPE NOT SUPPORTED\n", if_chain);
            return LGW_HAL_ERROR;
}
    return LGW_HAL_SUCCESS;
}


int lgw_txgain_setconf (struct lgw_tx_gain_lut_s* conf) {
    int i;

    /* Check LUT size */
    if ((conf->size < 1) || (conf->size > TX_GAIN_LUT_SIZE_MAX)) {
        LOG(MOD_SIM|ERROR, "ERROR: TX gain LUT must have at least one entry and  maximum %d entries\n", TX_GAIN_LUT_SIZE_MAX);
        return LGW_HAL_ERROR;
    }

    // txgain_lut.size = conf->size;

    for (i = 0; i < conf->size; i++) {
        /* Check gain range */
        if (conf->lut[i].dig_gain > 3) {
            LOG(MOD_SIM|ERROR, "ERROR: TX gain LUT: SX1301 digital gain must be between 0 and 3\n");
            return LGW_HAL_ERROR;
        }
        if (conf->lut[i].dac_gain != 3) {
            LOG(MOD_SIM|ERROR, "ERROR: TX gain LUT: SX1257 DAC gains != 3 are not supported\n");
            return LGW_HAL_ERROR;
        }
        if (conf->lut[i].mix_gain > 15) {
            LOG(MOD_SIM|ERROR, "ERROR: TX gain LUT: SX1257 mixer gain must not exceed 15\n");
            return LGW_HAL_ERROR;
        } else if (conf->lut[i].mix_gain < 8) {
            LOG(MOD_SIM|ERROR, "ERROR: TX gain LUT: SX1257 mixer gains < 8 are not supported\n");
            return LGW_HAL_ERROR;
        }
        if (conf->lut[i].pa_gain > 3) {
            LOG(MOD_SIM|ERROR, "ERROR: TX gain LUT: External PA gain must not exceed 3\n");
            return LGW_HAL_ERROR;
        }

        // /* Set internal LUT */
        // txgain_lut.lut[i].dig_gain = conf->lut[i].dig_gain;
        // txgain_lut.lut[i].dac_gain = conf->lut[i].dac_gain;
        // txgain_lut.lut[i].mix_gain = conf->lut[i].mix_gain;
        // txgain_lut.lut[i].pa_gain  = conf->lut[i].pa_gain;
        // txgain_lut.lut[i].rf_power = conf->lut[i].rf_power;
    }

    return LGW_HAL_SUCCESS;
}

int lgw_lbt_setconf (struct lgw_conf_lbt_s conf) {
    return LGW_HAL_SUCCESS;
}

#if defined(CFG_sx1302)
int lgw_sx1261_setconf (struct lgw_conf_sx1261_s *conf) {
    if (conf && conf->enable) {
        LOG(MOD_RAL|INFO, "SX1261 LBT configured: rssi_target=%d nb_channel=%d",
            conf->lbt_conf.rssi_target, conf->lbt_conf.nb_channel);
    }
    return LGW_HAL_SUCCESS;
}
#endif // CFG_sx1302

str_t lgw_version_info () {
    return "LGW Simulation";
}

#if defined(CFG_smtcpico)
int lgw_connect (const char *com_path) {
    return LGW_HAL_SUCCESS;
}
#endif

// LCOV_EXCL_STOP
#endif // CFG_lgwsim
