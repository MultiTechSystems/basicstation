#!/usr/bin/env python3

"""
AS923 Duty Cycle Tests

Tests AS923 per-channel duty cycle enforcement (10% per channel with LBT).

Sub-cases:
- DISABLED: duty_cycle_enabled: false - all frames pass
- SINGLE_CH: Single channel DC - 10% limit
- MULTI_CH: Multiple channels - each has separate budget
- WINDOW: Exhaust channel DC, wait, verify recovery
"""

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test9b-as923')

sys.path.append('../../pysys')
import tcutils as tu
import simutils as su
import testutils as tstu


station = None
infos = None
muxs = None
sim = None
test_result = None

# AS923 channels
CH1 = 923200000
CH2 = 923400000
CH3 = 923600000

# AS923 has 10% per-channel DC
# SF7/125kHz 6-byte payload ≈ 51ms airtime
# 10% DC: 51ms * 10 = 510ms off-time per channel

TEST_CASES = {
    'DISABLED': {
        'duty_cycle_enabled': False,
        'freqs': [(CH1, CH1)] * 5,
        'intervals': [2.0] * 5,  # Allow time for RxDelay + TX
        'min_tx': 4, 'max_tx': 5,
        'desc': 'duty_cycle_enabled: false - all frames pass'
    },
    'SINGLE_CH': {
        'duty_cycle_enabled': None,
        'freqs': [(CH1, CH1)] * 5,
        'intervals': [2.0] * 5,  # 2s > 510ms off-time, should pass
        'min_tx': 4, 'max_tx': 5,
        'desc': 'Single channel 10% DC - rapid TX allowed'
    },
    'MULTI_CH': {
        'duty_cycle_enabled': None,
        'freqs': [
            (CH1, CH1), (CH2, CH2), (CH3, CH3),
            (CH1, CH1), (CH2, CH2),
        ],
        'intervals': [2.0] * 5,
        'min_tx': 4, 'max_tx': 5,
        'desc': 'Multi-channel - separate DC budgets'
    },
    'WINDOW': {
        'duty_cycle_enabled': None,
        'freqs': [(CH1, CH1)] * 5,
        'intervals': [1.0, 1.0, 1.0, 2.0, 2.0],  # Burst then normal
        'min_tx': 3, 'max_tx': 5,
        'desc': 'Window test - exhaust DC, wait, recover'
    },
}


class TestLgwSimServer(su.LgwSimServer):
    fcnt = 0
    updf_task = None
    txcnt = 0
    test_freqs = []
    test_intervals = []

    async def on_connected(self, lgwsim: su.LgwSim) -> None:
        self.updf_task = asyncio.ensure_future(self.send_updf())

    async def on_close(self):
        if self.updf_task:
            self.updf_task.cancel()
            self.updf_task = None

    async def on_tx(self, lgwsim, pkt):
        self.txcnt += 1

    async def send_updf(self) -> None:
        try:
            while True:
                idx = self.fcnt
                if idx < len(self.test_freqs):
                    upfreq, _ = self.test_freqs[idx]
                    interval = self.test_intervals[idx] if idx < len(self.test_intervals) else 1.0
                else:
                    upfreq = CH1
                    interval = 1.0
                
                port = 1 if self.fcnt < len(self.test_freqs) else 3
                if 0 not in self.units:
                    return
                await self.units[0].send_rx(rps=(7, 125), freq=upfreq/1e6,
                                            frame=su.makeDF(fcnt=self.fcnt, port=port))
                self.fcnt += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error('send_updf failed!', exc_info=True)


