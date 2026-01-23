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
# DATA, OR PROFITS; OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test3e-rejoin')

import tcutils as tu
import simutils as su
import testutils as tstu


station = None
infos = None
muxs = None
sim = None


class TestLgwSimServer(su.LgwSimServer):
    def __init__(self):
        super().__init__()
        self.rejoin_sent = False
        self.jreq_sent = False

    REJOIN_FRAME = bytes([
        0xC0,                                           # MHdr (rejoin)
        0x00,                                           # RJType = 0
        0x01, 0x02, 0x03,                               # NetID
        0xF1, 0xE3, 0xF5, 0xE7, 0xF9, 0xEB, 0xFD, 0xEF, # DevEUI
        0x10, 0x20,                                     # RJcount0
        0xA0, 0xA1, 0xA2, 0xA3                          # MIC
    ])

    JREQ_FRAME = bytes([
        0x00,                                           # MHdr (join request)
        0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF, # JoinEUI
        0xF1, 0xE3, 0xF5, 0xE7, 0xF9, 0xEB, 0xFD, 0xEF, # DevEUI
        0x30, 0x40,                                     # DevNonce
        0xA0, 0xA1, 0xA2, 0xA3                          # MIC
    ])

    async def on_connected(self, lgwsim:su.LgwSim) -> None:
        self.task = asyncio.ensure_future(self.send_frames())

    async def on_close(self):
        self.task.cancel()
        logger.debug('LGWSIM - close')

    async def send_frames(self) -> None:
        try:
            await asyncio.sleep(1.0)
            # Send rejoin first
            if not self.rejoin_sent:
                logger.debug('LGWSIM - Sending REJOIN')
                await self.send_rx(rps=(7,125), freq=869.525, frame=self.REJOIN_FRAME)
                self.rejoin_sent = True
                await asyncio.sleep(2.0)

            # Send join request
            if not self.jreq_sent:
                logger.debug('LGWSIM - Sending JREQ')
                await self.send_rx(rps=(7,125), freq=869.525, frame=self.JREQ_FRAME)
                self.jreq_sent = True
                await asyncio.sleep(2.0)

        except asyncio.CancelledError:
            logger.debug('send_frames canceled.')
        except Exception as exc:
            logger.error('send_frames failed!', exc_info=True)


class TestMuxs(tu.Muxs):
    def __init__(self):
        super().__init__()
        self.rejoin_seen = False
        self.jreq_seen = False

    async def testDone(self, status):
        global station
        if station:
            station.terminate()
            await station.wait()
            station = None
        os._exit(status)

    async def handle_rejoin(self, ws, msg):
        logger.debug('REJOIN: MHdr=%r MIC=%r pdu=%r', msg.get('MHdr'), msg.get('MIC'), msg.get('pdu'))
        if msg.get('MHdr') != 192:
            await self.testDone(4)
        if msg.get('MIC') != -1549622880:
            await self.testDone(5)
        expected_pdu = TestLgwSimServer.REJOIN_FRAME.hex().upper()
        if msg.get('pdu') != expected_pdu:
            await self.testDone(6)
        self.rejoin_seen = True
        logger.info('REJOIN validated')

        # Check if both messages received
        if self.rejoin_seen and self.jreq_seen:
            await self.testDone(0)

    async def handle_jreq(self, ws, msg):
        logger.debug('JREQ: MHdr=%r DevNonce=%r', msg.get('MHdr'), msg.get('DevNonce'))
        if msg.get('MHdr') != 0:
            await self.testDone(7)
        if msg.get('DevNonce') != 16464:  # 0x3040
            await self.testDone(8)
        self.jreq_seen = True
        logger.info('JREQ validated')

        # Check if both messages received
        if self.rejoin_seen and self.jreq_seen:
            await self.testDone(0)


tls_mode  = (sys.argv[1:2] == ['tls'])
tls_no_ca = (sys.argv[2:3] == ['no_ca'])

ws = 'wss' if tls_mode else 'ws'

with open("tc.uri","w") as f:
    f.write('%s://localhost:6038' % ws)

async def test_start():
    global station, infos, muxs, sim
    infos = tu.Infos(muxsuri = ('%s://localhost:6039/router' % ws),
                     tlsidentity = ('infos-0' if tls_mode else None),
                     tls_no_ca = tls_no_ca)
    muxs = TestMuxs()
    sim = TestLgwSimServer()

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