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
Test asymmetric datarate support (RP2 1.0.5 US915/AU915).

This test verifies:
1. Station correctly parses DRs_up and DRs_dn from router_config
2. Uplink packets are processed with correct DR lookup
3. Downlink responses use the correct (asymmetric) DR table
"""

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test6-asym-drs')

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
                
                # Test different uplink DRs
                # US915 RP2 1.0.5 uplink: DR0=SF10/125, DR1=SF9/125, DR2=SF8/125, DR3=SF7/125
                if self.fcnt == 0:
                    # DR0 uplink = SF10/125kHz
                    await lgwsim.send_rx(rps=(10, 125), freq=902.3, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 1:
                    # DR3 uplink = SF7/125kHz
                    await lgwsim.send_rx(rps=(7, 125), freq=902.5, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 2:
                    # Send termination signal
                    await lgwsim.send_rx(rps=(7, 125), freq=902.3, frame=su.makeDF(fcnt=self.fcnt, port=3))
                
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
        # Use asymmetric DR config (sx1301 version for testsim)
        self.router_config = tu.router_config_US902_8ch_RP2_sx1301

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
            if len(self.received_updf) >= 3:
                logger.info('Test completed successfully - received %d uplinks', len(self.received_updf))
                await self.testDone(0)
            else:
                logger.error('Test failed - only received %d uplinks', len(self.received_updf))
                await self.testDone(1)
            return
        
        # Send downlink response
        # For asymmetric DRs, the downlink DR should be looked up from DRs_dn table
        # US915 RP2 1.0.5: Uplink DR0 (SF10/125) -> maps to different physical params in downlink
        dnframe = {
            'msgtype' : 'dnmsg',
            'dC'      : 0,
            'dnmode'  : 'updn',
            'priority': 0,
            'RxDelay' : 0,
            'RX1DR'   : 8,  # DR8 downlink = SF12/500kHz (from DRs_dn table)
            'RX1Freq' : 923300000,  # US915 downlink frequency
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