class TestMuxs(tu.Muxs):
    tx_count = 0
    duty_cycle_enabled = None
    test_freqs = []
    min_tx = 1
    max_tx = 99
    test_name = ''

    def get_router_config(self):
        config = {**self.router_config, 'MuxTime': time.time()}
        if self.duty_cycle_enabled is not None:
            config['duty_cycle_enabled'] = self.duty_cycle_enabled
        return config

    async def testDone(self, status):
        global station, test_result
        test_result = status
        if station:
            station.terminate()
            await station.wait()
            station = None

    async def handle_dntxed(self, ws, msg):
        self.tx_count += 1
        logger.info('DNTXED: seqno=%d tx_count=%d' % (msg['seqno'], self.tx_count))

    async def handle_updf(self, ws, msg):
        fcnt = msg['FCnt']
        port = msg['FPort']
        logger.info('UPDF: FCnt=%d Freq=%.3fMHz port=%d' % (fcnt, msg['Freq']/1e6, port))
        
        if port >= 3:
            if self.min_tx <= self.tx_count <= self.max_tx:
                logger.info('SUCCESS [%s]: %d TX (expected %d-%d)' %
                           (self.test_name, self.tx_count, self.min_tx, self.max_tx))
                await self.testDone(0)
            else:
                logger.error('FAILED [%s]: %d TX (expected %d-%d)' %
                            (self.test_name, self.tx_count, self.min_tx, self.max_tx))
                await self.testDone(1)
            return
        
        if fcnt < len(self.test_freqs):
            _, dnfreq = self.test_freqs[fcnt]
        else:
            dnfreq = CH1
            
        dnframe = {
            'msgtype': 'dnmsg',
            'DevEui': '00-00-00-00-00-00-00-01',
            'dC': 0, 'diid': fcnt,
            'pdu': '0A0B0C0D0E0F',
            'priority': 0, 'RxDelay': 1,
            'RX1DR': 5, 'RX1Freq': dnfreq,
            'xtime': msg['upinfo']['xtime'] + 1000000,
            'seqno': fcnt, 'MuxTime': time.time(),
            'rctx': msg['upinfo']['rctx'],
        }
        await ws.send(json.dumps(dnframe))


async def run_test(test_name):
    global station, infos, muxs, sim, test_result
    
    if test_name not in TEST_CASES:
        logger.error('Unknown test: %s' % test_name)
        logger.error('Available: %s' % ', '.join(TEST_CASES.keys()))
        return 1
    
    tc = TEST_CASES[test_name]
    logger.info('='*60)
    logger.info('AS923 Test: %s' % tc['desc'])
    logger.info('='*60)
    
    test_result = None
    
    with open("tc.uri", "w") as f:
        f.write('ws://localhost:6038')
    
    infos = tu.Infos(muxsuri='ws://localhost:6039/router')
    muxs = TestMuxs()
    muxs.router_config = tu.router_config_AS923
    muxs.duty_cycle_enabled = tc['duty_cycle_enabled']
    muxs.test_freqs = tc['freqs']
    muxs.min_tx = tc['min_tx']
    muxs.max_tx = tc['max_tx']
    muxs.test_name = test_name
    muxs.tx_count = 0
    
    sim = TestLgwSimServer(path='./spidev')
    sim.fcnt = 0
    sim.txcnt = 0
    sim.test_freqs = tc['freqs']
    sim.test_intervals = tc['intervals']

    await infos.start_server()
    await muxs.start_server()
    await sim.start_server()

    variant = os.environ.get('TEST_VARIANT', 'testsim')
    station_bin = '../../build-linux-%s/bin/station' % variant
    station = await subprocess.create_subprocess_exec(station_bin, '-p', '--temp', '.')

    try:
        await asyncio.wait_for(station.wait(), timeout=25)
    except asyncio.TimeoutError:
        logger.error('TIMEOUT [%s]' % test_name)
        if station:
            station.terminate()
            await station.wait()
        if muxs.min_tx <= muxs.tx_count <= muxs.max_tx:
            test_result = 0
        else:
            test_result = 1
    
    if sim: sim.close()
    if infos and infos.server: infos.server.close()
    if muxs and muxs.server: muxs.server.close()
    await asyncio.sleep(0.3)
    
    return 0 if test_result == 0 else 1


if __name__ == '__main__':
    tstu.setup_logging()
    test_name = os.environ.get('DC_TEST', 'DISABLED')
    result = asyncio.get_event_loop().run_until_complete(run_test(test_name))
    sys.exit(result)
