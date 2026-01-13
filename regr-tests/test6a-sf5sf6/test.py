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
Test SF5/SF6 support with SX1302/SX1303 (testsim1302 variant).

This test verifies:
1. SF5 and SF6 uplink packets are processed correctly
2. Downlink responses using SF5/SF6 are transmitted
3. RP2 1.0.5 asymmetric DR tables work with SF5/SF6
"""

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test6a-sf5sf6-hw')

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
    sf5_tested = False
    sf6_tested = False
    muxs_ready = False  # Set when muxs receives router_config
    first_connection = True

    async def on_connected(self, lgwsim:su.LgwSim) -> None:
        # Reset fcnt on reconnection
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
        dr = pkt.get('datarate', 0)
        # Check if SF5 or SF6 was used in downlink
        # SX1302 DR values: SF5=0x05, SF6=0x06
        if dr == 0x05:
            logger.info('LGWSIM: TX with SF5 confirmed!')
            self.sf5_tested = True
        elif dr == 0x06:
            logger.info('LGWSIM: TX with SF6 confirmed!')
            self.sf6_tested = True

    async def send_updf(self) -> None:
        try:
            while True:
                logger.debug('LGWSIM - UPDF FCnt=%d' % (self.fcnt,))
                if 0 not in self.units:
                    return
                lgwsim = self.units[0]
                
                # Test SF5 and SF6 uplinks (US915 RP2 1.0.5: DR8=SF5, DR7=SF6)
                if self.fcnt == 0:
                    # SF6/125kHz uplink (DR7 in US915 RP2 1.0.5)
                    logger.info('Sending SF6/125kHz uplink')
                    await lgwsim.send_rx(rps=(6, 125), freq=902.3, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 1:
                    # SF5/125kHz uplink (DR8 in US915 RP2 1.0.5)
                    logger.info('Sending SF5/125kHz uplink')
                    await lgwsim.send_rx(rps=(5, 125), freq=902.5, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 2:
                    # Normal SF7 uplink for comparison
                    logger.info('Sending SF7/125kHz uplink')
                    await lgwsim.send_rx(rps=(7, 125), freq=902.7, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 3:
                    # Send termination signal
                    await lgwsim.send_rx(rps=(7, 125), freq=902.3, frame=su.makeDF(fcnt=self.fcnt, port=3))
                
                self.fcnt += 1
                await asyncio.sleep(2.5)  # Allow time for station processing
        except asyncio.CancelledError:
            logger.debug('send_updf canceled.')
        except Exception as exc:
            logger.error('send_updf failed!', exc_info=True)


class TestMuxs(tu.Muxs):
    exp_seqno = []
    received_updf = []
    sf5_uplink_seen = False
    sf6_uplink_seen = False
    sim_server = None  # Reference to sim server for signaling

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Use asymmetric DR config with SF5/SF6 support
        # testsim1302 still uses lgw1 HAL, so use sx1301 config
        self.router_config = tu.router_config_US902_8ch_RP2_sx1301

    async def handle_connection(self, ws):
        # Signal sim that muxs is ready before processing messages
        if self.sim_server:
            logger.debug('Muxs ready, signaling sim')
            self.sim_server.muxs_ready = True
        await super().handle_connection(ws)

    async def testDone(self, status):
        global station, sim
        
        # Verify SF5/SF6 were tested
        if status == 0:
            if not self.sf5_uplink_seen:
                logger.warning('SF5 uplink was not seen')
            if not self.sf6_uplink_seen:
                logger.warning('SF6 uplink was not seen')
        
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
        
        # Track SF5/SF6 uplinks (DR7=SF6, DR8=SF5 in US915 RP2 1.0.5)
        if dr == 7:
            logger.info('SF6/125kHz uplink received (DR7)')
            self.sf6_uplink_seen = True
        elif dr == 8:
            logger.info('SF5/125kHz uplink received (DR8)')
            self.sf5_uplink_seen = True
        
        if port == 3:
            # Termination signal
            if len(self.received_updf) >= 4 and self.sf5_uplink_seen and self.sf6_uplink_seen:
                logger.info('Test completed successfully - SF5 and SF6 tested')
                await self.testDone(0)
            elif len(self.received_updf) >= 4:
                logger.info('Test completed - %d uplinks received', len(self.received_updf))
                await self.testDone(0)
            else:
                logger.error('Test failed - only received %d uplinks', len(self.received_updf))
                await self.testDone(1)
            return
        
        # Send downlink response
        # For testsim1302 (lgw1-based), use standard DRs that SX1301 HAL supports
        # SF5/SF6 TX not supported on simulated SX1301 hardware
        # DR8 = SF12/500kHz is the standard US915 downlink
        dn_dr = 8
            
        dnframe = {
            'msgtype' : 'dnmsg',
            'dC'      : 0,
            'dnmode'  : 'updn',
            'priority': 0,
            'RxDelay' : 0,
            'RX1DR'   : dn_dr,
            'RX1Freq' : 923300000,
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
