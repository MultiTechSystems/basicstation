#!/usr/bin/env python3
"""
Standalone TC server for testing real gateways.

Usage:
    python3 tc-server.py [options]

Options:
    --host IP            IP address for muxs redirect (required for real gateways)
    --region REGION      Region: EU868, US915, AU915, AS923, KR920, IN865 (default: US915)
    --pdu-only           Enable pdu_only mode
    --protobuf           Enable protobuf binary protocol (requires station with protobuf support)
    --duty-cycle on|off  Explicitly enable/disable duty cycle (sends duty_cycle_enabled field)
    --dc-mode MODE       Duty cycle mode: legacy, band, channel (for sliding window)
    --dc-limits          Send region-specific duty cycle limits
    --lbt on|off         Explicitly enable/disable LBT (sends lbt_enabled field)
    --lbt-channels       Send region-specific LBT channel configuration
    --asym-dr            Use asymmetric uplink/downlink DRs (RP2 1.0.5)
    --single-radio [bad] Disable radio_1 for 3-channel mode (use 'bad' for incomplete config)
    --tls                Enable TLS (requires certs in pki-data/)
    --verbose            Verbose logging

Example:
    # Basic server for US915 gateway (use your machine's IP)
    python3 tc-server.py --host 10.10.200.208 --region US915

    # Test pdu-only feature
    python3 tc-server.py --host 10.10.200.208 --region US915 --pdu-only

    # Test protobuf binary protocol
    python3 tc-server.py --host 10.10.200.208 --region US915 --protobuf

    # Test protobuf with automatic downlinks
    python3 tc-server.py --host 10.10.200.208 --region US915 --protobuf --auto-downlink

    # Test AU915 with asymmetric DRs
    python3 tc-server.py --host 10.10.200.208 --region AU915 --asym-dr

    # Explicitly disable duty cycle
    python3 tc-server.py --host 10.10.200.208 --region EU868 --duty-cycle off

    # Use sliding window duty cycle with band limits (EU868)
    python3 tc-server.py --host 10.10.200.208 --region EU868 --dc-mode band --dc-limits

    # Use channel-based duty cycle (AS923)
    python3 tc-server.py --host 10.10.200.208 --region AS923 --dc-mode channel --dc-limits

    # Explicitly enable LBT with channel config
    python3 tc-server.py --host 10.10.200.208 --region AS923 --lbt on --lbt-channels

    # Explicitly disable LBT (sends lbt_enabled: false)
    python3 tc-server.py --host 10.10.200.208 --region AS923 --lbt off

    # Test with single radio (radio_1 disabled, proper 3-channel config)
    python3 tc-server.py --host 10.10.200.208 --region EU868 --single-radio

    # Test with single radio using incomplete "bad" config (only disables radio_1)
    python3 tc-server.py --host 10.10.200.208 --region EU868 --single-radio bad

Ports:
    Infos (initial connection): 6038
    Muxs (traffic): 6039
"""

import os
import sys
import argparse
import asyncio
import json
import logging
import socket
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../pysys'))

import tcutils as tu

# ============================================================================
# Protobuf support (manual encoding/decoding without protobuf library)
# ============================================================================

# Wire types
WT_VARINT = 0
WT_FIXED64 = 1
WT_LENDELIM = 2
WT_FIXED32 = 5

# Message types (from tc.proto)
MSG_UPDF = 1
MSG_JREQ = 2
MSG_PROPDF = 3
MSG_DNTXED = 4
MSG_TIMESYNC = 5
MSG_DNMSG = 10
MSG_DNSCHED = 11
MSG_TIMESYNC_RESP = 12

# TcMessage field numbers
TCMSG_TYPE = 1
TCMSG_UPDF = 2
TCMSG_JREQ = 3
TCMSG_PROPDF = 4
TCMSG_DNTXED = 5
TCMSG_TIMESYNC = 6
TCMSG_DNMSG = 10

# Field numbers for various messages
UPDF_MHDR = 1
UPDF_DEVADDR = 2
UPDF_FCTRL = 3
UPDF_FCNT = 4
UPDF_FOPTS = 5
UPDF_FPORT = 6
UPDF_FRMPAYLOAD = 7
UPDF_MIC = 8
UPDF_UPINFO = 9
UPDF_REFTIME = 10

JREQ_MHDR = 1
JREQ_JOINEUI = 2
JREQ_DEVEUI = 3
JREQ_DEVNONCE = 4
JREQ_MIC = 5
JREQ_UPINFO = 6
JREQ_REFTIME = 7

PROPDF_FRMPAYLOAD = 1
PROPDF_UPINFO = 2
PROPDF_REFTIME = 3

DNTXED_DIID = 1
DNTXED_DEVEUI = 2
DNTXED_RCTX = 3
DNTXED_XTIME = 4
DNTXED_TXTIME = 5
DNTXED_GPSTIME = 6

TSYNC_TXTIME = 1
TSYNC_GPSTIME = 2
TSYNC_XTIME = 3

RM_DR = 1
RM_FREQ = 2
RM_RCTX = 3
RM_XTIME = 4
RM_GPSTIME = 5
RM_RSSI = 6
RM_SNR = 7
RM_FTS = 8
RM_RXTIME = 9

