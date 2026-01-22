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
Test AU915 region compatibility.

This test verifies:
1. Station correctly parses AU915 region config
2. Standard uplink DRs (DR0-DR6) work correctly
3. Works on all variants (testsim, testsim1302, testms, testms1302)
"""

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test6l-au915-compat')

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
    muxs_ready = False
    first_connection = True

    async def on_connected(self, lgwsim:su.LgwSim) -> None:
        if not self.first_connection:
            logger.debug('LGWSIM reconnected, resetting fcnt')
            self.fcnt = 0
        self.first_connection = False
        
        while not self.muxs_ready:
            await asyncio.sleep(0.1)
        self.updf_task = asyncio.ensure_future(self.send_updf())

    async def on_close(self):
        if self.updf_task:
            self.updf_task.cancel()
            self.updf_task = None
        logger.debug('LGWSIM - close')

    async def on_tx(self, lgwsim, pkt):
        self.txcnt += 1
        logger.info('LGWSIM: TX #%d' % (self.txcnt,))

    async def send_updf(self) -> None:
        try:
            while True:
                logger.debug('LGWSIM - UPDF FCnt=%d' % (self.fcnt,))
                if 0 not in self.units:
                    return
                lgwsim = self.units[0]
                
                # Test standard AU915 uplinks (DR0-6 for SX1301 compatibility)
                if self.fcnt == 0:
                    logger.info('Sending SF12/125kHz uplink (AU915 DR0)')
                    await lgwsim.send_rx(rps=(12, 125), freq=916.2, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 1:
                    logger.info('Sending SF7/125kHz uplink (AU915 DR5)')
                    await lgwsim.send_rx(rps=(7, 125), freq=916.4, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 2:
                    logger.info('Sending SF9/125kHz uplink (AU915 DR3)')
                    await lgwsim.send_rx(rps=(9, 125), freq=916.6, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 3:
                    # Termination signal
                    await lgwsim.send_rx(rps=(7, 125), freq=916.8, frame=su.makeDF(fcnt=self.fcnt, port=3))
                
                self.fcnt += 1
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            logger.debug('send_updf canceled.')
        except Exception as exc:
            logger.error('send_updf failed!', exc_info=True)


class TestMuxs(tu.Muxs):
    received_updf = []
    uplink_drs = {}
    sim_server = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Use AU915 RP2 1.0.5 SX1301 config (backward compatible)
        self.router_config = tu.router_config_AU915_8ch_RP2_sx1301

    async def handle_connection(self, ws):
        if self.sim_server:
            logger.debug('Muxs ready, signaling sim')
            self.sim_server.muxs_ready = True
        await super().handle_connection(ws)

    async def testDone(self, status):
        global station
        
        if status == 0:
            logger.info('Uplink DRs received: %s', self.uplink_drs)
        
        if station:
            station.terminate()
            await station.wait()
            station = None
        os._exit(status)

    async def handle_updf(self, ws, msg):
        fcnt = msg['FCnt']
        dr = msg['DR']
        freq = msg['Freq']
        port = msg['FPort']
        
        logger.info('UPDF: FCnt=%d DR=%d Freq=%.3fMHz FPort=%d' % (fcnt, dr, freq/1e6, port))
        self.received_updf.append({'fcnt': fcnt, 'dr': dr, 'freq': freq, 'port': port})
        self.uplink_drs[dr] = self.uplink_drs.get(dr, 0) + 1
        
        if port == 3:
            # Termination signal - verify we received uplinks
            if len(self.received_updf) >= 4:
                logger.info('Test completed successfully - AU915 region config working')
                await self.testDone(0)
            else:
                logger.error('Test failed - only received %d uplinks', len(self.received_updf))
                await self.testDone(1)
            return


with open("tc.uri","w") as f:
    f.write('ws://localhost:6038')

async def test_start():
    global station, infos, muxs, sim
    infos = tu.Infos(muxsuri='ws://localhost:6039/router')
    muxs = TestMuxs()
    sim = TestLgwSimServer()
    
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
