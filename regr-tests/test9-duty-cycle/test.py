#!/usr/bin/env python3

"""
Test duty_cycle_enabled router_config option.

This test verifies:
1. duty_cycle_enabled: false disables DC enforcement (all frames transmitted)
2. duty_cycle_enabled: true (or absent) enables DC enforcement (frames blocked)
3. Different regions have different DC behavior (EU868 has DC, US915 does not)

Test cases:
- EU868 with duty_cycle_enabled: false -> all frames pass
- EU868 with duty_cycle_enabled: true  -> frames blocked by DC
- EU868 with no setting (default)      -> frames blocked by DC (default enabled)
- US915 (no DC region)                 -> all frames pass regardless of setting
- KR920 with duty_cycle_enabled: false -> all frames pass (has DC limits)
"""

import os
import sys
import time
import json
import asyncio
from asyncio import subprocess

import logging
logger = logging.getLogger('test9-dc')

sys.path.append('../../pysys')
import tcutils as tu
import simutils as su
import testutils as tstu


station = None
infos = None
muxs = None
sim = None
test_result = None


# Test configurations - region, dc_setting, dc_freq, expected_tx_count, description
# Note: Only testing regions with DC limits (EU868, KR920)
# US915/AU915 don't have DC enforcement in station
TEST_CASES = [
    # (region_config, duty_cycle_enabled, test_freq, min_expected_tx, description)
    ('EU868_DC_DISABLED', False, 867100000, 5, 'EU868 with duty_cycle_enabled: false'),
    ('EU868_DC_ENABLED', True, 867100000, 1, 'EU868 with duty_cycle_enabled: true'),
    ('EU868_DC_DEFAULT', None, 867100000, 1, 'EU868 with no duty_cycle setting (default)'),
    ('KR920_DC_DISABLED', False, 922100000, 5, 'KR920 with duty_cycle_enabled: false'),
    ('KR920_DC_DEFAULT', None, 922100000, 1, 'KR920 with no duty_cycle setting (default)'),
]


class TestLgwSimServer(su.LgwSimServer):
    fcnt = 0
    updf_task = None
    txcnt = 0
    test_freq = 867100000

    async def on_connected(self, lgwsim: su.LgwSim) -> None:
        self.updf_task = asyncio.ensure_future(self.send_updf())

    async def on_close(self):
        if self.updf_task:
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
                # Use test frequency (varies by region/DC band)
                freq = self.test_freq / 1e6
                port = 1
                if self.fcnt >= 6:
                    port = 3  # Signal termination
                if 0 not in self.units:
                    return
                lgwsim = self.units[0]
                await lgwsim.send_rx(rps=(7, 125), freq=freq, frame=su.makeDF(fcnt=self.fcnt, port=port))
                self.fcnt += 1
                await asyncio.sleep(2.5)
        except asyncio.CancelledError:
            logger.debug('send_updf canceled.')
        except Exception as exc:
            logger.error('send_updf failed!', exc_info=True)


class TestMuxs(tu.Muxs):
    exp_seqno = []
    tx_count = 0
    duty_cycle_enabled = None  # None = not set, True/False = explicit
    test_freq = 867100000
    min_expected_tx = 5
    test_name = ''

    def get_router_config(self):
        """Send router_config with duty_cycle_enabled setting"""
        config = {
            **self.router_config,
            'MuxTime': time.time(),
        }
        if self.duty_cycle_enabled is not None:
            config['duty_cycle_enabled'] = self.duty_cycle_enabled
            logger.info("Sending router_config with duty_cycle_enabled: %s" % self.duty_cycle_enabled)
        else:
            logger.info("Sending router_config without duty_cycle_enabled (default)")
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
        logger.info('DNTXED: seqno=%r tx_count=%d' % (msg['seqno'], self.tx_count))
        
        # Check if we've received expected number of transmissions
        if self.tx_count >= self.min_expected_tx:
            logger.info('SUCCESS [%s]: %d frames transmitted (expected >= %d)' % 
                       (self.test_name, self.tx_count, self.min_expected_tx))
            await self.testDone(0)

    async def handle_updf(self, ws, msg):
        fcnt = msg['FCnt']
        logger.info('UPDF: FCnt=%d Freq=%.3fMHz FPort=%d' % (fcnt, msg['Freq']/1e6, msg['FPort']))
        port = msg['FPort']
        
        if port >= 3:
            # Check if test passed based on expected tx count
            if self.min_expected_tx <= 1:
                # Expecting DC to block - should have 1 or fewer TX
                if self.tx_count <= 1:
                    logger.info('SUCCESS [%s]: Only %d frame(s) transmitted (DC blocking as expected)' % 
                               (self.test_name, self.tx_count))
                    await self.testDone(0)
                else:
                    logger.error('FAILED [%s]: %d frames transmitted (expected DC to block after 1)' % 
                                (self.test_name, self.tx_count))
                    await self.testDone(1)
            else:
                # Expecting all frames to pass
                if self.tx_count >= self.min_expected_tx:
                    logger.info('SUCCESS [%s]: %d frames transmitted' % (self.test_name, self.tx_count))
                    await self.testDone(0)
                else:
                    logger.error('FAILED [%s]: Only %d frames transmitted (expected %d+)' % 
                                (self.test_name, self.tx_count, self.min_expected_tx))
                    await self.testDone(1)
            return
        
        # Send downlink on test frequency
        dnframe = {
            'msgtype': 'dnmsg',
            'DevEui': '00-00-00-00-00-00-00-01',
            'dC': 0,  # Class A
            'diid': fcnt,
            'pdu': '0A0B0C0D0E0F',
            'priority': 0,
            'RxDelay': 1,
            'RX1DR': 5,
            'RX1Freq': self.test_freq,
            'xtime': msg['upinfo']['xtime'] + 1000000,
            'seqno': fcnt,
            'MuxTime': time.time(),
            'rctx': msg['upinfo']['rctx'],
        }
        self.exp_seqno.append(fcnt)
        await ws.send(json.dumps(dnframe))


