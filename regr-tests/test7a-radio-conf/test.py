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
Test that verifies Basic Station accepts 'radio_conf' as configuration key name.
Basic Station accepts sx1301_conf, sx1302_conf, and radio_conf interchangeably.
This test ensures the radio_conf key is properly parsed and functional.
"""

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test7a-radio-conf')

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

    async def on_connected(self, lgwsim:su.LgwSim) -> None:
        self.updf_task = asyncio.ensure_future(self.send_updf())

    async def on_close(self):
        self.updf_task.cancel()
        self.updf_task = None
        logger.debug('LGWSIM - close')

    async def on_tx(self, lgwsim, pkt):
        logger.debug('LGWSIM: TX %r' % (pkt,))
        self.txcnt += 1

    async def send_updf(self) -> None:
        try:
            while True:
                logger.debug('LGWSIM - UPDF FCnt=%d' % (self.fcnt,))
                # Use 10% DC band (869.525) to avoid duty cycle blocking
                freq = 869.525
                port = 1 if self.fcnt < 3 else 3  # port 3 signals success
                if 0 not in self.units:
                    return
                lgwsim = self.units[0]
                await lgwsim.send_rx(rps=(7,125), freq=freq, frame=su.makeDF(fcnt=self.fcnt, port=port))
                self.fcnt += 1
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            logger.debug('send_updf canceled.')
        except Exception as exc:
            logger.error('send_updf failed!', exc_info=True)


class TestMuxs(tu.Muxs):
    exp_seqno = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Use EU868 config with radio_conf key to test alternate config key name
        self.router_config = tu.router_config_EU868_6ch_radio_conf

    async def testDone(self, status):
        global station
        if station:
            station.terminate()
            await station.wait()
            station = None
        os._exit(status)

    async def handle_dntxed(self, ws, msg):
        seqno = msg['seqno']
        logger.debug('DNTXED: seqno=%r diid=%r', seqno, msg['diid'])
        # Just verify we get some downlinks - don't strictly check sequence
        if seqno in self.exp_seqno:
            self.exp_seqno.remove(seqno)

    async def handle_updf(self, ws, msg):
        fcnt = msg['FCnt']
        logger.debug('UPDF: rctx=%r Fcnt=%d Freq=%.3fMHz FPort=%d' % (msg['upinfo']['rctx'], fcnt, msg['Freq']/1e6, msg['FPort']))
        port = msg['FPort']
        if port >= 3:
            # Test passed - we received uplinks which means radio_conf was parsed correctly
            await self.testDone(0)
        dnframe = {
            'msgtype' : 'dnmsg',
            'dC'      : 0,
            'dnmode'  : 'updn',
            'priority': 0,
            'RxDelay' : 0,
            'RX1DR'   : msg['DR'],
            'RX1Freq' : msg['Freq'],
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

    await infos.start_server()
    await muxs.start_server()
    await sim.start_server()

    station_args = ['station','-p', '--temp', '.']
    station = await subprocess.create_subprocess_exec(*station_args)

tstu.setup_logging()

asyncio.ensure_future(test_start())
asyncio.get_event_loop().run_forever()
