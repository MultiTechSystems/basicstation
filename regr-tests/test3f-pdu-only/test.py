import os
import sys
import time
import json
import asyncio
import base64
import re
from asyncio import subprocess

import logging
logger = logging.getLogger('test3f-pdu-only')

import tcutils as tu
import simutils as su
import testutils as tstu

station = None
infos = None
muxs = None
sim = None

# Test mode: 'hex' or 'base64'
test_encoding = os.environ.get('PDU_ENCODING', 'hex')

def is_valid_hex(s):
    """Check if string is valid hexadecimal"""
    return bool(re.match(r'^[0-9A-Fa-f]+$', s))

def is_valid_base64(s):
    """Check if string is valid base64"""
    try:
        # Check for valid base64 characters and padding
        if not re.match(r'^[A-Za-z0-9+/]*={0,2}$', s):
            return False
        base64.b64decode(s)
        return True
    except Exception:
        return False

class TestLgwSimServer(su.LgwSimServer):
    async def on_connected(self, lgwsim:su.LgwSim) -> None:
        # Wait for router config to be sent and processed, then send test frame
        logger.debug('LGWSIM - Waiting for config to be sent')
        while not muxs.config_sent:
            await asyncio.sleep(0.1)
        await asyncio.sleep(3.0)  # Extra time for processing
        logger.debug('LGWSIM - Sending test frame')
        if 0 in self.units:
            lgwsim = self.units[0]
            await lgwsim.send_rx(rps=(7,125), freq=869.525, frame=su.makeDF(fcnt=0, port=1))

class TestMuxs(tu.Muxs):
    def __init__(self, tlsidentity=None, tls_no_ca=False):
        super().__init__(tlsidentity=tlsidentity, tls_no_ca=tls_no_ca)
        self.test_completed = False
        self.config_sent = False

    async def testDone(self, status):
        global station
        if station:
            station.terminate()
            await station.wait()
            station = None
        os._exit(status)

    async def handle_version(self, ws, msg):
        logger.debug('Station version received: %r' % msg)
        # Version message received, now we can assume station is ready for config
        self.config_sent = True
        await super().handle_version(ws, msg)

    async def handle_updf(self, ws, msg):
        logger.debug('UPDF received: %r' % msg)
        # Check for PDU-only format
        if 'pdu' not in msg:
            logger.error('PDU-only mode verification failed - no pdu field')
            await self.testDone(1)
            return
        
        if 'MHdr' in msg or 'DevAddr' in msg:
            logger.error('PDU-only mode verification failed - still has parsed fields')
            await self.testDone(1)
            return
        
        pdu = msg['pdu']
        
        # Verify encoding format
        if test_encoding == 'base64':
            if is_valid_base64(pdu) and not is_valid_hex(pdu):
                # Base64 strings that aren't valid hex (to distinguish)
                # Actually, some base64 could be valid hex, so check length ratio
                # Hex is 2x binary length, base64 is ~1.33x
                # For a frame, base64 should be shorter than hex would be
                logger.info('PDU-only mode with base64 encoding verified successfully')
                logger.info('PDU (base64): %s', pdu)
                self.test_completed = True
                await self.testDone(0)
            elif is_valid_hex(pdu):
                logger.error('PDU-only mode: expected base64 but got hex encoding')
                await self.testDone(1)
            else:
                logger.error('PDU-only mode: pdu is neither valid hex nor base64')
                await self.testDone(1)
        else:  # hex encoding (default)
            if is_valid_hex(pdu):
                logger.info('PDU-only mode with hex encoding verified successfully')
                logger.info('PDU (hex): %s', pdu)
                self.test_completed = True
                await self.testDone(0)
            else:
                logger.error('PDU-only mode: expected hex but got invalid format')
                await self.testDone(1)

    async def handle_ws(self, ws):
        print('TEST: handle_ws called')
        await super().handle_ws(ws)
        print('TEST: handle_ws completed')

    def get_router_config(self):
        config = super().get_router_config()
        config['pdu_only'] = True  # Enable PDU-only mode
        if test_encoding == 'base64':
            config['pdu_encoding'] = 'base64'
        with open('debug.log', 'a') as f:
            f.write(f'TEST: Sending router config with PDU-only enabled (encoding={test_encoding})\n')
        logger.info('Router config: pdu_only=True, pdu_encoding=%s', test_encoding)
        return config

tls_mode  = (sys.argv[1:2] == ['tls'])
tls_no_ca = (sys.argv[2:3] == ['no_ca'])

ws = 'wss' if tls_mode else 'ws'

# Create tc.uri file for station to connect to
with open("tc.uri","w") as f:
    f.write('%s://localhost:6038' % ws)

async def test_start():
    global station, infos, muxs, sim
    infos = tu.Infos(muxsuri=('%s://localhost:6039/router' % ws),
                     tlsidentity=('infos-0' if tls_mode else None),
                     tls_no_ca=tls_no_ca)
    muxs = TestMuxs(tlsidentity='muxs-0' if tls_mode else None, tls_no_ca=tls_no_ca)
    sim = TestLgwSimServer()

    await infos.start_server()
    await muxs.start_server()
    await sim.start_server()

    print(f"DEBUG: Current dir: {os.getcwd()}")
    print(f"DEBUG: station.conf exists: {os.path.exists('station.conf')}")
    a = os.environ.get('STATION_ARGS','')
    args = [] if not a else a.split(' ')
    station_args = ['station','-p', '--temp', '.'] + args
    print(f"DEBUG: Running: {station_args}")
    station = await subprocess.create_subprocess_exec(*station_args, cwd='.')

tstu.setup_logging()

asyncio.ensure_future(test_start())
asyncio.get_event_loop().run_forever()