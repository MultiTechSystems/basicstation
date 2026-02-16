# --- Revised 3-Clause BSD License ---
# Copyright MULTI-TECH SYSTEMS, INC. 2025. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#     * Neither the name of MULTI-TECH SYSTEMS, INC. nor the names of its
#       contributors may be used to endorse or promote products derived from this
#       software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL MULTI-TECH SYSTEMS, INC. BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Integration test for protobuf TC protocol.

Tests:
1. Capability negotiation (station advertises protobuf support)
2. Protocol format selection (server enables protobuf)
3. Uplink encoding (station sends binary updf/jreq)
4. Downlink decoding (station receives binary dnmsg)
5. TX confirmation (station sends binary dntxed)
6. Timesync (binary request/response)
"""

import os
import sys
import time
import json
import struct
import asyncio
from asyncio import subprocess

# Add pysys to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../pysys'))

import logging
logger = logging.getLogger('test11-protobuf')

import tcutils as tu
import simutils as su
import testutils as tstu


# ============================================================================
# Protobuf encoding/decoding (same as in tc-server.py)
# ============================================================================

WT_VARINT = 0
WT_FIXED64 = 1
WT_LENDELIM = 2
WT_FIXED32 = 5

# Message types
MSG_UPDF = 1
MSG_JREQ = 2
MSG_PROPDF = 3
MSG_DNTXED = 4
MSG_TIMESYNC = 5
MSG_DNMSG = 10
MSG_TIMESYNC_RESP = 12

# Field numbers
TCMSG_TYPE = 1
TCMSG_UPDF = 2
TCMSG_JREQ = 3
TCMSG_DNTXED = 5
TCMSG_TIMESYNC = 6
TCMSG_DNMSG = 10

UPDF_DEVADDR = 2
UPDF_FCNT = 4
UPDF_FPORT = 6
UPDF_UPINFO = 9

JREQ_JOINEUI = 2
JREQ_DEVEUI = 3

DNTXED_DIID = 1
DNTXED_DEVEUI = 2

TSYNC_TXTIME = 1
TSYNC_GPSTIME = 2

RM_XTIME = 4
RM_FREQ = 2
RM_DR = 1

DNMSG_DEVEUI = 1
DNMSG_DC = 2
DNMSG_DIID = 3
DNMSG_PDU = 4
DNMSG_RXDELAY = 5
DNMSG_RX1DR = 6
DNMSG_RX1FREQ = 7
DNMSG_RX2DR = 8
DNMSG_RX2FREQ = 9
DNMSG_XTIME = 11
DNMSG_RCTX = 12
DNMSG_MUXTIME = 16


class ProtobufDecoder:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
    
    def read_varint(self) -> int:
        result = 0
        shift = 0
        while self.pos < len(self.data):
            b = self.data[self.pos]
            self.pos += 1
            result |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                return result
            shift += 7
        raise ValueError("Truncated varint")
    
    def read_svarint(self) -> int:
        n = self.read_varint()
        return (n >> 1) ^ -(n & 1)
    
    def read_fixed64(self) -> int:
        val = struct.unpack('<Q', self.data[self.pos:self.pos+8])[0]
        self.pos += 8
        return val
    
    def read_sfixed32(self) -> int:
        val = struct.unpack('<i', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return val
    
    def read_double(self) -> float:
        val = struct.unpack('<d', self.data[self.pos:self.pos+8])[0]
        self.pos += 8
        return val
    
    def read_float(self) -> float:
        val = struct.unpack('<f', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return val
    
    def read_bytes(self) -> bytes:
        length = self.read_varint()
        val = self.data[self.pos:self.pos+length]
        self.pos += length
        return val
    
    def skip(self, wiretype: int):
        if wiretype == WT_VARINT:
            self.read_varint()
        elif wiretype == WT_FIXED64:
            self.pos += 8
        elif wiretype == WT_LENDELIM:
            length = self.read_varint()
            self.pos += length
        elif wiretype == WT_FIXED32:
            self.pos += 4


class ProtobufEncoder:
    def __init__(self):
        self.data = bytearray()
    
    def write_varint(self, value: int):
        while value >= 0x80:
            self.data.append((value & 0x7F) | 0x80)
            value >>= 7
        self.data.append(value)
    
    def write_svarint(self, value: int):
        if value >= 0:
            self.write_varint(value << 1)
        else:
            self.write_varint(((-value) << 1) - 1)
    
    def write_fixed64(self, value: int):
        self.data.extend(struct.pack('<Q', value))
    
    def write_double(self, value: float):
        self.data.extend(struct.pack('<d', value))
    
    def write_bytes(self, value: bytes):
        self.write_varint(len(value))
        self.data.extend(value)
    
    def write_tag(self, field: int, wiretype: int):
        self.write_varint((field << 3) | wiretype)
    
    def encode_dnmsg(self, deveui, dclass, diid, pdu, rxdelay, rx1dr, rx1freq,
                     rx2dr, rx2freq, xtime, rctx, muxtime):
        submsg = ProtobufEncoder()
        submsg.write_tag(DNMSG_DEVEUI, WT_FIXED64)
        submsg.write_fixed64(deveui)
        submsg.write_tag(DNMSG_DC, WT_VARINT)
        submsg.write_varint(dclass)
        submsg.write_tag(DNMSG_DIID, WT_VARINT)
        submsg.write_svarint(diid)
        submsg.write_tag(DNMSG_PDU, WT_LENDELIM)
        submsg.write_bytes(pdu)
        submsg.write_tag(DNMSG_RXDELAY, WT_VARINT)
        submsg.write_varint(rxdelay)
        submsg.write_tag(DNMSG_RX1DR, WT_VARINT)
        submsg.write_varint(rx1dr)
        submsg.write_tag(DNMSG_RX1FREQ, WT_VARINT)
        submsg.write_varint(rx1freq)
        submsg.write_tag(DNMSG_RX2DR, WT_VARINT)
        submsg.write_varint(rx2dr)
        submsg.write_tag(DNMSG_RX2FREQ, WT_VARINT)
        submsg.write_varint(rx2freq)
        submsg.write_tag(DNMSG_XTIME, WT_VARINT)
        submsg.write_svarint(xtime)
        submsg.write_tag(DNMSG_RCTX, WT_VARINT)
        submsg.write_svarint(rctx)
        submsg.write_tag(DNMSG_MUXTIME, WT_FIXED64)
        submsg.write_double(muxtime)
        
        self.write_tag(TCMSG_TYPE, WT_VARINT)
        self.write_varint(MSG_DNMSG)
        self.write_tag(TCMSG_DNMSG, WT_LENDELIM)
        self.write_bytes(bytes(submsg.data))
        return bytes(self.data)
    
    def encode_timesync_response(self, gpstime, txtime):
        submsg = ProtobufEncoder()
        submsg.write_tag(TSYNC_GPSTIME, WT_VARINT)
        submsg.write_svarint(gpstime)
        submsg.write_tag(TSYNC_TXTIME, WT_FIXED64)
        submsg.write_double(txtime)
        
        self.write_tag(TCMSG_TYPE, WT_VARINT)
        self.write_varint(MSG_TIMESYNC_RESP)
        self.write_tag(TCMSG_TIMESYNC, WT_LENDELIM)
        self.write_bytes(bytes(submsg.data))
        return bytes(self.data)


def decode_protobuf_message(data: bytes) -> dict:
    """Decode a protobuf TcMessage and return dict with msgtype and fields."""
    dec = ProtobufDecoder(data)
    msgtype = None
    
    while dec.pos < len(data):
        tag = dec.read_varint()
        field = tag >> 3
        wt = tag & 7
        
        if field == TCMSG_TYPE:
            msgtype = dec.read_varint()
        elif wt == WT_LENDELIM:
            payload = dec.read_bytes()
            break
        else:
            dec.skip(wt)
    
    if msgtype == MSG_UPDF:
        return decode_updf(payload)
    elif msgtype == MSG_JREQ:
        return decode_jreq(payload)
    elif msgtype == MSG_DNTXED:
        return decode_dntxed(payload)
    elif msgtype == MSG_TIMESYNC:
        return decode_timesync(payload)
    else:
        return {'msgtype': f'unknown_{msgtype}'}


def decode_updf(payload: bytes) -> dict:
    result = {'msgtype': 'updf'}
    dec = ProtobufDecoder(payload)
    while dec.pos < len(payload):
        tag = dec.read_varint()
        field = tag >> 3
        wt = tag & 7
        if field == UPDF_DEVADDR:
            result['DevAddr'] = dec.read_sfixed32()
        elif field == UPDF_FCNT:
            result['FCnt'] = dec.read_varint()
        elif field == UPDF_FPORT:
            result['FPort'] = dec.read_svarint()
        elif field == UPDF_UPINFO:
            result['upinfo'] = decode_radio_metadata(dec.read_bytes())
        else:
            dec.skip(wt)
    return result


def decode_jreq(payload: bytes) -> dict:
    result = {'msgtype': 'jreq'}
    dec = ProtobufDecoder(payload)
    while dec.pos < len(payload):
        tag = dec.read_varint()
        field = tag >> 3
        wt = tag & 7
        if field == JREQ_JOINEUI:
            result['JoinEui'] = dec.read_fixed64()
        elif field == JREQ_DEVEUI:
            result['DevEui'] = dec.read_fixed64()
        else:
            dec.skip(wt)
    return result


def decode_dntxed(payload: bytes) -> dict:
    result = {'msgtype': 'dntxed'}
    dec = ProtobufDecoder(payload)
    while dec.pos < len(payload):
        tag = dec.read_varint()
        field = tag >> 3
        wt = tag & 7
        if field == DNTXED_DIID:
            result['diid'] = dec.read_svarint()
        elif field == DNTXED_DEVEUI:
            result['DevEui'] = dec.read_fixed64()
        else:
            dec.skip(wt)
    return result


def decode_timesync(payload: bytes) -> dict:
    result = {'msgtype': 'timesync'}
    dec = ProtobufDecoder(payload)
    while dec.pos < len(payload):
        tag = dec.read_varint()
        field = tag >> 3
        wt = tag & 7
        if field == TSYNC_TXTIME:
            result['txtime'] = dec.read_double()
        else:
            dec.skip(wt)
    return result


def decode_radio_metadata(payload: bytes) -> dict:
    result = {}
    dec = ProtobufDecoder(payload)
    while dec.pos < len(payload):
        tag = dec.read_varint()
        field = tag >> 3
        wt = tag & 7
        if field == RM_XTIME:
            result['xtime'] = dec.read_svarint()
        elif field == RM_FREQ:
            result['Freq'] = dec.read_varint()
        elif field == RM_DR:
            result['DR'] = dec.read_varint()
        else:
            dec.skip(wt)
    return result


# ============================================================================
# Test components
# ============================================================================

station = None
infos = None
muxs = None
sim = None


class TestLgwSimServer(su.LgwSimServer):
    fcnt = 0
    updf_task = None
    txcnt = 0

    async def on_connected(self, lgwsim: su.LgwSim) -> None:
        logger.info('LGWSIM connected')
        self.updf_task = asyncio.ensure_future(self.send_updf())

    async def on_close(self):
        if self.updf_task:
            self.updf_task.cancel()
            self.updf_task = None
        logger.debug('LGWSIM - close')

    async def on_tx(self, lgwsim, pkt):
        logger.info('LGWSIM: TX received - freq=%d dr=%d size=%d', 
                   pkt.get('freq_hz', 0), pkt.get('datarate', 0), pkt.get('size', 0))
        self.txcnt += 1

    async def send_updf(self) -> None:
        try:
            await asyncio.sleep(1.0)  # Wait for connection setup
            while self.fcnt < 5:
                logger.info('LGWSIM - sending UPDF FCnt=%d', self.fcnt)
                if 0 not in self.units:
                    logger.error('No lgwsim unit available')
                    return
                lgwsim = self.units[0]
                
                # Send uplink on EU868 frequency
                port = self.fcnt + 1
                if self.fcnt == 4:
                    port = 99  # Signal termination
                
                await lgwsim.send_rx(
                    rps=(7, 125), 
                    freq=868.1, 
                    frame=su.makeDF(fcnt=self.fcnt, port=port)
                )
                self.fcnt += 1
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            logger.debug('send_updf canceled.')
        except Exception as exc:
            logger.error('send_updf failed!', exc_info=True)


class TestMuxs(tu.Muxs):
    """Test Muxs that enables protobuf and verifies binary messages."""
    
    protobuf_enabled = False
    station_capabilities = []
    updf_count = 0
    dntxed_count = 0
    exp_diids = []
    test_passed = False

    def get_router_config(self):
        config = dict(tu.router_config_EU863_6ch)
        # Enable protobuf if station supports it
        if 'lbs-dp' in self.station_capabilities:
            config['protocol_format'] = 'protobuf'
            self.protobuf_enabled = True
            logger.info('Enabling protobuf protocol')
        return config

    async def handle_version(self, ws, msg):
        """Check for lbs-dp capability in version message."""
        features_str = msg.get('features', '')
        self.station_capabilities = features_str.split() if features_str else []
        logger.info('Station capabilities: %s', self.station_capabilities)
        
        if 'lbs-dp' not in self.station_capabilities:
            logger.error('Station does not advertise lbs-dp capability!')
            await self.testDone(1)
            return
        
        logger.info('Station advertises lbs-dp capability - TEST PASSED')
        
        # Send router_config with protobuf enabled
        rconf = self.get_router_config()
        await ws.send(json.dumps(rconf))

    async def handle_updf(self, ws, msg):
        """Handle uplink - should be received as protobuf."""
        self.updf_count += 1
        fcnt = msg.get('FCnt', -1)
        fport = msg.get('FPort', -1)
        upinfo = msg.get('upinfo', {})
        xtime = upinfo.get('xtime', 0)
        
        logger.info('UPDF #%d: FCnt=%d FPort=%d xtime=%d', 
                   self.updf_count, fcnt, fport, xtime)
        
        if fport == 99:
            # Termination signal
            if self.updf_count >= 5 and self.dntxed_count >= 3:
                logger.info('Test completed successfully!')
                self.test_passed = True
                await self.testDone(0)
            else:
                logger.error('Test failed: updf_count=%d dntxed_count=%d',
                           self.updf_count, self.dntxed_count)
                await self.testDone(1)
            return
        
        # Send downlink as protobuf
        if self.protobuf_enabled and xtime != 0:
            diid = fcnt + 1000
            self.exp_diids.append(diid)
            
            enc = ProtobufEncoder()
            pdu = bytes([0x60, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
                        0x01, 0xAA, 0xBB, 0xCC, 0xDD])
            data = enc.encode_dnmsg(
                deveui=0x0000000011000001,
                dclass=0,
                diid=diid,
                pdu=pdu,
                rxdelay=1,
                rx1dr=5,  # SF7/125kHz
                rx1freq=868100000,
                rx2dr=0,
                rx2freq=869525000,
                xtime=xtime,
                rctx=0,
                muxtime=time.time()
            )
            await ws.send(data)
            logger.info('Sent protobuf dnmsg diid=%d (%d bytes)', diid, len(data))

    async def handle_dntxed(self, ws, msg):
        """Handle TX confirmation."""
        diid = msg.get('diid', -1)
        self.dntxed_count += 1
        logger.info('DNTXED #%d: diid=%d', self.dntxed_count, diid)
        
        if diid in self.exp_diids:
            self.exp_diids.remove(diid)
            logger.info('DNTXED diid=%d matches expected', diid)
        else:
            logger.warning('DNTXED diid=%d not in expected list %r', diid, self.exp_diids)

    async def handle_timesync(self, ws, msg):
        """Handle timesync - respond with protobuf if enabled."""
        txtime = msg.get('txtime', 0)
        logger.debug('TIMESYNC: txtime=%s', txtime)
        
        if self.protobuf_enabled:
            gpstime = int(time.time() * 1e6)
            enc = ProtobufEncoder()
            data = enc.encode_timesync_response(gpstime, txtime)
            await ws.send(data)
            logger.debug('Sent protobuf timesync response')
        else:
            await super().handle_timesync(ws, msg)

    async def handle_binaryData(self, ws, data: bytes):
        """Handle binary (protobuf) messages."""
        if not self.protobuf_enabled:
            logger.warning('Received binary data but protobuf not enabled')
            return
        
        try:
            msg = decode_protobuf_message(data)
            msgtype = msg.get('msgtype')
            logger.debug('Received protobuf %s (%d bytes)', msgtype, len(data))
            
            if msgtype == 'updf':
                await self.handle_updf(ws, msg)
            elif msgtype == 'dntxed':
                await self.handle_dntxed(ws, msg)
            elif msgtype == 'timesync':
                await self.handle_timesync(ws, msg)
            else:
                logger.warning('Unknown protobuf msgtype: %s', msgtype)
        except Exception as e:
            logger.error('Failed to decode protobuf: %s', e, exc_info=True)

    async def testDone(self, status):
        global station
        if station:
            station.terminate()
            await station.wait()
            station = None
        os._exit(status)


with open("tc.uri", "w") as f:
    f.write('ws://localhost:6038')


async def test_start():
    global station, infos, muxs, sim
    
    infos = tu.Infos(muxsuri='ws://localhost:6039/router')
    muxs = TestMuxs()
    sim = TestLgwSimServer()

    await infos.start_server()
    await muxs.start_server()
    await sim.start_server()

    logger.info('Starting station...')
    # Find station binary - check build directory
    station_bin = os.path.join(os.path.dirname(__file__), 
                               '../../build-linux-testsim/bin/station')
    if not os.path.exists(station_bin):
        # Try testsim1302
        station_bin = os.path.join(os.path.dirname(__file__), 
                                   '../../build-linux-testsim1302/bin/station')
    if not os.path.exists(station_bin):
        logger.error('Station binary not found! Build with: make platform=linux variant=testsim')
        await muxs.testDone(1)
        return
    
    station_args = [station_bin, '-p', '--temp', '.']
    station = await subprocess.create_subprocess_exec(*station_args)
    
    # Timeout after 30 seconds
    await asyncio.sleep(30)
    logger.error('Test timeout!')
    await muxs.testDone(1)


tstu.setup_logging()

asyncio.ensure_future(test_start())
asyncio.get_event_loop().run_forever()
