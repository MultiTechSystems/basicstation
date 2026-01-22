#!/usr/bin/env python3

"""
EU868 Duty Cycle Tests

Tests EU868 band-based duty cycle enforcement:
- 10% DC band (869.4-869.65 MHz) - DC_DECI
- 1% DC band (868.0-868.6 MHz, 869.7-870.0 MHz) - DC_CENTI  
- 0.1% DC band (everything else) - DC_MILLI

Sub-cases:
- DISABLED: duty_cycle_enabled: false - all frames pass
- BAND_10PCT: 10% band - rapid TX allowed
- BAND_1PCT: 1% band - some blocking
- BAND_01PCT: 0.1% band - heavy blocking
- MULTIBAND: Different bands have separate budgets
- WINDOW: Send to exhaust DC, wait, verify more can be sent
"""

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test9a-eu868')

sys.path.append('../../pysys')
import tcutils as tu
import simutils as su
import testutils as tstu


station = None
infos = None
muxs = None
sim = None
test_result = None

# EU868 DC band frequencies
BAND_DECI  = 869525000   # 10% DC band (869.4-869.65 MHz)
BAND_CENTI = 868100000   # 1% DC band (868.0-868.6 MHz)
BAND_MILLI = 867100000   # 0.1% DC band

# DC rates (multiplier on airtime for off-time)
# 10% = 10x, 1% = 100x, 0.1% = 1000x
# SF7/125kHz 6-byte payload ≈ 51ms airtime
# 10% band: 51ms * 10 = 510ms off-time
# 1% band: 51ms * 100 = 5.1s off-time  
# 0.1% band: 51ms * 1000 = 51s off-time

TEST_CASES = {
    'DISABLED': {
        'duty_cycle_enabled': False,
        'freqs': [(BAND_MILLI, BAND_MILLI)] * 5,
        'intervals': [1.5] * 5,
        'min_tx': 4, 'max_tx': 5,  # May get 4-5 due to timing
        'desc': 'duty_cycle_enabled: false - all frames pass'
    },
    'BAND_10PCT': {
        'duty_cycle_enabled': None,
        'freqs': [(BAND_DECI, BAND_DECI)] * 5,
        'intervals': [2.0] * 5,  # 2s allows RxDelay(1s) + TX + margin
        'min_tx': 4, 'max_tx': 5,
        'desc': '10% band (869.525MHz) - rapid TX allowed'
    },
    'BAND_1PCT': {
        'duty_cycle_enabled': None,
        'freqs': [(BAND_CENTI, BAND_CENTI)] * 5,
        'intervals': [2.0] * 5,  # 2s < 5.1s DC off-time, expect some blocking
        'min_tx': 1, 'max_tx': 3,  # Some blocking expected
        'desc': '1% band (868.1MHz) - some frames blocked'
    },
    'BAND_01PCT': {
        'duty_cycle_enabled': None,
        'freqs': [(BAND_MILLI, BAND_MILLI)] * 5,
        'intervals': [2.0] * 5,  # 2s << 51s DC off-time, heavy blocking
        'min_tx': 1, 'max_tx': 2,  # Heavy blocking expected
        'desc': '0.1% band (867.1MHz) - heavy blocking'
    },
    'MULTIBAND': {
        'duty_cycle_enabled': None,
        'freqs': [
            (BAND_DECI, BAND_DECI),    # 10% band
            (BAND_CENTI, BAND_CENTI),  # 1% band  
            (BAND_MILLI, BAND_MILLI),  # 0.1% band
            (BAND_DECI, BAND_DECI),    # 10% band again
            (BAND_CENTI, BAND_CENTI),  # 1% band again
        ],
        'intervals': [2.0] * 5,
        'min_tx': 3, 'max_tx': 5,
        'desc': 'Multi-band - each band has separate DC budget'
    },
    'WINDOW': {
        'duty_cycle_enabled': None,
        'freqs': [
            (BAND_DECI, BAND_DECI),  # TX 1 - succeeds
            (BAND_DECI, BAND_DECI),  # TX 2 - may block if too fast
            (BAND_DECI, BAND_DECI),  # TX 3 - after wait, should work
            (BAND_DECI, BAND_DECI),  # TX 4
            (BAND_DECI, BAND_DECI),  # TX 5
        ],
        'intervals': [1.0, 1.0, 2.5, 2.0, 2.0],  # Fast burst, wait, resume
        'min_tx': 3, 'max_tx': 5,
        'desc': 'Window test - exhaust DC, wait for recovery'
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
        logger.debug('LGWSIM - close')

    async def on_tx(self, lgwsim, pkt):
        logger.debug('LGWSIM: TX freq=%d' % pkt.get('freq_hz', 0))
        self.txcnt += 1

    async def send_updf(self) -> None:
        try:
            while True:
                idx = self.fcnt
                if idx < len(self.test_freqs):
                    upfreq, _ = self.test_freqs[idx]
                    interval = self.test_intervals[idx] if idx < len(self.test_intervals) else 1.5
                else:
                    upfreq = BAND_MILLI
                    interval = 1.5
                
                logger.debug('LGWSIM - UPDF FCnt=%d freq=%.3f' % (self.fcnt, upfreq/1e6))
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
            dnfreq = BAND_MILLI
            
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
    logger.info('EU868 Test: %s' % tc['desc'])
    logger.info('='*60)
    
    test_result = None
    
    with open("tc.uri", "w") as f:
        f.write('ws://localhost:6038')
    
    infos = tu.Infos(muxsuri='ws://localhost:6039/router')
    muxs = TestMuxs()
    muxs.router_config = tu.router_config_EU863_6ch
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
        await asyncio.wait_for(station.wait(), timeout=30)
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
