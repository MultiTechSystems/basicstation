// Auto generated by genkwcrcs - DO NOT CHANGE!
#define UJ_UPDATE_CRC(crc,c) ((((crc)>>(32-8))*65537) ^ ((crc)*257) ^ ((c)&0x7F))
#define UJ_FINISH_CRC(crc)   ((crc) ? (crc) : 1)
#define J_addcrc               ((ujcrc_t)(0x1991DA5B))
#define J_antenna_gain         ((ujcrc_t)(0xB5F37EF4))
#define J_antenna_type         ((ujcrc_t)(0x7D4274ED))
#define J_api                  ((ujcrc_t)(0x00617278))
#define J_arguments            ((ujcrc_t)(0x5ACAD020))
#define J_AS923                ((ujcrc_t)(0xD653976B))
#define J_AS923_1              ((ujcrc_t)(0x66169288))
#define J_AS923_2              ((ujcrc_t)(0x6616928B))
#define J_AS923_3              ((ujcrc_t)(0x6616928A))
#define J_AS923_4              ((ujcrc_t)(0x6616928D))
#define J_AS923JP              ((ujcrc_t)(0x6616F98E))
#define J_asap                 ((ujcrc_t)(0x61D4E603))
#define J_AU915                ((ujcrc_t)(0xD8599E68))
#define J_bcning               ((ujcrc_t)(0x1EE5E245))
#define J_beaconing            ((ujcrc_t)(0x58428CA7))
#define J_cca                  ((ujcrc_t)(0x00636361))
#define J_CN470                ((ujcrc_t)(0xD75F977D))
#define J_CN779                ((ujcrc_t)(0xD75E9777))
#define J_command              ((ujcrc_t)(0xA46E40CA))
#define J_config               ((ujcrc_t)(0xF7A3E35F))
#define J_dC                   ((ujcrc_t)(0x00006427))
#define J_DevEui               ((ujcrc_t)(0x0F01F1A4))
#define J_DevEUI               ((ujcrc_t)(0x0F01D1A4))
#define J_device               ((ujcrc_t)(0xF0921352))
#define J_device_mode          ((ujcrc_t)(0x2DB3FCE7))
#define J_diid                 ((ujcrc_t)(0x64D5D500))
#define J_disconnect           ((ujcrc_t)(0x508A92A9))
#define J_dnmode               ((ujcrc_t)(0xFB97E55A))
#define J_dnframe              ((ujcrc_t)(0xF7095424))
#define J_dnmsg                ((ujcrc_t)(0x37C3E917))
#define J_dnsched              ((ujcrc_t)(0xFDEA5B35))
#define J_dntxed               ((ujcrc_t)(0x12FBF954))
#define J_domain               ((ujcrc_t)(0x0590E65C))
#define J_DR                   ((ujcrc_t)(0x00004416))
#define J_DRs                  ((ujcrc_t)(0x00445A65))
#define J_duty_cycle           ((ujcrc_t)(0x18855C82))
#define J_enable               ((ujcrc_t)(0x0697E35F))
#define J_error                ((ujcrc_t)(0x47A7EB1D))
#define J_EU433                ((ujcrc_t)(0xE0569061))
#define J_EU863                ((ujcrc_t)(0xE0529B68))
#define J_EU868                ((ujcrc_t)(0xE0529B63))
#define J_euiprefix            ((ujcrc_t)(0x9D5E0C96))
#define J_shell                ((ujcrc_t)(0x767A1E0A))
#define J_cmd                  ((ujcrc_t)(0x0063716A))
#define J_freq                 ((ujcrc_t)(0x66E0EB00))
#define J_Freq                 ((ujcrc_t)(0x46C0CB20))
#define J_freqs                ((ujcrc_t)(0x47ADEB15))
#define J_freq_range           ((ujcrc_t)(0x38A2732C))
#define J_gateway_conf         ((ujcrc_t)(0x186A380C))
#define J_getxtime             ((ujcrc_t)(0x286076CA))
#define J_gps                  ((ujcrc_t)(0x00677E64))
#define J_gps_enable           ((ujcrc_t)(0x068AEBB6))
#define J_gpstime              ((ujcrc_t)(0xCC004EB5))
#define J_hello                ((ujcrc_t)(0x46DBE30A))
#define J_hwspec               ((ujcrc_t)(0xE3C2202A))
#define J_if                   ((ujcrc_t)(0x0000690F))
#define J_IL915                ((ujcrc_t)(0xE1689771))
#define J_infos_uri            ((ujcrc_t)(0xE3215635))
#define J_JoinEui              ((ujcrc_t)(0x5B616676))
#define J_JoinEUI              ((ujcrc_t)(0x5B618676))
#define J_KR920                ((ujcrc_t)(0xFB789669))
#define J_layout               ((ujcrc_t)(0x11950A24))
#define J_log_file             ((ujcrc_t)(0x7886C6B6))
#define J_log_level            ((ujcrc_t)(0x7B397448))
#define J_log_rotate           ((ujcrc_t)(0x240F1106))
#define J_log_size             ((ujcrc_t)(0x6453ABB5))
#define J_max_eirp             ((ujcrc_t)(0x60B4BA83))
#define J_mix_gain             ((ujcrc_t)(0xC7F3BD05))
#define J_msgid                ((ujcrc_t)(0x66901419))
#define J_msgtype              ((ujcrc_t)(0xBD07399C))
#define J_muxs                 ((ujcrc_t)(0x6DF2E513))
#define J_MuxTime              ((ujcrc_t)(0x8F6686E3))
#define J_NetID                ((ujcrc_t)(0x16D1EE1C))
#define J_nocca                ((ujcrc_t)(0x4CC0D20E))
#define J_nodc                 ((ujcrc_t)(0x6EDDD406))
#define J_nodwell              ((ujcrc_t)(0xB6A53879))
#define J_no_gps_capture       ((ujcrc_t)(0xDEA1F99B))
#define J_ontime               ((ujcrc_t)(0xF9E41F34))
#define J_pa_gain              ((ujcrc_t)(0xDEE8634E))
#define J_pdu                  ((ujcrc_t)(0x00708461))
#define J_preamble             ((ujcrc_t)(0x05167D25))
#define J_priority             ((ujcrc_t)(0xF00C8E15))
#define J_pps                  ((ujcrc_t)(0x00707073))
#define J_radio                ((ujcrc_t)(0x6A861A03))
#define J_radio_conf           ((ujcrc_t)(0xBA23370B))
#define J_radio_init           ((ujcrc_t)(0xA4224015))
#define J_rctx                 ((ujcrc_t)(0x72F5E81D))
#define J_reboot               ((ujcrc_t)(0xF6CE1F1D))
#define J_reconnect            ((ujcrc_t)(0xD965FF91))
#define J_region               ((ujcrc_t)(0xF5F71604))
#define J_regionid             ((ujcrc_t)(0xE6FFB211))
#define J_restart              ((ujcrc_t)(0xFFFF1F62))
#define J_rmtsh                ((ujcrc_t)(0x77731403))
#define J_router               ((ujcrc_t)(0xFEE91D0C))
#define J_routerid             ((ujcrc_t)(0xE1C9C417))
#define J_router_config        ((ujcrc_t)(0xE5E7E58E))
#define J_runcmd               ((ujcrc_t)(0x1EF2012F))
#define J_RX1DR                ((ujcrc_t)(0x0114167F))
#define J_RX1Freq              ((ujcrc_t)(0x3E8FAA5D))
#define J_RX2DR                ((ujcrc_t)(0x0111107C))
#define J_RX2Freq              ((ujcrc_t)(0x3480AA59))
#define J_RxDelay              ((ujcrc_t)(0xCDE79F00))
#define J_schedule             ((ujcrc_t)(0xDEEAC928))
#define J_seqno                ((ujcrc_t)(0x709FF915))
#define J_server_address       ((ujcrc_t)(0x338DDCAD))
#define J_serv_port            ((ujcrc_t)(0x7405B388))
#define J_spread_factor        ((ujcrc_t)(0xD933EFAA))
#define J_start                ((ujcrc_t)(0x61BEF413))
#define J_station_conf         ((ujcrc_t)(0xE4AA60B9))
#define J_stop                 ((ujcrc_t)(0x73EDE218))
#define J_term                 ((ujcrc_t)(0x74F9E80E))
#define J_timesync             ((ujcrc_t)(0xD3CACC10))
#define J_threshold            ((ujcrc_t)(0xB76BCE9C))
#define J_txpow_adjust         ((ujcrc_t)(0x03E0F6FD))
#define J_txtime               ((ujcrc_t)(0x02CB1104))
#define J_type                 ((ujcrc_t)(0x74F5FE18))
#define J_upchannels           ((ujcrc_t)(0x7FCAA9EB))
#define J_updf                 ((ujcrc_t)(0x75EFDB07))
#define J_upgrade              ((ujcrc_t)(0xF49BF544))
#define J_uri                  ((ujcrc_t)(0x00757C6E))
#define J_US902                ((ujcrc_t)(0x061FA968))
#define J_US915                ((ujcrc_t)(0x061FA86E))
#define J_user                 ((ujcrc_t)(0x75F0DE11))
#define J_version              ((ujcrc_t)(0x00E51D6C))
#define J_web_port             ((ujcrc_t)(0xA9963701))
#define J_web_dir              ((ujcrc_t)(0xCDD77DAA))
#define J_xtime                ((ujcrc_t)(0x759DF115))
#define J_bandwidth            ((ujcrc_t)(0x0188BDD4))
#define J_chan_FSK             ((ujcrc_t)(0x399777C1))
#define J_chan_Lora_std        ((ujcrc_t)(0xAE60A484))
#define J_clksrc               ((ujcrc_t)(0x028CF35C))
#define J_dac_gain             ((ujcrc_t)(0xB95BD71D))
#define J_datarate             ((ujcrc_t)(0xFC3A1C24))
#define J_dig_gain             ((ujcrc_t)(0x1932BE8A))
#define J_lorawan_public       ((ujcrc_t)(0xF6ECACD6))
#define J_radio_0              ((ujcrc_t)(0xBA1753F6))
#define J_radio_1              ((ujcrc_t)(0xBA1753F7))
#define J_rf_chain             ((ujcrc_t)(0x3497D91E))
#define J_rf_power             ((ujcrc_t)(0x95FCE8DC))
#define J_rssi_offset          ((ujcrc_t)(0x2C99BDFE))
#define J_rssi_offset_lbt      ((ujcrc_t)(0xAFDE7647))
#define J_SX1250               ((ujcrc_t)(0x1FBE0E5B))
#define J_SX1255               ((ujcrc_t)(0x1FBE0E5E))
#define J_SX1257               ((ujcrc_t)(0x1FBE0E5C))
#define J_SX1272               ((ujcrc_t)(0x1FBE0C5B))
#define J_SX1276               ((ujcrc_t)(0x1FBE0C5F))
#define J_sx1301_conf          ((ujcrc_t)(0x2AF5BD41))
#define J_SX1301_conf          ((ujcrc_t)(0xCF76EBC6))
#define J_sx1302_conf          ((ujcrc_t)(0x2BF4BF45))
#define J_SX1302_conf          ((ujcrc_t)(0x76DDEBC0))
#define J_sync_word            ((ujcrc_t)(0xA4BF704D))
#define J_sync_word_size       ((ujcrc_t)(0xE6AAAB54))
#define J_tx_enable            ((ujcrc_t)(0x631F9A2D))
#define J_tx_gain_lut          ((ujcrc_t)(0x43B971DB))
#define J_tx_notch_freq        ((ujcrc_t)(0xA8FCE052))
#define J_pwr_idx              ((ujcrc_t)(0xDFD7588B))
#define J_rssi_tcomp           ((ujcrc_t)(0x47CB0C8F))
#define J_tx_dwelltime_lbt     ((ujcrc_t)(0xBFDD6EA4))
#define J_coeff_a              ((ujcrc_t)(0x87785402))
#define J_coeff_b              ((ujcrc_t)(0x87785401))
#define J_coeff_c              ((ujcrc_t)(0x87785400))
#define J_coeff_d              ((ujcrc_t)(0x87785407))
#define J_coeff_e              ((ujcrc_t)(0x87785406))
#define J_implicit_hdr         ((ujcrc_t)(0xC842AB12))
#define J_implicit_payload_length ((ujcrc_t)(0xA83D6605))
#define J_implicit_crc_en      ((ujcrc_t)(0x531037C1))
#define J_implicit_coderate    ((ujcrc_t)(0x644EF1C1))
#define J_sx1302_conf          ((ujcrc_t)(0x2BF4BF45))
#define J_SX1302_conf          ((ujcrc_t)(0x76DDEBC0))
#define J_tx_lut               ((ujcrc_t)(0x25A75023))
#define J_rf_power             ((ujcrc_t)(0x95FCE8DC))
#define J_fpga_dig_gain        ((ujcrc_t)(0xB17E4194))
#define J_ad9361_atten         ((ujcrc_t)(0x6EA72BD1))
#define J_ad9361_auxdac_vref   ((ujcrc_t)(0x21E8657E))
#define J_ad9361_auxdac_word   ((ujcrc_t)(0x20EC6177))
#define J_ad9361_tcomp_coeff_a ((ujcrc_t)(0x555897EE))
#define J_ad9361_tcomp_coeff_b ((ujcrc_t)(0x555897ED))
#define J_rf_chain_conf        ((ujcrc_t)(0xDF35B2E0))
#define J_rx_enable            ((ujcrc_t)(0x73858A63))
#define J_rssi_offset          ((ujcrc_t)(0x2C99BDFE))
#define J_rssi_offset_coeff_a  ((ujcrc_t)(0x11C37A14))
#define J_rssi_offset_coeff_b  ((ujcrc_t)(0x11C37A17))
#define J_tx_enable            ((ujcrc_t)(0x631F9A2D))
#define J_tx_freq_min          ((ujcrc_t)(0xA3956A08))
#define J_tx_freq_max          ((ujcrc_t)(0xA3957216))
#define J_tx_lut               ((ujcrc_t)(0x25A75023))
#define J_lbt_conf             ((ujcrc_t)(0x5AA8CB99))
#define J_enable               ((ujcrc_t)(0x0697E35F))
#define J_rssi_target          ((ujcrc_t)(0xD983A9C2))
#define J_rssi_shift           ((ujcrc_t)(0x40F516B1))
#define J_chan_cfg             ((ujcrc_t)(0x39BA8AFD))
#define J_freq_hz              ((ujcrc_t)(0xD4F73A99))
#define J_scan_time_us         ((ujcrc_t)(0xB4392EF2))
#define J_SX1301_conf          ((ujcrc_t)(0xCF76EBC6))
#define J_chip_enable          ((ujcrc_t)(0x887A9A91))
#define J_chip_center_freq     ((ujcrc_t)(0xE016F2A3))
#define J_chip_rf_chain        ((ujcrc_t)(0xC99D90A0))
#define J_chan_multiSF_0       ((ujcrc_t)(0x0A1E99ED))
#define J_chan_multiSF_1       ((ujcrc_t)(0x0A1E99EC))
#define J_chan_multiSF_2       ((ujcrc_t)(0x0A1E99EF))
#define J_chan_multiSF_3       ((ujcrc_t)(0x0A1E99EE))
#define J_chan_multiSF_4       ((ujcrc_t)(0x0A1E99E9))
#define J_chan_multiSF_5       ((ujcrc_t)(0x0A1E99E8))
#define J_chan_multiSF_6       ((ujcrc_t)(0x0A1E99EB))
#define J_chan_multiSF_7       ((ujcrc_t)(0x0A1E99EA))
#define J_chan_LoRa_std        ((ujcrc_t)(0x8CA425D4))
#define J_chan_FSK             ((ujcrc_t)(0x399777C1))
#define J_chan_rx_freq         ((ujcrc_t)(0x06FCFE18))
#define J_spread_factor        ((ujcrc_t)(0xD933EFAA))
#define J_bandwidth            ((ujcrc_t)(0x0188BDD4))
#define J_bit_rate             ((ujcrc_t)(0xED4AA68B))
#define J_SX1301_array_conf    ((ujcrc_t)(0x0A4F4BCE))
#define J_board_type           ((ujcrc_t)(0xB6BB08C7))
#define J_board_rx_freq        ((ujcrc_t)(0xE7946A94))
#define J_board_rx_bw          ((ujcrc_t)(0x6E5A1327))
#define J_full_duplex          ((ujcrc_t)(0x3CC1F742))
#define J_FSK_sync             ((ujcrc_t)(0x6CFE62EF))
#define J_loramac_public       ((ujcrc_t)(0x42F0CD46))
#define J_nb_dsp               ((ujcrc_t)(0x2F8B2E0D))
#define J_dsp_stat_interval    ((ujcrc_t)(0x26D3D0B1))
#define J_aes_key              ((ujcrc_t)(0xD9FE95FC))
#define J_calibration_temperature_celsius_room ((ujcrc_t)(0x8D9594E4))
#define J_calibration_temperature_code_ad9361 ((ujcrc_t)(0x2D301DEC))
#define J_fpga_flavor          ((ujcrc_t)(0x1A5CFA3E))
#define J_SX1388_A11           ((ujcrc_t)(0x7D70D2A0))
#define J_SX1388_SAGEMCOM      ((ujcrc_t)(0xD7A4F74B))
#define J_SX1388_B11           ((ujcrc_t)(0x7D73CEA3))
#define J_SX1388_KERLINK       ((ujcrc_t)(0xEBC39360))
#define J_SX1388_C11           ((ujcrc_t)(0x7D72CEA2))
#define J_SX1388_CISCO         ((ujcrc_t)(0x4432F439))
#define J_SX1388_E11           ((ujcrc_t)(0x7D7CD2A4))
#define J_SX1388_SEMTECH       ((ujcrc_t)(0xE9AC9268))
#define J_SX1388_F11           ((ujcrc_t)(0x7D7FCEA7))
#define J_SX1388_FOXCONN       ((ujcrc_t)(0x9CA462ED))
#define J_SX1388_L11           ((ujcrc_t)(0x7D75D2AD))
#define J_SX1388_MULTITECH     ((ujcrc_t)(0xA42F71FA))
#define J_lbt_enable           ((ujcrc_t)(0x1C7A0E2A))
#define J_freq_band            ((ujcrc_t)(0xB067FA9A))
#define J_rx_freq              ((ujcrc_t)(0xEB1D6E55))
#define J_wifi_cfg             ((ujcrc_t)(0xA90D75DA))
#define J_wifi_scan            ((ujcrc_t)(0xE63F210E))
#define J_wifi_ssid            ((ujcrc_t)(0xE60F391C))
#define J_wifi_pass            ((ujcrc_t)(0xE13C3600))
#define J_cups_uri             ((ujcrc_t)(0x594AB0B8))
#define J_LUT_BASE             ((ujcrc_t)(0x4E5FF50A))
#define J_capabilities         ((ujcrc_t)(0x1B0F1267))