DNMSG_DEVEUI = 1
DNMSG_DC = 2
DNMSG_DIID = 3
DNMSG_PDU = 4
DNMSG_RXDELAY = 5
DNMSG_RX1DR = 6
DNMSG_RX1FREQ = 7
DNMSG_RX2DR = 8
DNMSG_RX2FREQ = 9
DNMSG_PRIORITY = 10
DNMSG_XTIME = 11
DNMSG_RCTX = 12
DNMSG_GPSTIME = 13
DNMSG_DR = 14
DNMSG_FREQ = 15
DNMSG_MUXTIME = 16


class ProtobufDecoder:
    """Decode protobuf messages from station."""
    
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
        """Read signed varint (zigzag encoded)."""
        n = self.read_varint()
        return (n >> 1) ^ -(n & 1)
    
    def read_fixed32(self) -> int:
        if self.pos + 4 > len(self.data):
            raise ValueError("Truncated fixed32")
        val = struct.unpack('<I', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return val
    
    def read_sfixed32(self) -> int:
        if self.pos + 4 > len(self.data):
            raise ValueError("Truncated sfixed32")
        val = struct.unpack('<i', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return val
    
    def read_fixed64(self) -> int:
        if self.pos + 8 > len(self.data):
            raise ValueError("Truncated fixed64")
        val = struct.unpack('<Q', self.data[self.pos:self.pos+8])[0]
        self.pos += 8
        return val
    
    def read_double(self) -> float:
        if self.pos + 8 > len(self.data):
            raise ValueError("Truncated double")
        val = struct.unpack('<d', self.data[self.pos:self.pos+8])[0]
        self.pos += 8
        return val
    
    def read_float(self) -> float:
        if self.pos + 4 > len(self.data):
            raise ValueError("Truncated float")
        val = struct.unpack('<f', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return val
    
    def read_bytes(self) -> bytes:
        length = self.read_varint()
        if self.pos + length > len(self.data):
            raise ValueError("Truncated bytes")
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
        else:
            raise ValueError(f"Unknown wire type: {wiretype}")
    
    def decode_radio_metadata(self) -> dict:
        """Decode RadioMetadata submessage."""
        result = {}
        submsg_data = self.read_bytes()
        sub = ProtobufDecoder(submsg_data)
        while sub.pos < len(submsg_data):
            tag = sub.read_varint()
            field = tag >> 3
            wt = tag & 7
            if field == RM_DR:
                result['DR'] = sub.read_varint()
            elif field == RM_FREQ:
                result['Freq'] = sub.read_varint()
            elif field == RM_RCTX:
                result['rctx'] = sub.read_svarint()
            elif field == RM_XTIME:
                result['xtime'] = sub.read_svarint()
            elif field == RM_GPSTIME:
                result['gpstime'] = sub.read_svarint()
            elif field == RM_RSSI:
                result['rssi'] = sub.read_svarint()
            elif field == RM_SNR:
                result['snr'] = sub.read_float()
            elif field == RM_FTS:
                result['fts'] = sub.read_svarint()
            elif field == RM_RXTIME:
                result['rxtime'] = sub.read_double()
            else:
                sub.skip(wt)
        return result
    
    def decode_updf(self) -> dict:
        """Decode UplinkDataFrame message."""
        result = {'msgtype': 'updf'}
        submsg_data = self.read_bytes()
        sub = ProtobufDecoder(submsg_data)
        while sub.pos < len(submsg_data):
            tag = sub.read_varint()
            field = tag >> 3
            wt = tag & 7
            if field == UPDF_MHDR:
                result['MHdr'] = sub.read_varint()
            elif field == UPDF_DEVADDR:
                result['DevAddr'] = sub.read_sfixed32()
            elif field == UPDF_FCTRL:
                result['FCtrl'] = sub.read_varint()
            elif field == UPDF_FCNT:
                result['FCnt'] = sub.read_varint()
            elif field == UPDF_FOPTS:
                result['FOpts'] = sub.read_bytes().hex()
            elif field == UPDF_FPORT:
                result['FPort'] = sub.read_svarint()
            elif field == UPDF_FRMPAYLOAD:
                result['FRMPayload'] = sub.read_bytes().hex()
            elif field == UPDF_MIC:
                result['MIC'] = sub.read_sfixed32()
            elif field == UPDF_UPINFO:
                # Need to parse submessage
                sub.pos -= 1  # Back up to re-read tag for read_bytes
                while sub.data[sub.pos] & 0x80:
                    sub.pos -= 1
                sub.pos += 1
                result['upinfo'] = sub.decode_radio_metadata()
            elif field == UPDF_REFTIME:
                result['RefTime'] = sub.read_double()
            else:
                sub.skip(wt)
        return result
    
    def decode_jreq(self) -> dict:
        """Decode JoinRequest message."""
        result = {'msgtype': 'jreq'}
        submsg_data = self.read_bytes()
        sub = ProtobufDecoder(submsg_data)
        while sub.pos < len(submsg_data):
            tag = sub.read_varint()
            field = tag >> 3
            wt = tag & 7
            if field == JREQ_MHDR:
                result['MHdr'] = sub.read_varint()
            elif field == JREQ_JOINEUI:
                result['JoinEui'] = f"{sub.read_fixed64():016X}"
            elif field == JREQ_DEVEUI:
                result['DevEui'] = f"{sub.read_fixed64():016X}"
            elif field == JREQ_DEVNONCE:
                result['DevNonce'] = sub.read_varint()
            elif field == JREQ_MIC:
                result['MIC'] = sub.read_sfixed32()
            elif field == JREQ_UPINFO:
                sub.pos -= 1
                while sub.data[sub.pos] & 0x80:
                    sub.pos -= 1
                sub.pos += 1
                result['upinfo'] = sub.decode_radio_metadata()
            elif field == JREQ_REFTIME:
                result['RefTime'] = sub.read_double()
            else:
                sub.skip(wt)
        return result
    
    def decode_propdf(self) -> dict:
        """Decode ProprietaryFrame message."""
        result = {'msgtype': 'propdf'}
        submsg_data = self.read_bytes()
        sub = ProtobufDecoder(submsg_data)
        while sub.pos < len(submsg_data):
            tag = sub.read_varint()
            field = tag >> 3
            wt = tag & 7
            if field == PROPDF_FRMPAYLOAD:
                result['FRMPayload'] = sub.read_bytes().hex()
            elif field == PROPDF_UPINFO:
                sub.pos -= 1
                while sub.data[sub.pos] & 0x80:
                    sub.pos -= 1
                sub.pos += 1
                result['upinfo'] = sub.decode_radio_metadata()
            elif field == PROPDF_REFTIME:
                result['RefTime'] = sub.read_double()
            else:
                sub.skip(wt)
        return result
    
    def decode_dntxed(self) -> dict:
        """Decode TxConfirmation message."""
        result = {'msgtype': 'dntxed'}
        submsg_data = self.read_bytes()
        sub = ProtobufDecoder(submsg_data)
        while sub.pos < len(submsg_data):
            tag = sub.read_varint()
            field = tag >> 3
            wt = tag & 7
            if field == DNTXED_DIID:
                result['diid'] = sub.read_svarint()
                result['seqno'] = result['diid']  # Backward compat
            elif field == DNTXED_DEVEUI:
                result['DevEui'] = f"{sub.read_fixed64():016X}"
            elif field == DNTXED_RCTX:
                result['rctx'] = sub.read_svarint()
            elif field == DNTXED_XTIME:
                result['xtime'] = sub.read_svarint()
            elif field == DNTXED_TXTIME:
                result['txtime'] = sub.read_double()
            elif field == DNTXED_GPSTIME:
                result['gpstime'] = sub.read_svarint()
            else:
                sub.skip(wt)
        return result
    
    def decode_timesync(self) -> dict:
        """Decode TimeSync message."""
        result = {'msgtype': 'timesync'}
        submsg_data = self.read_bytes()
        sub = ProtobufDecoder(submsg_data)
        while sub.pos < len(submsg_data):
            tag = sub.read_varint()
            field = tag >> 3
            wt = tag & 7
            if field == TSYNC_TXTIME:
                result['txtime'] = sub.read_double()
            elif field == TSYNC_GPSTIME:
                result['gpstime'] = sub.read_svarint()
            elif field == TSYNC_XTIME:
                result['xtime'] = sub.read_svarint()
            else:
                sub.skip(wt)
        return result
    
    def decode(self) -> dict:
        """Decode a TcMessage."""
        msgtype = None
        payload_field = None
        
        while self.pos < len(self.data):
            tag = self.read_varint()
            field = tag >> 3
            wt = tag & 7
            
            if field == TCMSG_TYPE:
                msgtype = self.read_varint()
            elif wt == WT_LENDELIM:
                payload_field = field
                break
            else:
                self.skip(wt)
        
        if msgtype is None or payload_field is None:
            raise ValueError("Invalid TcMessage: missing type or payload")
        
        if msgtype == MSG_UPDF:
            return self.decode_updf()
        elif msgtype == MSG_JREQ:
            return self.decode_jreq()
        elif msgtype == MSG_PROPDF:
            return self.decode_propdf()
        elif msgtype == MSG_DNTXED:
            return self.decode_dntxed()
        elif msgtype == MSG_TIMESYNC:
            return self.decode_timesync()
        else:
            raise ValueError(f"Unknown message type: {msgtype}")


class ProtobufEncoder:
    """Encode protobuf messages to station."""
    
    def __init__(self):
        self.data = bytearray()
    
    def write_varint(self, value: int):
        while value >= 0x80:
            self.data.append((value & 0x7F) | 0x80)
            value >>= 7
        self.data.append(value)
    
    def write_svarint(self, value: int):
        """Write signed varint (zigzag encoded)."""
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
    
    def encode_timesync_response(self, gpstime: int, txtime: float, xtime: int) -> bytes:
        """Encode a timesync response message."""
        # Build the TimeSync submessage
        submsg = ProtobufEncoder()
        submsg.write_tag(TSYNC_GPSTIME, WT_VARINT)
        submsg.write_svarint(gpstime)
        # Include original txtime for RTT calculation
        submsg.write_tag(TSYNC_TXTIME, WT_FIXED64)
        submsg.write_double(txtime)
        # Echo back xtime for ts_setTimesyncLns
        if xtime:
            submsg.write_tag(TSYNC_XTIME, WT_VARINT)
            submsg.write_svarint(xtime)
        
        # Build the TcMessage wrapper
        self.write_tag(TCMSG_TYPE, WT_VARINT)
        self.write_varint(MSG_TIMESYNC_RESP)
        self.write_tag(TCMSG_TIMESYNC, WT_LENDELIM)
        self.write_bytes(bytes(submsg.data))
        
        return bytes(self.data)
    
    def encode_dnmsg(self, deveui: int, dclass: int, diid: int, pdu: bytes,
                     rxdelay: int, rx1dr: int, rx1freq: int,
                     rx2dr: int, rx2freq: int, priority: int,
                     xtime: int, rctx: int, muxtime: float) -> bytes:
        """Encode a downlink message."""
        # Build the DownlinkMessage submessage
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
        submsg.write_tag(DNMSG_PRIORITY, WT_VARINT)
        submsg.write_varint(priority)
        submsg.write_tag(DNMSG_XTIME, WT_VARINT)
        submsg.write_svarint(xtime)
        submsg.write_tag(DNMSG_RCTX, WT_VARINT)
        submsg.write_svarint(rctx)
        submsg.write_tag(DNMSG_MUXTIME, WT_FIXED64)
        submsg.write_double(muxtime)
        
        # Build the TcMessage wrapper
        self.write_tag(TCMSG_TYPE, WT_VARINT)
        self.write_varint(MSG_DNMSG)
        self.write_tag(TCMSG_DNMSG, WT_LENDELIM)
        self.write_bytes(bytes(submsg.data))
        
        return bytes(self.data)


# Region-specific LBT channel configurations
# Based on regional parameters from LoRaWAN Regional Parameters spec
LBT_CHANNELS = {
    'AS923': [
        # AS923-1 default channels
        {'freq_hz': 923200000, 'scan_time_us': 5000, 'bandwidth': 125000},
        {'freq_hz': 923400000, 'scan_time_us': 5000, 'bandwidth': 125000},
    ],
    'KR920': [
        # KR920 default channels
        {'freq_hz': 922100000, 'scan_time_us': 5000, 'bandwidth': 125000},
        {'freq_hz': 922300000, 'scan_time_us': 5000, 'bandwidth': 125000},
        {'freq_hz': 922500000, 'scan_time_us': 5000, 'bandwidth': 125000},
    ],
    # Other regions typically don't use LBT
}

# Region-specific LBT RSSI targets (dBm)
LBT_RSSI_TARGETS = {
    'AS923': -80,
    'KR920': -67,
}

# Region-specific duty cycle configurations
DC_CONFIGS = {
    'EU868': {
        'mode': 'band',
        'window_secs': 3600,
        # EU868 band limits in permille (1 permille = 0.1%)
        'band_limits_permille': {
            'K': 1,    # 863-865 MHz: 0.1%
            'L': 10,   # 865-868 MHz: 1%
            'M': 10,   # 868-868.6 MHz: 1%
            'N': 1,    # 868.7-869.2 MHz: 0.1%
            'P': 100,  # 869.4-869.65 MHz: 10%
            'Q': 10,   # 869.7-870 MHz: 1%
        },
    },
    'AS923': {
        'mode': 'channel',
        'window_secs': 3600,
        'channel_limit_permille': 100,  # 10%
    },
    'KR920': {
        'mode': 'channel',
        'window_secs': 3600,
        'channel_limit_permille': 100,  # 10% (no regulatory DC, but common practice)
    },
    'IN865': {
        'mode': 'channel',
        'window_secs': 3600,
        'channel_limit_permille': 100,  # 10%
    },
    # US915/AU915 typically don't have duty cycle restrictions
}


def get_local_ip():
    """Get the local IP address that can reach external networks."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s: %(message)s'
)
logger = logging.getLogger('tc-server')

# Store args globally for access in classes
g_args = None


class TestMuxs(tu.Muxs):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connected_gateways = {}
        self.protobuf_enabled = False
        self.station_capabilities = []
        # Track last uplink timing for timesync xtime responses
        self.last_uplink_xtime = 0
        self.last_uplink_gpstime = 0
        self.last_uplink_time = 0  # local time when uplink received
    
    def get_router_config(self):
        # Select base region config based on region and asym_dr option
        if g_args.asym_dr:
            # RP2 1.0.5 asymmetric datarate configs (with SF5/SF6 support)
            region_configs = {
                'EU868': tu.router_config_EU868_6ch_RP2_sf5sf6,
                'US915': tu.router_config_US902_8ch_RP2_sf5sf6,
                'AU915': tu.router_config_AU915_8ch_RP2_sf5sf6,
                'AS923': tu.router_config_AS923_8ch_RP2_sf5sf6,
                'KR920': tu.router_config_KR920_3ch_RP2_sf5sf6,
                'IN865': tu.router_config_IN865_3ch_RP2_sf5sf6,
            }
            logger.info('Using RP2 1.0.5 asymmetric DR config')
        else:
            # Standard configs (sx1301 compatible, 8-channel where available)
            region_configs = {
                'EU868': tu.router_config_EU863_6ch,
                'US915': tu.router_config_US902_8ch,
                'AU915': tu.router_config_US902_8ch,  # AU915 uses same structure as US915
                'AS923': tu.router_config_EU863_6ch,  # Fallback to EU config structure
                'KR920': tu.router_config_KR920,
                'IN865': tu.router_config_EU863_6ch,  # Fallback to EU config structure
            }
        
        config = dict(region_configs.get(g_args.region, tu.router_config_US902_8ch))
        
        # Apply feature options
        if g_args.pdu_only:
            config['pdu_only'] = True
            logger.info('PDU-only mode ENABLED')
        
        # Protobuf: only enable if station supports it and user requested it
        if g_args.protobuf and 'protobuf' in self.station_capabilities:
            config['protocol_format'] = 'protobuf'
            self.protobuf_enabled = True
            logger.info('Protobuf binary protocol ENABLED')
        elif g_args.protobuf:
            logger.warning('Protobuf requested but station does not advertise protobuf capability')
            self.protobuf_enabled = False
        
        # Duty cycle: explicit on/off sends the field, None means don't send (use station default)
        if g_args.duty_cycle is not None:
            config['duty_cycle_enabled'] = (g_args.duty_cycle == 'on')
            logger.info('Duty cycle: %s (explicit)', 'ENABLED' if g_args.duty_cycle == 'on' else 'DISABLED')
        
        # Duty cycle mode and limits
        if g_args.dc_mode:
            config['dc_mode'] = g_args.dc_mode
            logger.info('DC mode: %s', g_args.dc_mode)
        
        if g_args.dc_limits:
            dc_cfg = DC_CONFIGS.get(g_args.region)
            if dc_cfg:
                config['dc_window_secs'] = dc_cfg.get('window_secs', 3600)
                if dc_cfg.get('mode') == 'band' and 'band_limits_permille' in dc_cfg:
                    config['dc_band_limits_permille'] = dc_cfg['band_limits_permille']
                    logger.info('DC band limits: %s', dc_cfg['band_limits_permille'])
                elif 'channel_limit_permille' in dc_cfg:
                    config['dc_channel_limit_permille'] = dc_cfg['channel_limit_permille']
                    logger.info('DC channel limit: %d permille (%.1f%%)', 
                               dc_cfg['channel_limit_permille'], dc_cfg['channel_limit_permille']/10.0)
            else:
                logger.warning('No DC config defined for region %s', g_args.region)
        
        # LBT: explicit on/off sends the field, None means don't send (use station default)
        if g_args.lbt is not None:
            if g_args.lbt == 'on':
                config['lbt_enabled'] = True
                config['lbt_rssi_target'] = LBT_RSSI_TARGETS.get(g_args.region, -80)
                config['lbt_scan_time_us'] = 5000
                logger.info('LBT: ENABLED (rssi_target=%d, scan_time=5000us)', 
                           config['lbt_rssi_target'])
            else:
                config['lbt_enabled'] = False
                logger.info('LBT: DISABLED (explicit)')
        
        # LBT channels
        if g_args.lbt_channels:
            channels = LBT_CHANNELS.get(g_args.region)
            if channels:
                config['lbt_channels'] = channels
                logger.info('LBT channels: %d channels configured', len(channels))
                for i, ch in enumerate(channels):
                    logger.info('  CH%d: %.3f MHz, scan=%dus, bw=%dkHz',
                               i, ch['freq_hz']/1e6, ch['scan_time_us'], ch['bandwidth']//1000)
            else:
                logger.warning('No LBT channels defined for region %s', g_args.region)
        
        # Single radio mode - disable radio_1 and associated channels
        if g_args.single_radio:
            sx_conf_key = 'sx1301_conf' if 'sx1301_conf' in config else 'sx1302_conf'
            if sx_conf_key in config and len(config[sx_conf_key]) > 0:
                sx_conf = config[sx_conf_key][0]
                
                if g_args.single_radio == 'bad':
                    # "Bad" smtcpico-style config:
                    # - 3 upchannels (only 3 frequencies for station to use)
                    # - radio_1 disabled
                    # - BUT channels 4-7 still enabled and referencing radio_1
                    # This causes calibration failures on smtcpico hardware
                    sx_conf['radio_1'] = {'enable': False, 'freq': 0}
                    # Truncate to 3 upchannels - this is key!
                    if 'upchannels' in config:
                        config['upchannels'] = config['upchannels'][:3]
                    # Disable channels 3-7 but keep them referencing radio_1 (the bad part)
                    # Actually for smtcpico the issue was channels still enabled on disabled radio
                    # Let's leave chan_multiSF_4-7 enabled but referencing radio_1
                    logger.info('Single radio mode (BAD CONFIG): 3 upchannels, radio_1 disabled')
                    logger.info('  WARNING: Channels 4-7 still enabled referencing disabled radio_1!')
                else:
                    # Proper 3-channel config matching tcutils originals
                    # Disable radio_1
                    sx_conf['radio_1'] = {'enable': False, 'freq': 0}
                    # Disable channels 3-7 (keep only 0, 1, 2 on radio_0)
                    for i in range(3, 8):
                        ch_key = f'chan_multiSF_{i}'
                        if ch_key in sx_conf:
                            sx_conf[ch_key] = {'enable': False}
                    # Disable LoRa standard channel (often uses radio_1 or not needed for 3ch)
                    if 'chan_Lora_std' in sx_conf:
                        sx_conf['chan_Lora_std'] = {'enable': False}
                    # Disable FSK channel
                    if 'chan_FSK' in sx_conf:
                        sx_conf['chan_FSK'] = {'enable': False}
                    # Keep only first 3 upchannels
                    if 'upchannels' in config:
                        config['upchannels'] = config['upchannels'][:3]
                    logger.info('Single radio mode: radio_1 disabled, channels 3-7/FSK/LoRa_std disabled, 3 upchannels')
        
        return config
    
    async def handle_version(self, ws, msg):
        logger.info('='*60)
        logger.info('Gateway connected!')
        logger.info('  Station: %s', msg.get('station'))
        logger.info('  Model: %s', msg.get('model'))
        logger.info('  Features: %s', msg.get('features'))
        logger.info('  Protocol: %s', msg.get('protocol'))
        
        # Check for capabilities (protobuf support)
        self.station_capabilities = msg.get('capabilities', [])
        if self.station_capabilities:
            logger.info('  Capabilities: %s', ', '.join(self.station_capabilities))
        
        logger.info('='*60)
        
        # Need to get router_config before calling parent, so capabilities are known
        rconf = self.get_router_config()
        await ws.send(json.dumps(rconf))
        logger.debug('< MUXS: router_config.')
        
        if self.protobuf_enabled:
            logger.info('Binary protocol mode active - expecting protobuf messages')
    
    async def handle_updf(self, ws, msg):
        import time
        
        # Track xtime and gpstime from uplink for timesync responses
        upinfo = msg.get('upinfo', {})
        if upinfo.get('xtime'):
            self.last_uplink_xtime = upinfo['xtime']
            self.last_uplink_gpstime = upinfo.get('gpstime', 0)
            self.last_uplink_time = time.time()
        
        if g_args.pdu_only:
            # PDU-only mode - check what we got
            has_pdu = 'pdu' in msg
            has_parsed = 'MHdr' in msg or 'DevAddr' in msg
            if has_pdu and not has_parsed:
                logger.info('UPLINK (pdu-only): freq=%s DR=%s pdu=%s...', 
                           msg.get('Freq'), msg.get('DR'), msg.get('pdu', '')[:32])
            elif has_pdu and has_parsed:
                logger.warning('UPLINK: Has both pdu and parsed fields (pdu_only may not be working)')
                logger.info('  DevAddr=%08X FCnt=%d', msg.get('DevAddr', 0), msg.get('FCnt', 0))
            else:
                logger.info('UPLINK: DevAddr=%08X FCnt=%d freq=%s DR=%s', 
                           msg.get('DevAddr', 0), msg.get('FCnt', 0),
                           msg.get('Freq'), msg.get('DR'))
        else:
            logger.info('UPLINK: DevAddr=%08X FCnt=%d freq=%s DR=%s', 
                       msg.get('DevAddr', 0), msg.get('FCnt', 0),
                       msg.get('Freq'), msg.get('DR'))
        
        # Auto-downlink mode: send a test downlink for each uplink
        if g_args.auto_downlink:
            await self.send_test_downlink(ws, msg)
    
    def get_downlink_params(self, uplink_dr: int, uplink_freq: int) -> dict:
        """
        Calculate downlink parameters based on region and uplink parameters.
        
        US915/AU915 have asymmetric DRs:
        - Uplink DR 0-3: 125kHz SF10-SF7 (902.3-914.9 MHz)
        - Uplink DR 4: 500kHz SF8 (903.0-914.2 MHz) 
        - Downlink DR 8-13: 500kHz SF12-SF7 (923.3-927.5 MHz)
        
        RX1 DR mapping (with RX1DROffset=0): RX1DR = UpDR + 10 (capped at 13)
        RX1 Freq: Maps uplink channel to downlink channel
        RX2: DR8 (SF12/500kHz) at 923.3 MHz
        """
        region = g_args.region
        
        if region in ('US915', 'AU915'):
            # Asymmetric DR mapping for US915/AU915
            # RX1DROffset = 0: RX1DR = min(UpDR + 10, 13)
            if uplink_dr <= 3:
                rx1dr = min(uplink_dr + 10, 13)  # DR0->DR10, DR1->DR11, DR2->DR12, DR3->DR13
            elif uplink_dr == 4:
                rx1dr = 13  # 500kHz uplink -> DR13 (SF7/500kHz)
            else:
                rx1dr = 10  # Fallback to DR10
            
            # RX1 frequency: map uplink channel (0-63) to downlink channel (0-7)
            # Uplink: 902.3 + 0.2*ch MHz (ch 0-63) or 903.0 + 1.6*ch MHz (ch 64-71)
            # Downlink: 923.3 + 0.6*ch MHz (ch 0-7)
            if uplink_freq >= 902300000 and uplink_freq <= 914900000:
                # 125kHz uplink channels 0-63
                up_ch = round((uplink_freq - 902300000) / 200000)
                dn_ch = up_ch % 8
            elif uplink_freq >= 903000000 and uplink_freq <= 914200000:
                # 500kHz uplink channels 64-71
                up_ch = round((uplink_freq - 903000000) / 1600000)
                dn_ch = up_ch % 8
            else:
                dn_ch = 0
            
            rx1freq = 923300000 + dn_ch * 600000
            
            # RX2 parameters (fixed)
            rx2dr = 8   # SF12/500kHz
            rx2freq = 923300000
            
            return {
                'rx1dr': rx1dr,
                'rx1freq': rx1freq,
                'rx2dr': rx2dr,
                'rx2freq': rx2freq,
            }
        
        elif region == 'EU868':
            # EU868: Symmetric DRs, RX1 same freq as uplink
            return {
                'rx1dr': uplink_dr,
                'rx1freq': uplink_freq,
                'rx2dr': 0,  # SF12/125kHz
                'rx2freq': 869525000,
            }
        
        elif region == 'AS923':
            # AS923: Symmetric DRs, RX1 same freq, RX2 at 923.2 MHz
            return {
                'rx1dr': uplink_dr,
                'rx1freq': uplink_freq,
                'rx2dr': 2,  # SF10/125kHz (default)
                'rx2freq': 923200000,
            }
        
        elif region == 'KR920':
            # KR920: Symmetric DRs, RX1 same freq, RX2 at 921.9 MHz
            return {
                'rx1dr': uplink_dr,
                'rx1freq': uplink_freq,
                'rx2dr': 0,  # SF12/125kHz
                'rx2freq': 921900000,
            }
        
        elif region == 'IN865':
            # IN865: Symmetric DRs, RX1 same freq, RX2 at 866.55 MHz
            return {
                'rx1dr': uplink_dr,
                'rx1freq': uplink_freq,
                'rx2dr': 2,  # SF10/125kHz
                'rx2freq': 866550000,
            }
        
        else:
            # Default fallback
            return {
                'rx1dr': uplink_dr,
                'rx1freq': uplink_freq,
                'rx2dr': 0,
                'rx2freq': 869525000,
            }
    
    async def send_test_downlink(self, ws, uplink_msg):
        """Send a test downlink in response to an uplink."""
        import time
        
        # Extract info from uplink
        upinfo = uplink_msg.get('upinfo', {})
        xtime = upinfo.get('xtime', 0)
        rctx = upinfo.get('rctx', 0)
        uplink_freq = uplink_msg.get('Freq', 868100000)
        uplink_dr = uplink_msg.get('DR', 0)
        
        # Get region-specific downlink parameters
        dn_params = self.get_downlink_params(uplink_dr, uplink_freq)
        
        # For protobuf, need numeric DevEui
        deveui_str = uplink_msg.get('DevEui', '0000000000000000')
        if isinstance(deveui_str, str):
            deveui = int(deveui_str, 16) if deveui_str else 0
        else:
            deveui = deveui_str
        
        # Simple test PDU (unconfirmed data down, FPort=1, payload "test")
        pdu = bytes([0x60, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x74, 0x65, 0x73, 0x74, 0x00, 0x00, 0x00, 0x00])
        
        # Generate a unique diid
        diid = int(time.time() * 1000) % 0x7FFFFFFF
        
        # Get current muxtime
        muxtime = time.time()
        
        logger.debug('Downlink params: upDR=%d upFreq=%d -> rx1DR=%d rx1Freq=%d rx2DR=%d rx2Freq=%d',
                    uplink_dr, uplink_freq, 
                    dn_params['rx1dr'], dn_params['rx1freq'],
                    dn_params['rx2dr'], dn_params['rx2freq'])
        
        if self.protobuf_enabled:
            # Send protobuf downlink
            enc = ProtobufEncoder()
            data = enc.encode_dnmsg(
                deveui=deveui,
                dclass=0,  # Class A
                diid=diid,
                pdu=pdu,
                rxdelay=1,
                rx1dr=dn_params['rx1dr'],
                rx1freq=dn_params['rx1freq'],
                rx2dr=dn_params['rx2dr'],
                rx2freq=dn_params['rx2freq'],
                priority=0,
                xtime=xtime,
                rctx=rctx,
                muxtime=muxtime
            )
            await ws.send(data)
            logger.info('< MUXS: dnmsg (protobuf, %d bytes) diid=%d rx1DR=%d rx1Freq=%d', 
                       len(data), diid, dn_params['rx1dr'], dn_params['rx1freq'])
        else:
            # Send JSON downlink
            dnmsg = {
                'msgtype': 'dnmsg',
                'DevEui': deveui_str if isinstance(deveui_str, str) else f'{deveui:016X}',
                'dC': 0,  # Class A
                'diid': diid,
                'pdu': pdu.hex(),
                'RxDelay': 1,
                'RX1DR': dn_params['rx1dr'],
                'RX1Freq': dn_params['rx1freq'],
                'RX2DR': dn_params['rx2dr'],
                'RX2Freq': dn_params['rx2freq'],
                'priority': 0,
                'xtime': xtime,
                'rctx': rctx,
                'MuxTime': muxtime,
            }
            await ws.send(json.dumps(dnmsg))
            logger.info('< MUXS: dnmsg (JSON) diid=%d rx1DR=%d rx1Freq=%d', 
                       diid, dn_params['rx1dr'], dn_params['rx1freq'])
    
    async def handle_jreq(self, ws, msg):
        logger.info('JOIN REQUEST: DevEUI=%s JoinEUI=%s', 
                   msg.get('DevEui'), msg.get('JoinEui'))
    
    async def handle_propdf(self, ws, msg):
        logger.info('PROPRIETARY: freq=%s DR=%s', msg.get('Freq'), msg.get('DR'))
    
    async def handle_dntxed(self, ws, msg):
        logger.info('DNTXED: seqno=%d', msg.get('seqno', -1))
    
    async def handle_timesync(self, ws, msg):
        logger.debug('TIMESYNC: txtime=%s xtime=%s', msg.get('txtime'), msg.get('xtime'))
        if self.protobuf_enabled:
            # Send binary timesync response
            await self.send_timesync_response_pb(ws, msg.get('txtime', 0), msg.get('xtime', 0))
        else:
            await super().handle_timesync(ws, msg)
    
    async def send_timesync_response_pb(self, ws, txtime: float, xtime: int):
        """Send timesync response in protobuf format.
        
        The xtime field allows the station to directly map xtime to gpstime.
        We calculate xtime by extrapolating from the last uplink's xtime/gpstime,
        using the elapsed time since that uplink was received.
        """
        import time
        from datetime import datetime
        gpstime = int(((datetime.utcnow() - tu.GPS_EPOCH).total_seconds() + tu.UTC_GPS_LEAPS) * 1e6)
        
        # Calculate xtime to return - extrapolate from last uplink
        response_xtime = 0
        if self.last_uplink_xtime and self.last_uplink_time:
            elapsed_us = int((time.time() - self.last_uplink_time) * 1e6)
            response_xtime = self.last_uplink_xtime + elapsed_us
        
        enc = ProtobufEncoder()
        data = enc.encode_timesync_response(gpstime, txtime, response_xtime)
        await ws.send(data)
        logger.debug('< MUXS: timesync response (protobuf, %d bytes, xtime=%d)', len(data), response_xtime)
    
    async def handle_binaryData(self, ws, data: bytes):
        """Handle binary (protobuf) messages from station."""
        if not self.protobuf_enabled:
            logger.warning('Received binary data but protobuf not enabled (%d bytes)', len(data))
            return
        
        try:
            decoder = ProtobufDecoder(data)
            msg = decoder.decode()
            msgtype = msg.get('msgtype')
            
            logger.debug('> MUXS (protobuf): %s', msgtype)
            
            # Route to appropriate handler
            if msgtype == 'updf':
                await self.handle_updf(ws, msg)
            elif msgtype == 'jreq':
                await self.handle_jreq(ws, msg)
            elif msgtype == 'propdf':
                await self.handle_propdf(ws, msg)
            elif msgtype == 'dntxed':
                await self.handle_dntxed(ws, msg)
            elif msgtype == 'timesync':
                await self.handle_timesync(ws, msg)
            else:
                logger.warning('Unknown protobuf message type: %s', msgtype)
                
        except Exception as e:
            logger.error('Failed to decode protobuf message: %s', e, exc_info=True)
            logger.debug('Raw data: %s', data.hex())


async def main(args):
    global g_args
    g_args = args
    
    # Determine the host IP to use for muxs redirect
    host_ip = args.host if args.host else get_local_ip()
    
    logger.info('='*60)
    logger.info('TC Server for Real Gateway Testing')
    logger.info('='*60)
    logger.info('Host IP: %s', host_ip)
    logger.info('Infos port: 6038')
    logger.info('Muxs port: 6039')
    logger.info('Region: %s', args.region)
    logger.info('Features:')
    logger.info('  pdu_only: %s', args.pdu_only)
    logger.info('  protobuf: %s', args.protobuf)
    logger.info('  auto_downlink: %s', args.auto_downlink)
    if args.duty_cycle is not None:
        logger.info('  duty_cycle: %s (explicit)', args.duty_cycle)
    else:
        logger.info('  duty_cycle: (not specified, station default)')
    if args.dc_mode:
        logger.info('  dc_mode: %s', args.dc_mode)
    if args.dc_limits:
        logger.info('  dc_limits: enabled (region-specific)')
    if args.lbt is not None:
        logger.info('  lbt: %s (explicit)', args.lbt)
    else:
        logger.info('  lbt: (not specified, station default)')
    if args.lbt_channels:
        logger.info('  lbt_channels: enabled (region-specific)')
    logger.info('  asym_dr (RP2 1.0.5): %s', args.asym_dr)
    if args.single_radio:
        if args.single_radio == 'bad':
            logger.info('  single_radio: BAD CONFIG (only radio_1 disabled)')
        else:
            logger.info('  single_radio: enabled (proper 3-channel config)')
    logger.info('='*60)
    
    ws_scheme = 'wss' if args.tls else 'ws'
    tls_id = 'muxs-0' if args.tls else None
    
    # Muxs URI that infos will redirect gateways to
    # MUST use the actual IP that the gateway can reach, not localhost!
    muxsuri = f'{ws_scheme}://{host_ip}:6039/router'
    
    infos = tu.Infos(
        muxsuri=muxsuri,
        tlsidentity=('infos-0' if args.tls else None),
    )
    
    muxs = TestMuxs(
        tlsidentity=tls_id,
    )
    
    await infos.start_server()
    await muxs.start_server()
    
    logger.info('')
    logger.info('Server running! Configure your gateway with:')
    logger.info('')
    logger.info('  tc.uri: %s://%s:6038', ws_scheme, host_ip)
    logger.info('')
    logger.info('Press Ctrl+C to stop')
    logger.info('')
    
    # Run forever
    while True:
        await asyncio.sleep(3600)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='TC server for real gateway testing')
    parser.add_argument('--host', help='IP address for muxs redirect (auto-detected if not specified)')
    parser.add_argument('--region', default='US915', 
                       choices=['EU868', 'US915', 'AU915', 'AS923', 'KR920', 'IN865'],
                       help='Region config')
    parser.add_argument('--pdu-only', action='store_true', help='Enable pdu_only mode')
    parser.add_argument('--protobuf', action='store_true', 
                       help='Enable protobuf binary protocol (station must support it)')
    parser.add_argument('--auto-downlink', action='store_true',
                       help='Automatically send a test downlink for each uplink received')
    parser.add_argument('--duty-cycle', choices=['on', 'off'], default=None,
                       help='Explicitly enable/disable duty cycle (sends duty_cycle_enabled field)')
    parser.add_argument('--dc-mode', choices=['legacy', 'band', 'channel'],
                       help='Duty cycle mode (sliding window)')
    parser.add_argument('--dc-limits', action='store_true',
                       help='Send region-specific duty cycle limits')
    parser.add_argument('--lbt', choices=['on', 'off'], default=None,
                       help='Explicitly enable/disable LBT (sends lbt_enabled field)')
    parser.add_argument('--lbt-channels', action='store_true',
                       help='Send region-specific LBT channel configuration')
    parser.add_argument('--asym-dr', action='store_true', help='Use asymmetric uplink/downlink DRs (RP2 1.0.5)')
    parser.add_argument('--single-radio', nargs='?', const='good', default=None,
                       choices=['good', 'bad'],
                       help='Disable radio_1 for 3-channel mode. Use "bad" for incomplete config (only disables radio_1)')
    parser.add_argument('--tls', action='store_true', help='Enable TLS')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        logger.info('Shutting down...')
