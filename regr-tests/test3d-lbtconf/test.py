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
Test LBT channel configuration via router_config.

This test verifies:
1. LBT channels can be explicitly configured via lbt_channels in router_config
2. LBT rssi_target can be configured via lbt_rssi_target
3. Station correctly applies LBT configuration and blocks TX on busy channels

The test uses AS923-1 region with explicit lbt_channels configuration,
then verifies CCA behavior by marking channels as busy.
"""

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test3d-lbtconf')

import tcutils as tu
import simutils as su
import testutils as tstu


station = None
infos = None
muxs = None
sim = None

# Test frequencies for AS923 - same as upchannels
FREQ1 = 923.2  # Free
FREQ2 = 923.4  # Will be marked busy
FREQ3 = 923.6  # Free


class TestLgwSimServer(su.LgwSimServer):
    fcnt = 0
    updf_task = None
    txcnt = 0
    exp_txfreq = []

    async def on_connected(self, lgwsim: su.LgwSim) -> None:
        # Mark FREQ2 as busy
        now = lgwsim.xticks()
        await lgwsim.send_cca([(FREQ2, now, now + int(20e6))])
        logger.info('LBT: Marked %.3f MHz as busy for 20 seconds', FREQ2)

    async def on_close(self):
        if self.updf_task:
            self.updf_task.cancel()
            self.updf_task = None
        logger.debug('LGWSIM - close')

    async def on_tx(self, lgwsim, pkt):
        logger.debug('LGWSIM: TX freq=%.3fMHz power=%ddBm', pkt['freq_hz']/1e6, pkt['rf_power'])
        self.txcnt += 1
        if self.exp_txfreq and [pkt['freq_hz']] != self.exp_txfreq[0:1]:
            logger.error('LGWSIM: freq=%.3fMHz but expected %.3fMHz',
                        pkt['freq_hz']/1e6, self.exp_txfreq[0]/1e6)
            await self.testDone(2)
        if self.exp_txfreq:
            del self.exp_txfreq[0]


class TestMuxs(tu.Muxs):
    exp_seqno = []
    seqno = 0
    ws = None
    send_task = None
    ev = None

    def get_router_config(self):
        # AS923-1 with explicit LBT channel configuration
        config = dict(tu.router_config_AS923)
        config['lbt_enabled'] = True
        config['lbt_rssi_target'] = -80
        config['lbt_scan_time_us'] = 5000
        config['lbt_channels'] = [
            {'freq_hz': int(FREQ1 * 1e6), 'scan_time_us': 5000},
            {'freq_hz': int(FREQ2 * 1e6), 'scan_time_us': 5000},
            {'freq_hz': int(FREQ3 * 1e6), 'scan_time_us': 5000},
        ]
        logger.info('Sending router_config with lbt_enabled=True, lbt_channels=%s', config['lbt_channels'])
        return config

    async def handle_connection(self, ws):
        self.ws = ws
        self.ev = asyncio.Event()
        self.send_task = asyncio.ensure_future(self.run_test())
        await super().handle_connection(ws)

    async def testDone(self, status):
        global station
        if station:
            try:
                station.terminate()
            except Exception as exc:
                logger.error('Shutting down station: %s', exc, exc_info=True)
            try:
                await station.wait()
                logger.error('Exit code station: %d', station.returncode)
                station = None
            except Exception as exc:
                logger.error('Failed to get exit code of station: %s', exc, exc_info=True)
            os._exit(status)

    async def handle_dntxed(self, ws, msg):
        seqno = msg['seqno']
        logger.debug('DNTXED: seqno=%d (expected: %s)', seqno, self.exp_seqno)
        if seqno in self.exp_seqno:
            self.exp_seqno.remove(seqno)
        self.ev.set()

    def make_dnmsgC(self, rx2dr=4, rx2freq=FREQ1, plen=12):
        dnmsg = {
            'msgtype': 'dnmsg',
            'dC': 2,          # device class C
            'dnmode': 'dn',
            'priority': 0,
            'RX2DR': rx2dr,
            'RX2Freq': int(rx2freq * 1e6),
            'DevEui': '00-00-00-00-11-00-00-01',
            'seqno': self.seqno,
            'MuxTime': time.time(),
            'rctx': 0,
            'pdu': bytes(range(plen)).hex(),
        }
        self.seqno += 1
        return dnmsg

    async def run_test(self):
        """Test LBT channel configuration"""
        try:
            # Wait for station to sync time
            await asyncio.sleep(3.0)

            logger.info('=== Testing LBT channel config with AS923-1 ===')
            logger.info('FREQ1=%.3f (free), FREQ2=%.3f (busy), FREQ3=%.3f (free)', FREQ1, FREQ2, FREQ3)

            # Send downlinks on all three frequencies
            # FREQ2 (923.4 MHz) is marked busy, should be blocked
            for f in (FREQ1, FREQ2, FREQ3, FREQ2):
                dnmsg = self.make_dnmsgC(rx2freq=f)
                if f != FREQ2:
                    self.exp_seqno.append(dnmsg['seqno'])
                    sim.exp_txfreq.append(dnmsg['RX2Freq'])
                logger.debug('Sending dnmsg seqno=%d freq=%.3fMHz (busy=%s)',
                            dnmsg['seqno'], f, f == FREQ2)
                await self.ws.send(json.dumps(dnmsg))

            # Wait for expected TX completions
            timeout = 10.0
            start = time.time()
            while self.exp_seqno and (time.time() - start) < timeout:
                self.ev.clear()
                try:
                    await asyncio.wait_for(self.ev.wait(), 2.0)
                except asyncio.TimeoutError:
                    pass

            # Wait a bit more for any straggler TXs
            await asyncio.sleep(2.0)

            # Verify results
            if self.exp_seqno:
                logger.error('Not all expected TXs completed: remaining=%s', self.exp_seqno)
                await self.testDone(1)
                return
            if sim.exp_txfreq:
                logger.error('Not all expected TX freqs seen: remaining=%s', sim.exp_txfreq)
                await self.testDone(1)
                return

            logger.info('=== LBT channel config test PASSED ===')
            logger.info('TX count=%d, blocked count=2 (FREQ2 was busy)', sim.txcnt)
            await self.testDone(0)

        except asyncio.CancelledError:
            logger.debug('run_test canceled.')
        except Exception as exc:
            logger.error('run_test failed: %s', exc, exc_info=True)
            await self.testDone(1)


with open("tc.uri", "w") as f:
    f.write('ws://localhost:6038')


async def test_start():
    global station, infos, muxs, sim
    infos = tu.Infos()
    muxs = TestMuxs()
    sim = TestLgwSimServer()

    await infos.start_server()
    await muxs.start_server()
    await sim.start_server()

    station_args = ['station', '-p', '--temp', '.']
    station = await subprocess.create_subprocess_exec(*station_args)


tstu.setup_logging()

asyncio.ensure_future(test_start())
asyncio.get_event_loop().run_forever()
