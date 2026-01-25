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
import math
from collections import defaultdict
import time

# Import generated protobuf module
import tc_pb2

# ============================================================================
# TDoA Geolocation Support
# ============================================================================

# Speed of light in m/s
SPEED_OF_LIGHT = 299792458.0

class TDoALocator:
    """
    TDoA-based device geolocation using multiple gateway receptions.
    
    When the same uplink is received by 3+ gateways, we can use the time
    differences of arrival to estimate the device location.
    """
    
    def __init__(self):
        # Gateway locations: gateway_id -> (lat, lon, alt)
        self.gateways = {}
        # Pending uplinks: (DevAddr, FCnt, pdu_hash) -> [(gateway_id, gpstime, fts, rssi, snr, freq, recv_time)]
        self.pending = defaultdict(list)
        # Aggregation window in seconds (wait for all gateways to report)
        self.window = 1.0
        
    def add_gateway(self, gateway_id: str, lat: float, lon: float, alt: float = 0.0):
        """Register a gateway location."""
        self.gateways[gateway_id] = (lat, lon, alt)
        logger.info('TDoA: Registered gateway %s at (%.6f, %.6f, %.1fm)', 
                   gateway_id, lat, lon, alt)
        
    def add_reception(self, gateway_id: str, dev_addr: int, fcnt: int, pdu: str,
                     gpstime: int, fts: int, rssi: int, snr: float, freq: int):
        """
        Add a reception of an uplink packet.
        
        Args:
            gateway_id: Identifier for the gateway (e.g., IP address)
            dev_addr: Device address from the uplink
            fcnt: Frame counter from the uplink
            pdu: Raw PDU hex string (for matching duplicates)
            gpstime: GPS time in microseconds (0 if not available)
            fts: Fine timestamp in nanoseconds (-1 if not available)
            rssi: RSSI in dBm
            snr: SNR in dB
            freq: Frequency in Hz
        """
        # Use PDU hash to match exact same packet across gateways
        pdu_hash = hash(pdu) if pdu else 0
        key = (dev_addr, fcnt, pdu_hash)
        now = time.time()
        
        # Clean up old entries
        old_keys = [k for k, rxs in self.pending.items() 
                   if rxs and now - rxs[0][6] > self.window * 3]
        for k in old_keys:
            del self.pending[k]
        
        # Check if we already have this gateway for this packet
        for rx in self.pending[key]:
            if rx[0] == gateway_id:
                return  # Duplicate from same gateway
        
        # Add reception
        self.pending[key].append((gateway_id, gpstime, fts, rssi, snr, freq, now))
        
        # Check if we can do TDoA
        receptions = self.pending[key]
        if len(receptions) >= 3:
            first_time = receptions[0][6]
            if now - first_time >= self.window:
                self._do_tdoa(dev_addr, fcnt, receptions)
                del self.pending[key]
    
    def _do_tdoa(self, dev_addr: int, fcnt: int, receptions: list):
        """Perform TDoA calculation with 3+ gateway receptions."""
        # Filter to gateways we have locations for
        valid = [(gw_id, gps, fts, rssi, snr, freq) 
                for gw_id, gps, fts, rssi, snr, freq, _ in receptions
                if gw_id in self.gateways]
        
        if len(valid) < 3:
            logger.info('TDoA: DevAddr=%08X FCnt=%d - only %d gateways with known locations',
                       dev_addr, fcnt, len(valid))
            return
        
        # Sort by arrival time (prefer fts, fall back to gpstime)
        def arrival_key(rx):
            gw_id, gps, fts, rssi, snr, freq = rx
            if fts >= 0 and gps > 0:
                return gps * 1000 + fts  # nanoseconds
            elif gps > 0:
                return gps * 1000
            return float('inf')
        
        valid.sort(key=arrival_key)
        
        # Reference is first arrival
        ref = valid[0]
        ref_gw, ref_gps, ref_fts, ref_rssi, ref_snr, ref_freq = ref
        ref_lat, ref_lon, ref_alt = self.gateways[ref_gw]
        
        logger.info('TDoA: DevAddr=%08X FCnt=%d - %d gateways', dev_addr, fcnt, len(valid))
        
        # Calculate time differences
        tdoas = []
        for i, (gw_id, gps, fts, rssi, snr, freq) in enumerate(valid):
            lat, lon, alt = self.gateways[gw_id]
            
            # Calculate TDoA relative to reference
            if i == 0:
                tdoa_ns = 0
            else:
                ref_time = (ref_gps * 1000 + ref_fts) if ref_fts >= 0 else ref_gps * 1000
                this_time = (gps * 1000 + fts) if fts >= 0 else gps * 1000
                tdoa_ns = this_time - ref_time
            
            dist_diff_m = (tdoa_ns * 1e-9) * SPEED_OF_LIGHT
            tdoas.append((gw_id, tdoa_ns, dist_diff_m, rssi, snr))
            
            fts_str = f'{fts}ns' if fts >= 0 else 'N/A'
            logger.info('  GW %s: RSSI=%d SNR=%.1f TDoA=%+dns (%.1fm) fts=%s',
                       gw_id, rssi, snr, tdoa_ns, dist_diff_m, fts_str)
        
        # Simple RSSI-weighted centroid estimate
        # (A real solver would use hyperbolic multilateration)
        total_w = 0.0
        est_lat = 0.0
        est_lon = 0.0
        
        for gw_id, tdoa_ns, dist_diff, rssi, snr in tdoas:
            lat, lon, alt = self.gateways[gw_id]
            # Weight: stronger signal = likely closer
            w = 10 ** ((rssi + 120) / 20.0)  # Normalize around -120 dBm
            est_lat += lat * w
            est_lon += lon * w
            total_w += w
        
        if total_w > 0:
            est_lat /= total_w
            est_lon /= total_w
            logger.info('  => Estimated location: (%.6f, %.6f)', est_lat, est_lon)
            
            # Calculate distances from estimate to each gateway
            for gw_id, _, _, rssi, _ in tdoas:
                gw_lat, gw_lon, _ = self.gateways[gw_id]
                dist_km = self._haversine(est_lat, est_lon, gw_lat, gw_lon)
                logger.info('     Distance to %s: %.2f km', gw_id, dist_km)
    
    def _haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great-circle distance between two points in km."""
        R = 6371.0  # Earth radius in km
        
        lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
        lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
        
        dlat = lat2_r - lat1_r
        dlon = lon2_r - lon1_r
        
        a = math.sin(dlat/2)**2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c

# Global TDoA locator instance
g_tdoa_locator = TDoALocator()

# ============================================================================
# Protobuf Helpers using generated tc_pb2 module
# ============================================================================

def decode_protobuf_message(data: bytes) -> dict:
    """
    Decode a protobuf TcMessage from the station.
    
    Returns a dict with 'msgtype' and message-specific fields.
    Uses the generated tc_pb2 module for correct wire format handling.
    """
    msg = tc_pb2.TcMessage()
    msg.ParseFromString(data)
    
    msgtype = msg.msg_type
    result = {}
    
    if msgtype == tc_pb2.MSG_UPDF:
        updf = msg.updf
        result = {'msgtype': 'updf'}
        
        # Check if this is pdu_only mode by looking at whether parsed fields have real values
        # In pdu_only mode: only pdu is set, all parsed fields are default (0)
        # In normal mode: parsed fields have values, pdu may or may not be present
        has_parsed_values = (updf.mhdr != 0 or updf.dev_addr != 0 or 
                            updf.fcnt != 0 or updf.mic != 0)
        
        # Include pdu if present
        if updf.pdu:
            result['pdu'] = updf.pdu.hex()
        
        # Only include parsed fields if they have actual values (not pdu_only mode)
        if has_parsed_values:
            result['MHdr'] = updf.mhdr
            result['DevAddr'] = updf.dev_addr
            result['FCtrl'] = updf.fctrl
            result['FCnt'] = updf.fcnt
            result['FPort'] = updf.fport
            result['MIC'] = updf.mic
            if updf.fopts:
                result['FOpts'] = updf.fopts.hex()
            if updf.frm_payload:
                result['FRMPayload'] = updf.frm_payload.hex()
        
        if updf.ref_time:
            result['RefTime'] = updf.ref_time
        if updf.HasField('upinfo'):
            result['upinfo'] = _decode_radio_metadata(updf.upinfo)
    
    elif msgtype == tc_pb2.MSG_JREQ:
        jreq = msg.jreq
        result = {
            'msgtype': 'jreq',
            'MHdr': jreq.mhdr,
            'JoinEui': f"{jreq.join_eui:016X}",
            'DevEui': f"{jreq.dev_eui:016X}",
            'DevNonce': jreq.dev_nonce,
            'MIC': jreq.mic,
            'RefTime': jreq.ref_time,
        }
        if jreq.HasField('upinfo'):
            result['upinfo'] = _decode_radio_metadata(jreq.upinfo)
    
    elif msgtype == tc_pb2.MSG_PROPDF:
        propdf = msg.propdf
        result = {
            'msgtype': 'propdf',
            'FRMPayload': propdf.frm_payload.hex() if propdf.frm_payload else '',
            'RefTime': propdf.ref_time,
        }
        if propdf.HasField('upinfo'):
            result['upinfo'] = _decode_radio_metadata(propdf.upinfo)
    
    elif msgtype == tc_pb2.MSG_DNTXED:
        dntxed = msg.dntxed
        result = {
            'msgtype': 'dntxed',
            'diid': dntxed.diid,
            'seqno': dntxed.diid,  # backward compat
            'DevEui': f"{dntxed.dev_eui:016X}",
            'rctx': dntxed.rctx,
            'xtime': dntxed.xtime,
            'txtime': dntxed.txtime,
            'gpstime': dntxed.gpstime,
        }
    
    elif msgtype == tc_pb2.MSG_TIMESYNC:
        ts = msg.timesync
        result = {
            'msgtype': 'timesync',
            'txtime': ts.txtime,
            'gpstime': ts.gpstime,
            'xtime': ts.xtime,
        }
    
    else:
        raise ValueError(f"Unknown message type: {msgtype}")
    
    return result


def _decode_radio_metadata(rm) -> dict:
    """Convert RadioMetadata protobuf to dict."""
    return {
        'DR': rm.dr,
        'Freq': rm.freq,
        'rctx': rm.rctx,
        'xtime': rm.xtime,
        'gpstime': rm.gpstime,
        'rssi': rm.rssi,
        'snr': rm.snr / 10.0,  # Convert centibels to dB
        'fts': rm.fts,
        'rxtime': rm.rxtime,
    }


def encode_timesync_response(gpstime: int, txtime: float, xtime: int = 0) -> bytes:
    """
    Encode a timesync response message.
    
    Args:
        gpstime: GPS time in microseconds since GPS epoch
        txtime: Original txtime from station (for RTT calculation)
        xtime: Optional xtime for LNS-initiated GPS transfer
    
    Returns:
        Serialized protobuf bytes
    """
    msg = tc_pb2.TcMessage()
    msg.msg_type = tc_pb2.MSG_TIMESYNC_RESP
    msg.timesync.gpstime = gpstime
    msg.timesync.txtime = txtime
    if xtime:
        msg.timesync.xtime = xtime
    return msg.SerializeToString()


def encode_downlink_message(deveui: int, dclass: int, diid: int, pdu: bytes,
                            rxdelay: int, rx1dr: int, rx1freq: int,
                            rx2dr: int, rx2freq: int, priority: int,
                            xtime: int, rctx: int, muxtime: float,
                            gpstime: int = 0) -> bytes:
    """
    Encode a downlink message.
    
    Args:
        deveui: Device EUI (64-bit)
        dclass: Device class (0=A, 1=B, 2=C)
        diid: Downlink ID for correlation
        pdu: PHYPayload bytes to transmit
        rxdelay: RX window delay in seconds
        rx1dr, rx1freq: RX1 data rate and frequency
        rx2dr, rx2freq: RX2 data rate and frequency
        priority: Transmission priority
        xtime: Timing reference from uplink
        rctx: Radio context from uplink
        muxtime: MuxTime for RTT monitoring
        gpstime: GPS time for Class B/C (optional)
    
    Returns:
        Serialized protobuf bytes
    """
    msg = tc_pb2.TcMessage()
    msg.msg_type = tc_pb2.MSG_DNMSG
    
    dnmsg = msg.dnmsg
    dnmsg.dev_eui = deveui
    dnmsg.dc = dclass
    dnmsg.diid = diid
    dnmsg.pdu = pdu
    dnmsg.rx_delay = rxdelay
    dnmsg.rx1_dr = rx1dr
    dnmsg.rx1_freq = rx1freq
    dnmsg.rx2_dr = rx2dr
    dnmsg.rx2_freq = rx2freq
    dnmsg.priority = priority
    dnmsg.xtime = xtime
    dnmsg.rctx = rctx
    dnmsg.mux_time = muxtime
    if gpstime:
        dnmsg.gpstime = gpstime
    
    return msg.SerializeToString()


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
        self.station_features = []
        # Track last uplink timing for timesync xtime responses
        self.last_uplink_xtime = 0
        self.last_uplink_gpstime = 0
        self.last_uplink_time = 0  # local time when uplink received
        # GPS toggle state
        self.gps_enabled = True
        self.gps_toggle_task = None
        self.active_ws = None
    
    async def handle_ws(self, ws):
        """Override base class to NOT send router_config before version message.
        
        We need to wait for the version message to know station capabilities
        (protobuf support) before sending router_config with protocol_format.
        """
        path = tu.get_ws_path(ws)
        logger.debug('. MUXS connect: %s' % (path,))
        if path != '/router':
            await ws.close(4000)
            return
        self.ws = ws
        # Reset per-connection state for new station
        self.station_version = ''
        self.station_features = []
        self.protobuf_enabled = False
        # Don't send router_config here - wait for handle_version
        await self.handle_connection(ws)
    
    def get_router_config(self):
        # Detect chipset from station version string (e.g., "2.0.6(mlinux/sx1303)")
        station_str = getattr(self, 'station_version', '') or ''
        is_sx1303 = 'sx1303' in station_str.lower()
        is_sx1302 = 'sx1302' in station_str.lower() and not is_sx1303
        
        # Select base region config based on region, asym_dr, and chipset
        if g_args.asym_dr:
            if is_sx1303:
                # SX1303 configs with sx1302_conf and hwspec sx1303/1
                region_configs = {
                    'EU868': tu.router_config_EU868_6ch_RP2_sx1303,
                    'US915': tu.router_config_US902_8ch_RP2_sx1303,
                    'AU915': tu.router_config_AU915_8ch_RP2_sx1303,
                    'AS923': tu.router_config_AS923_8ch_RP2_sx1303,
                    'KR920': tu.router_config_KR920_3ch_RP2_sx1303,
                    'IN865': tu.router_config_IN865_3ch_RP2_sx1303,
                }
                logger.info('Using RP2 1.0.5 config for SX1303')
            elif is_sx1302:
                # SX1302 configs with sx1302_conf and hwspec sx1302/1
                region_configs = {
                    'EU868': tu.router_config_EU868_6ch_RP2_sx1302,
                    'US915': tu.router_config_US902_8ch_RP2_sx1302,
                    'AU915': tu.router_config_AU915_8ch_RP2_sx1302,
                    'AS923': tu.router_config_AS923_8ch_RP2_sx1302,
                    'KR920': tu.router_config_KR920_3ch_RP2_sx1302,
                    'IN865': tu.router_config_IN865_3ch_RP2_sx1302,
                }
                logger.info('Using RP2 1.0.5 config for SX1302')
            else:
                # Chipset not detected - default to SX1302 config since asym-dr implies RP2 1.0.5
                # which is typically used with SX1302/SX1303 concentrators
                region_configs = {
                    'EU868': tu.router_config_EU868_6ch_RP2_sx1302,
                    'US915': tu.router_config_US902_8ch_RP2_sx1302,
                    'AU915': tu.router_config_AU915_8ch_RP2_sx1302,
                    'AS923': tu.router_config_AS923_8ch_RP2_sx1302,
                    'KR920': tu.router_config_KR920_3ch_RP2_sx1302,
                    'IN865': tu.router_config_IN865_3ch_RP2_sx1302,
                }
                logger.info('Using RP2 1.0.5 config (chipset not detected, defaulting to SX1302)')
                logger.debug('Station version string: %r', station_str)
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
        
        import copy
        config = copy.deepcopy(region_configs.get(g_args.region, tu.router_config_US902_8ch))
        
        # Apply feature options
        if g_args.pdu_only:
            config['pdu_only'] = True
            logger.info('PDU-only mode ENABLED')
        
        # Protobuf: only enable if user requested it AND station supports it
        if g_args.protobuf and 'protobuf' in self.station_features:
            config['protocol_format'] = 'protobuf'
            self.protobuf_enabled = True
            logger.info('Protobuf binary protocol ENABLED')
        else:
            # Explicitly set JSON to override any previous protobuf setting
            config['protocol_format'] = 'json'
            self.protobuf_enabled = False
            if g_args.protobuf:
                logger.warning('Protobuf requested but station does not support it - using JSON')
        
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
        # Get client IP from websocket (used as gateway ID for TDoA)
        try:
            peername = ws.remote_address
            self.gateway_id = peername[0] if peername else "unknown"
            client_ip = f"{peername[0]}:{peername[1]}" if peername else "unknown"
        except:
            self.gateway_id = "unknown"
            client_ip = "unknown"
        
        logger.info('='*60)
        logger.info('Gateway connected from %s', client_ip)
        logger.info('  Station: %s', msg.get('station'))
        logger.info('  Model: %s', msg.get('model'))
        logger.info('  Features: %s', msg.get('features'))
        logger.info('  Protocol: %s', msg.get('protocol'))
        
        # Store station version string for chipset detection (e.g., "2.0.6(mlinux/sx1303)")
        self.station_version = msg.get('station', '')
        
        # Parse features string for protobuf support
        features_str = msg.get('features', '')
        self.station_features = features_str.split() if features_str else []
        if 'protobuf' in self.station_features:
            logger.info('  Protobuf: supported')
        
        logger.info('='*60)
        
        # Store active websocket for GPS toggle
        self.active_ws = ws
        
        # Reset uplink tracking for new session
        self.last_uplink_xtime = 0
        self.last_uplink_gpstime = 0
        self.last_uplink_time = 0
        
        # Need to get router_config before calling parent, so capabilities are known
        rconf = self.get_router_config()
        await ws.send(json.dumps(rconf))
        logger.debug('< MUXS: router_config.')
        
        if self.protobuf_enabled:
            logger.info('Binary protocol mode active - expecting protobuf messages')
        
        # Start GPS toggle task if configured
        if g_args.gps_toggle > 0 and self.gps_toggle_task is None:
            self.gps_toggle_task = asyncio.create_task(self.gps_toggle_loop(ws))
    
    async def gps_toggle_loop(self, ws):
        """Periodically toggle GPS enable/disable via router_config."""
        interval = g_args.gps_toggle
        logger.info('GPS toggle task started (interval=%ds)', interval)
        try:
            while True:
                await asyncio.sleep(interval)
                self.gps_enabled = not self.gps_enabled
                logger.info('='*40)
                logger.info('GPS TOGGLE: %s', 'ENABLED' if self.gps_enabled else 'DISABLED')
                logger.info('='*40)
                # Send new router_config with updated gps_enable
                rconf = self.get_router_config()
                rconf['gps_enable'] = self.gps_enabled
                await ws.send(json.dumps(rconf))
                logger.info('< MUXS: router_config (gps_enable=%s)', self.gps_enabled)
        except asyncio.CancelledError:
            logger.info('GPS toggle task cancelled')
        except Exception as e:
            logger.error('GPS toggle task error: %s', e)
    
    def parse_pdu(self, pdu_hex: str) -> dict:
        """Parse a LoRaWAN PDU from hex string and extract key fields."""
        try:
            pdu = bytes.fromhex(pdu_hex)
            if len(pdu) < 12:
                return {'error': 'PDU too short'}
            
            mhdr = pdu[0]
            mtype = (mhdr >> 5) & 0x07
            
            mtype_names = {
                0: 'JoinReq', 1: 'JoinAcc', 2: 'UnconfUp', 3: 'UnconfDn',
                4: 'ConfUp', 5: 'ConfDn', 6: 'RejoinReq', 7: 'Proprietary'
            }
            
            result = {
                'MHdr': mhdr,
                'MType': mtype_names.get(mtype, f'Unknown({mtype})'),
            }
            
            # Data frames (MType 2-5)
            if mtype in (2, 3, 4, 5):
                devaddr = int.from_bytes(pdu[1:5], 'little')
                fctrl = pdu[5]
                fcnt = int.from_bytes(pdu[6:8], 'little')
                fopts_len = fctrl & 0x0F
                
                result['DevAddr'] = devaddr
                result['FCtrl'] = fctrl
                result['FCnt'] = fcnt
                result['FOptsLen'] = fopts_len
                result['ADR'] = bool(fctrl & 0x80)
                result['ACK'] = bool(fctrl & 0x20)
                
                # FPort if present
                fhdr_len = 8 + fopts_len
                if len(pdu) > fhdr_len + 4:  # +4 for MIC
                    result['FPort'] = pdu[fhdr_len]
                    payload_len = len(pdu) - fhdr_len - 1 - 4  # -1 FPort, -4 MIC
                    result['PayloadLen'] = payload_len
                
                # MIC (last 4 bytes)
                result['MIC'] = int.from_bytes(pdu[-4:], 'little')
            
            # Join request (MType 0)
            elif mtype == 0 and len(pdu) >= 23:
                result['JoinEUI'] = pdu[1:9].hex()
                result['DevEUI'] = pdu[9:17].hex()
                result['DevNonce'] = int.from_bytes(pdu[17:19], 'little')
            
            return result
        except Exception as e:
            return {'error': str(e)}
    
    async def handle_updf(self, ws, msg):
        import time
        
        # Track xtime and gpstime from uplink for timesync responses
        upinfo = msg.get('upinfo', {})
        xtime = upinfo.get('xtime', 0)
        if xtime:
            self.last_uplink_xtime = xtime
            self.last_uplink_gpstime = upinfo.get('gpstime', 0)
            now = time.time()
            
            # Send LNS-initiated GPS time transfer, but throttle to once per 10 seconds
            # to avoid flooding the station with time sync messages
            if now - self.last_uplink_time >= 10.0:
                await self.send_timesync_transfer(ws, xtime)
            self.last_uplink_time = now
        
        # Extract radio info
        freq = upinfo.get('Freq', msg.get('Freq', 0))
        dr = upinfo.get('DR', msg.get('DR', 0))
        rssi = upinfo.get('rssi', msg.get('rssi', 0))
        snr = upinfo.get('snr', msg.get('snr', 0))
        fts = upinfo.get('fts', -1)
        fts_status = 'OK' if fts >= 0 else 'NONE'
        
        # Format frequency nicely
        freq_mhz = freq / 1e6 if freq > 1e6 else freq
        
        # Auto-detect message format and log appropriately
        has_pdu = 'pdu' in msg and msg['pdu']
        has_parsed = 'DevAddr' in msg
        pdu_hex = msg.get('pdu', '')
        
        # Determine DevAddr and FCnt - either from parsed fields or by parsing PDU
        dev_addr = msg.get('DevAddr', 0)
        fcnt = msg.get('FCnt', 0)
        fport = msg.get('FPort', None)
        mtype = None
        
        if has_pdu and not has_parsed:
            # PDU-only: parse the PDU to extract fields
            parsed = self.parse_pdu(pdu_hex)
            if 'error' not in parsed:
                dev_addr = parsed.get('DevAddr', 0)
                fcnt = parsed.get('FCnt', 0)
                fport = parsed.get('FPort')
                mtype = parsed.get('MType')
        
        # Format the log message
        if mtype == 'JoinReq':
            parsed = self.parse_pdu(pdu_hex) if has_pdu else {}
            logger.info('JREQ: DevEUI=%s JoinEUI=%s freq=%.3f MHz DR=%d RSSI=%d SNR=%.1f fts=%s',
                       parsed.get('DevEUI', '?'), parsed.get('JoinEUI', '?'),
                       freq_mhz, dr, rssi, snr, fts_status)
        else:
            # Data frame (uplink)
            fport_str = str(fport) if fport is not None else '-'
            mode = 'pdu' if has_pdu and not has_parsed else 'parsed' if has_parsed else '?'
            logger.info('UPLINK [%s]: DevAddr=%08X FCnt=%d FPort=%s freq=%.3f MHz DR=%d RSSI=%d SNR=%.1f fts=%s',
                       mode, dev_addr, fcnt, fport_str, freq_mhz, dr, rssi, snr, fts_status)
        
        # TDoA geolocation: collect receptions from multiple gateways
        if g_args.tdoa:
            dev_addr = msg.get('DevAddr', 0)
            fcnt = msg.get('FCnt', 0)
            pdu = msg.get('pdu', '')
            gpstime = upinfo.get('gpstime', 0)
            gateway_id = getattr(self, 'gateway_id', 'unknown')
            
            g_tdoa_locator.add_reception(
                gateway_id=gateway_id,
                dev_addr=dev_addr,
                fcnt=fcnt,
                pdu=pdu,
                gpstime=gpstime,
                fts=fts,
                rssi=rssi,
                snr=snr,
                freq=freq
            )
        
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
            data = encode_downlink_message(
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
        
        Per the TC protocol spec (https://doc.sm.tc/station/tcproto.html):
        
        Station-initiated timesync (this function):
          Station sends: {"msgtype":"timesync", "txtime":INT64}
          LNS responds:  {"msgtype":"timesync", "txtime":INT64, "gpstime":INT64}
          
        The LNS echoes txtime and adds gpstime. This is for round-trip calculation.
        Do NOT include xtime here - that's for a separate LNS-initiated transfer.
        """
        from datetime import datetime, timezone
        gpstime = int(((datetime.now(timezone.utc).replace(tzinfo=None) - tu.GPS_EPOCH).total_seconds() + tu.UTC_GPS_LEAPS) * 1e6)
        
        # Per protocol: only txtime + gpstime in response to station-initiated timesync
        data = encode_timesync_response(gpstime, txtime, 0)
        await ws.send(data)
        logger.debug('< MUXS: timesync response (protobuf, gpstime=%d)', gpstime)
    
    async def send_timesync_transfer(self, ws, xtime: int):
        """Send LNS-initiated GPS time transfer.
        
        Per the TC protocol spec:
          LNS sends periodically: {"msgtype":"timesync", "xtime":INT64, "gpstime":INT64}
          
        The xtime comes from recent uplinks. This provides direct xtime->gpstime mapping.
        """
        from datetime import datetime, timezone
        gpstime = int(((datetime.now(timezone.utc).replace(tzinfo=None) - tu.GPS_EPOCH).total_seconds() + tu.UTC_GPS_LEAPS) * 1e6)
        
        # Per protocol: xtime + gpstime for LNS-initiated transfer (no txtime)
        data = encode_timesync_response(gpstime, 0, xtime)
        await ws.send(data)
        logger.debug('< MUXS: timesync transfer (protobuf, xtime=0x%X, gpstime=%d)', xtime, gpstime)
    
    async def handle_binaryData(self, ws, data: bytes):
        """Handle binary (protobuf) messages from station."""
        if not self.protobuf_enabled:
            # Station sent binary but we requested JSON - could be buffered from before reconnect
            # Decode it anyway to avoid losing messages
            logger.debug('Received binary data in JSON mode (%d bytes) - decoding anyway', len(data))
        
        try:
            msg = decode_protobuf_message(data)
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
    
    # Load gateway locations for TDoA
    if args.gateway_locations:
        try:
            with open(args.gateway_locations, 'r') as f:
                locations = json.load(f)
            for gw_id, loc in locations.items():
                g_tdoa_locator.add_gateway(gw_id, loc['lat'], loc['lon'], loc.get('alt', 0.0))
        except Exception as e:
            logger.error('Failed to load gateway locations: %s', e)
            if args.tdoa:
                logger.error('TDoA requires valid gateway locations file')
                sys.exit(1)
    elif args.tdoa:
        logger.warning('TDoA enabled but no --gateway-locations file specified')
        logger.warning('Create a JSON file like: {"10.10.200.140": {"lat": 37.7749, "lon": -122.4194}, ...}')
    
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
    if args.tdoa:
        logger.info('  tdoa: ENABLED (%d gateways configured)', len(g_tdoa_locator.gateways))
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
    parser.add_argument('--gps-toggle', type=int, metavar='SECS', default=0,
                       help='Toggle GPS enable/disable every N seconds (0=disabled)')
    parser.add_argument('--tdoa', action='store_true',
                       help='Enable TDoA geolocation (requires --gateway-locations)')
    parser.add_argument('--gateway-locations', type=str, metavar='FILE',
                       help='JSON file with gateway locations: {"ip_address": {"lat": N, "lon": E, "alt": M}, ...}')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        logger.info('Shutting down...')
