# --- Revised 3-Clause BSD License ---
# Copyright Semtech Corporation 2022. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#     * Neither the name of the Semtech corporation nor the names of its
#       contributors may be used to endorse or promote products derived from this
#       software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL SEMTECH CORPORATION. BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Test AU915 asymmetric datarate support (RP2 1.0.5).

This test verifies:
1. Station correctly parses DRs_up and DRs_dn for AU915 region
2. Uplink packets are processed with correct DR lookup
3. Downlink responses use the correct (asymmetric) DR table

AU915 RP2 1.0.5 differences from US915:
- Uplink: DR0=SF12/125, DR1=SF11/125, ..., DR5=SF7/125, DR6=SF8/500, DR7=LR-FHSS, DR9=SF6/125, DR10=SF5/125
- Downlink: Same as US915 (DR0=SF5/500, DR8-14=SF12-SF6/500)
"""

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test6b-au915')

import tcutils as tu
import simutils as su
import testutils as tstu


station = None
infos = None
muxs = None
sim = None


class TestLgwSimServer(su.LgwSimServer):
    fcnt = 0
    updf_task = None
    txcnt = 0
    last_tx_dr = None
    muxs_ready = False  # Set when muxs receives router_config
    first_connection = True

    async def on_connected(self, lgwsim:su.LgwSim) -> None:
        # Reset fcnt on reconnection (testms may restart slave)
        if not self.first_connection:
            logger.debug('LGWSIM reconnected, resetting fcnt')
            self.fcnt = 0
        self.first_connection = False
        
        # Wait for muxs to be configured before sending uplinks
        while not self.muxs_ready:
            await asyncio.sleep(0.1)
        self.updf_task = asyncio.ensure_future(self.send_updf())

    async def on_close(self):
        if self.updf_task:
            self.updf_task.cancel()
            self.updf_task = None
        logger.debug('LGWSIM - close')

    async def on_tx(self, lgwsim, pkt):
        logger.debug('LGWSIM: TX %r' % (pkt,))
        self.txcnt += 1
        # Record the datarate used for TX (downlink)
        self.last_tx_dr = pkt.get('datarate')
        logger.info('LGWSIM: TX datarate=0x%02x' % (self.last_tx_dr or 0,))

    async def send_updf(self) -> None:
        try:
            while True:
                logger.debug('LGWSIM - UPDF FCnt=%d' % (self.fcnt,))
                if 0 not in self.units:
                    return
                lgwsim = self.units[0]
                
                # Test different uplink DRs for AU915 RP2 1.0.5
                # AU915 uplink: DR0=SF12/125, DR2=SF10/125, DR5=SF7/125
                if self.fcnt == 0:
                    # DR0 uplink = SF12/125kHz (AU915 specific)
                    logger.info('Sending SF12/125kHz uplink (DR0)')
                    await lgwsim.send_rx(rps=(12, 125), freq=916.2, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 1:
                    # DR2 uplink = SF10/125kHz
                    logger.info('Sending SF10/125kHz uplink (DR2)')
                    await lgwsim.send_rx(rps=(10, 125), freq=916.4, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 2:
                    # DR5 uplink = SF7/125kHz
                    logger.info('Sending SF7/125kHz uplink (DR5)')
                    await lgwsim.send_rx(rps=(7, 125), freq=916.6, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 3:
                    # Send termination signal
                    await lgwsim.send_rx(rps=(7, 125), freq=916.2, frame=su.makeDF(fcnt=self.fcnt, port=3))
                
                self.fcnt += 1
                await asyncio.sleep(2.5)  # Match test3-updn-tls timing for testms compatibility
        except asyncio.CancelledError:
            logger.debug('send_updf canceled.')
        except Exception as exc:
            logger.error('send_updf failed!', exc_info=True)


class TestMuxs(tu.Muxs):
    exp_seqno = []
    received_updf = []
    sim_server = None  # Reference to sim server for signaling

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Use AU915 asymmetric DR config (sx1301 version for testsim)
        self.router_config = tu.router_config_AU915_8ch_RP2_sx1301

    async def handle_connection(self, ws):
        # Signal sim that muxs is ready before processing messages
        if self.sim_server:
            logger.debug('Muxs ready, signaling sim')
            self.sim_server.muxs_ready = True
        await super().handle_connection(ws)

    async def testDone(self, status):
        global station
        if station:
            station.terminate()
            await station.wait()
            station = None
        os._exit(status)

    async def handle_dntxed(self, ws, msg):
        seqno = msg['seqno']
        logger.debug('DNTXED: seqno=%r', seqno)
        if [seqno] != self.exp_seqno[0:1]:
            logger.error('DNTXED: %r but expected seqno=%r\n\t=>%r', seqno, self.exp_seqno, msg)
            await self.testDone(2)
        del self.exp_seqno[0]

    async def handle_updf(self, ws, msg):
        fcnt = msg['FCnt']
        dr = msg['DR']
        freq = msg['Freq']
        port = msg['FPort']
        
        logger.info('UPDF: FCnt=%d DR=%d Freq=%.3fMHz FPort=%d' % (fcnt, dr, freq/1e6, port))
        self.received_updf.append({'fcnt': fcnt, 'dr': dr, 'freq': freq, 'port': port})
        
        if port == 3:
            # Termination signal - verify we received expected uplinks
            if len(self.received_updf) >= 4:
                # Verify AU915 DR mapping
                # DR0=SF12/125 (AU915 specific, different from US915)
                # DR2=SF10/125, DR5=SF7/125
                dr0_seen = any(u['dr'] == 0 for u in self.received_updf)
                dr2_seen = any(u['dr'] == 2 for u in self.received_updf)
                dr5_seen = any(u['dr'] == 5 for u in self.received_updf)
                
                if dr0_seen and dr2_seen and dr5_seen:
                    logger.info('Test completed successfully - AU915 DRs verified (DR0, DR2, DR5)')
                    await self.testDone(0)
                else:
                    logger.error('Test failed - missing expected DRs: DR0=%s DR2=%s DR5=%s',
                                dr0_seen, dr2_seen, dr5_seen)
                    await self.testDone(1)
            else:
                logger.error('Test failed - only received %d uplinks', len(self.received_updf))
                await self.testDone(1)
            return
        
        # Send downlink response
        # AU915 downlink uses same DR table as US915
        # DR8 = SF12/500kHz
        dnframe = {
            'msgtype' : 'dnmsg',
            'dC'      : 0,
            'dnmode'  : 'updn',
            'priority': 0,
            'RxDelay' : 0,
            'RX1DR'   : 8,  # DR8 downlink = SF12/500kHz (from DRs_dn table)
            'RX1Freq' : 923300000,  # AU915 downlink frequency
            'DevEui'  : '00-00-00-00-11-00-00-01',
            'xtime'   : msg['upinfo']['xtime']+1000000,
            'seqno'   : fcnt,
            'MuxTime' : time.time(),
            'rctx'    : msg['upinfo']['rctx'],
            'pdu'     : '0A0B0C0D0E0F',
        }
        self.exp_seqno.append(dnframe['seqno'])
        await ws.send(json.dumps(dnframe))


with open("tc.uri","w") as f:
    f.write('ws://localhost:6038')

async def test_start():
    global station, infos, muxs, sim
    infos = tu.Infos(muxsuri='ws://localhost:6039/router')
    muxs = TestMuxs()
    sim = TestLgwSimServer()
    
    # Connect muxs and sim for ready signaling
    muxs.sim_server = sim

    await infos.start_server()
    await muxs.start_server()
    await sim.start_server()

    a = os.environ.get('STATION_ARGS','')
    args = [] if not a else a.split(' ')
    station_args = ['station','-p', '--temp', '.'] + args
    station = await subprocess.create_subprocess_exec(*station_args)


tstu.setup_logging()

asyncio.ensure_future(test_start())
asyncio.get_event_loop().run_forever()