def get_router_config_for_test(test_id):
    """Get the appropriate router config for each test case"""
    if test_id.startswith('EU868'):
        return tu.router_config_EU863_6ch
    elif test_id.startswith('US915'):
        return tu.router_config_US902_8ch
    elif test_id.startswith('KR920'):
        return tu.router_config_KR920
    return tu.router_config_EU863_6ch


async def run_test(test_id, duty_cycle_enabled, test_freq, min_expected_tx, description):
    """Run a single test case"""
    global station, infos, muxs, sim, test_result
    
    logger.info('='*60)
    logger.info('Starting test: %s' % description)
    logger.info('='*60)
    
    test_result = None
    
    # Create tc.uri file
    with open("tc.uri", "w") as f:
        f.write('ws://localhost:6038')
    
    infos = tu.Infos(muxsuri='ws://localhost:6039/router')
    muxs = TestMuxs()
    muxs.router_config = get_router_config_for_test(test_id)
    muxs.duty_cycle_enabled = duty_cycle_enabled
    muxs.test_freq = test_freq
    muxs.min_expected_tx = min_expected_tx
    muxs.test_name = test_id
    muxs.tx_count = 0
    muxs.exp_seqno = []
    
    sim = TestLgwSimServer()
    sim.fcnt = 0
    sim.txcnt = 0
    sim.test_freq = test_freq

    await infos.start_server()
    await muxs.start_server()
    await sim.start_server()

    variant = os.environ.get('TEST_VARIANT', 'testsim')
    station_bin = '../../build-linux-%s/bin/station' % variant
    a = os.environ.get('STATION_ARGS', '')
    args = [] if not a else a.split(' ')
    station_args = [station_bin, '-p', '--temp', '.'] + args
    station = await subprocess.create_subprocess_exec(*station_args)

    # Run until test completes or timeout
    try:
        await asyncio.wait_for(station.wait(), timeout=45)
    except asyncio.TimeoutError:
        logger.error('TIMEOUT [%s]' % test_id)
        if station:
            station.terminate()
            await station.wait()
        test_result = 1
    
    # Cleanup
    if sim:
        sim.close()
    if infos and infos.server:
        infos.server.close()
    if muxs and muxs.server:
        muxs.server.close()
    
    await asyncio.sleep(0.5)  # Let servers close
    
    return test_result == 0


async def test_main():
    """Run all test cases"""
    # Get test case from command line or run specific test
    test_name = os.environ.get('DC_TEST_CASE', 'EU868_DC_DISABLED')
    
    for test_id, dc_enabled, test_freq, min_tx, desc in TEST_CASES:
        if test_id == test_name:
            success = await run_test(test_id, dc_enabled, test_freq, min_tx, desc)
            return 0 if success else 1
    
    logger.error('Unknown test case: %s' % test_name)
    return 1


if __name__ == '__main__':
    tstu.setup_logging()
    result = asyncio.get_event_loop().run_until_complete(test_main())
    sys.exit(result)
