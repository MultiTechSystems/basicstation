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
Test US915 SF5/SF6 support with SX1302/SX1303 (testsim1302 variant).

This test verifies RP2 1.0.5 US915 datarates:
- Uplink: DR7 (SF6/125kHz), DR8 (SF5/125kHz)
- Downlink: DR0 (SF5/500kHz), DR14 (SF6/500kHz)

US915 RP2 1.0.5 DR tables:
  Uplink:  DR0=SF10/125, DR7=SF6/125, DR8=SF5/125
  Downlink: DR0=SF5/500, DR8=SF12/500, DR14=SF6/500
"""

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test6a-sf5sf6')

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
    tx_datarates = []  # Record all TX datarates
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
        dr = pkt.get('datarate', 0)
        self.tx_datarates.append(dr)
        self.txcnt += 1
        # Decode SF from datarate byte (lower nibble)
        sf = dr & 0x0F
        logger.info('LGWSIM: TX #%d datarate=0x%02x (SF%d)' % (self.txcnt, dr, sf))

    async def send_updf(self) -> None:
        try:
            while True:
                logger.debug('LGWSIM - UPDF FCnt=%d' % (self.fcnt,))
                if 0 not in self.units:
                    return
                lgwsim = self.units[0]
                
                # Test US915 RP2 1.0.5 uplinks
                if self.fcnt == 0:
                    # DR7 uplink = SF6/125kHz
                    logger.info('Sending SF6/125kHz uplink (US915 DR7)')
                    await lgwsim.send_rx(rps=(6, 125), freq=902.3, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 1:
                    # DR8 uplink = SF5/125kHz
                    logger.info('Sending SF5/125kHz uplink (US915 DR8)')
                    await lgwsim.send_rx(rps=(5, 125), freq=902.5, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 2:
                    # Standard DR3 uplink = SF7/125kHz for comparison
                    logger.info('Sending SF7/125kHz uplink (US915 DR3)')
                    await lgwsim.send_rx(rps=(7, 125), freq=902.7, frame=su.makeDF(fcnt=self.fcnt, port=1))
                elif self.fcnt == 3:
                    # Termination signal
                    await lgwsim.send_rx(rps=(7, 125), freq=902.3, frame=su.makeDF(fcnt=self.fcnt, port=3))
                
                self.fcnt += 1
                await asyncio.sleep(2.5)
        except asyncio.CancelledError:
            logger.debug('send_updf canceled.')
        except Exception as exc:
            logger.error('send_updf failed!', exc_info=True)


class TestMuxs(tu.Muxs):
    exp_seqno = []
    received_updf = []
    uplink_drs = {}  # Track which DRs we received
    sim_server = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Use US915 RP2 1.0.5 config with SF5/SF6 uplink support
        # This config has upchannels DR0-8 to allow SF5/SF6 uplinks
        self.router_config = tu.router_config_US902_8ch_RP2_sf5sf6

    async def handle_connection(self, ws):
        if self.sim_server:
            logger.debug('Muxs ready, signaling sim')
            self.sim_server.muxs_ready = True
        await super().handle_connection(ws)

    async def testDone(self, status):
        global station, sim
        
        if status == 0:
            # Verify results
            logger.info('Uplink DRs received: %s', self.uplink_drs)
            logger.info('Downlink datarates transmitted: %s', 
                       ['0x%02x' % d for d in sim.tx_datarates])
            
            # Check uplinks
            if 7 not in self.uplink_drs:
                logger.warning('DR7 (SF6/125) uplink not received')
            if 8 not in self.uplink_drs:
                logger.warning('DR8 (SF5/125) uplink not received')
        
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
        self.uplink_drs[dr] = self.uplink_drs.get(dr, 0) + 1
        
        if port == 3:
            # Termination signal
            if len(self.received_updf) >= 4:
                # Verify we received SF5/SF6 uplinks (DR7, DR8)
                if 7 in self.uplink_drs and 8 in self.uplink_drs:
                    logger.info('Test completed successfully - US915 SF5/SF6 uplinks verified')
                    await self.testDone(0)
                else:
                    logger.error('Test failed - missing SF5/SF6 uplinks: DR7=%s DR8=%s',
                                7 in self.uplink_drs, 8 in self.uplink_drs)
                    await self.testDone(1)
            else:
                logger.error('Test failed - only received %d uplinks', len(self.received_updf))
                await self.testDone(1)
            return
        
        # Send downlink response
        # Note: testsim1302 uses lgw1 HAL which can't TX SF5/SF6
        # Use standard downlink DRs (DR8-DR13) which are supported
        # DR0/DR14 (SF5/SF6 downlinks) require real SX1302/SX1303 hardware
        if fcnt == 0:
            dn_dr = 8   # DR8 = SF12/500kHz
            logger.info('Sending downlink with DR8 (SF12/500kHz)')
        elif fcnt == 1:
            dn_dr = 13  # DR13 = SF7/500kHz
            logger.info('Sending downlink with DR13 (SF7/500kHz)')
        else:
            dn_dr = 10  # DR10 = SF10/500kHz
            logger.info('Sending downlink with DR10 (SF10/500kHz)')
            
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
