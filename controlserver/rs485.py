def funcmap(devname, devid):
    m = brooks_mfc(devname, devid)
    return {'init_state': m.init_state, 'get_flow': m.get_flow, 'set_flow': m.set_flow,
            'get_curr_setp': m.get_curr_setp, 'get_fs_range': m.get_fs_range, 'handle': m}

# some utility functions
def checksum_sum(s): return chr(sum(ord(c) for c in s)%256)
import struct
def to_short(s): return struct.unpack('<H', s)[0]
def from_short(x): return struct.pack('<H', x)
def to_sshort(s): return struct.unpack('<h', s)[0]
def to_hex(s): return ':'.join("{0:x}".format(ord(c)) for c in s)
def to_int(s): return struct.unpack('<I', s)[0]
def from_int(x): return struct.pack('<I', x)

# usage in ipython:
# import rs485
# rs485.init_comm()
# m = rs485.brooks_mfc('somename', '\x32')
# m.init_state(10.0) # which is the fullscale range, it doesn't set it.
# m.get_flow()
# or to use the funcs directly:
# _get_flow('\x32', 10.0)  # macid of the device and its FS range.
# ..

#_TEST = False
_DEBUG = False # turn this on for debug output on console.

import serial 
_baud_rates = [9600, 19200, 38400, 115200]
# smaller timeouts are better for faster BRs, 0.000 doesn't work at all.
# for 115200, 0.005 maybe better timeout, experimentally it produces lower number 
# of queries (in cmd_io) on average. similarly 0.01 for 9600
_tm_o = {115200: 0.002, 9600: 0.01}
# too many errors and long delays at lower BR

import threading
chan_d = {'lock':threading.RLock(), 'portname':'/dev/ttyS0', 'port': None, 'cbr': 115200, 'timeout':_tm_o[115200], 'error_attempts':100}
# better not to use the probing of br, since in case of noise (at present) 
# 9600 bauds will be picked up, which is not good. for best results use:
# port_open(br=115200, tm_o=0.002)
def port_open(port=0, br=115200): 
    return serial.Serial(port, br, parity=serial.PARITY_NONE, stopbits=1, timeout=_tm_o[br])
# brooks RS232-RS485 needs 1 start bit, 8 data bits, 1 odd parity bit, 1 stop bit.
def set_port(p): 
    global chan_d
    chan_d['port'] = p
def port_close(): chan_d['port'].close()
def init_comm(): 
    # following is done to avoid communication errors
    # ideally it should work with set_port(port_open()) only
    set_port(port_open(br=9600))
    set_cbr(chr(32), br=115200)
    set_cbr(chr(33), br=115200)
    port_close()
    set_port(port_open())

## setting the br to 9600 and resetting to 115200 used to give correct channel state.
#def change_br9600(): port_open(br=115200) [set_cbr(m, br=9600) for m in mfcs] port_close() port_open(br=9600)
class brooks_mfc():
# fullscale value must have a decimal
    name, macid = None, '\x00'
    fs_range, curr_setp, actv_flow, ramptime = None, 0.0, 0.0, 0.0
    
    def __init__(self, name, macid):
        self.name, self.macid = name, chr(macid)
    def init_state(self, args):
        self.fs_range, self.curr_setp = args['fs_range'], args['init_val']
        set_cbr(self.macid, br=chan_d['cbr'])
        self.set_flow([self.curr_setp])
        self.get_flow([])
    def set_flow(self, args):
        s = float(args[0])
        if 0 <= s <= self.fs_range: 
            self.curr_setp = s
            return 'OK', [_set_setpoint_immediately(self.macid, s, self.fs_range, self.ramptime), s]
        else: return 'Error', ['Flow is beyond range(0, %f'%(self.fs_range)+'): '+args[0]]
    def get_flow(self, args):
        self.actv_flow = _get_flow(self.macid, self.fs_range)
        return 'OK', ['%.3f'%(self.actv_flow)] # it can be negative due to noise, but we display positive.
    def set_ramptime(self, args):
        self.ramptime = float(args[0])
        return 'OK', ['']
    def get_curr_setp(self, args):
        return 'OK', [repr(self.curr_setp)]
    def get_fs_range(self, args):
        return 'OK', [repr(self.fs_range)]

        
class MFC_Error(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

_STX, _ACK, _NAK = '\x02', '\x06', '\x16'
_R, _W = '\x80', '\x81'
_PAD = '\x00'
_mps = 9 # minimum packet size
# note that device is appending \x00 after macid, so _mps is 10 instead of 9.
_ack_pkt_sz = 1

# a packet in l-protocol :
# macid + stx + ccode + pktlen + classid + instanceid + attrid + data + pad(0x00) + cksum
def form_cmd(devid, rw, func, data):
    msg = _STX + rw + chr(len(data)+3) + func[0] +\
            func[1] + func[2] + data + _PAD
    msg =  devid + msg + checksum_sum(msg)
    return msg

def parse_resp(s):
    if _DEBUG: print 'Received(', len(s), '): ', to_hex(s)
    if checksum_sum(s[1:-1]) != s[-1]: raise MFC_Error("Checksum incorrect")
    dlen, func = ord(s[3]), (s[4], s[5], s[6])
    d = s[7:7+dlen-3]
    return func, d

def parse_ack(s):
    if _DEBUG: print 'Received(', len(s), '): ', to_hex(s)
    if s == _ACK: return True
    return False

# wrapper for sending cmds and recving response
def cmd_io(cmdstr, pkt_sz, monitor_attempts=False, attempts=chan_d['error_attempts']):
    def find_ack(s):
        for i in xrange(len(s)):
            if s[i]==_ACK or s[i]==_NAK: 
                return s[i], s[i+1:]
        return '', ''
    _PORT = chan_d['port']
    _LOCK = chan_d['lock']
    # write to the device
    if _DEBUG: print 'Sending(', len(cmdstr), '): ', to_hex(cmdstr), '. Expecting', pkt_sz, 'bytes.'
    c, s, i, a = '', '', 0, attempts
    with _LOCK:
        while not monitor_attempts or a > 0: # loop till correct resp (positive or negative is reached)
            a -= 1
            _PORT.write(_ACK)
            c, s, i = '', '', 0
            _PORT.write(cmdstr)
            while c=='' and i<3: #3 is arbitrary
                try: c = _PORT.read(100) # read as much as it yields, 100 is arbitrary
                except (serial.serialutil.SerialException, OSError): pass
                i += 1
            if c=='': continue
            if _DEBUG: print 'Ack(trials:',i,')', to_hex(c), '[len:', len(c), ']'
            # most of the times correct response is received with ACK token, so,
            c, s = find_ack(c)
            #_PORT.write(_ACK)
            # pkt_Sz is only indicator of max response sent by the device.
            i = 0
            while len(s)<pkt_sz and i<3: # 3 is arbitrary
                try: s += _PORT.read(pkt_sz)
                except (serial.serialutil.SerialException, OSError): pass
                i += 1
            if _DEBUG: print 'resp(trials:',i,')', to_hex(s), '[len:', len(s), ']'
            if s=='': continue # no resp! query again.
            # if c earlier had fragments from earlier unsuccessful run, then it is '' now
            # so, read it again from s. if not found, s = c = '', which will lead to query again.
            elif c!=_ACK and c!=_NAK: c, s = find_ack(s)
            if len(s) >= pkt_sz: break
    
        if _DEBUG: print 'Queries made:', attempts-a
        if monitor_attempts and a == 0: raise MFC_Error("No response")
        if c == _NAK: raise MFC_Error("Command incorrect.")
        if s[0] == _NAK: raise MFC_Error("Failed to process command.")
        _PORT.write(_ACK)
    return s

def get_macid(devid):
    cmd = form_cmd(devid, _R, ('\x03', '\x01', '\x01'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 1))
    return ord(d)
def set_macid(devid, newid):
    cmd = form_cmd(devid, _W, ('\x03', '\x01', '\x01'), chr(newid))
    try:
        if parse_ack(cmd_io(cmd, 1, monitor_attempts=True, attempts=20)): return newid
    except MFC_Error: pass
    return 0

def get_cbr(devid):
    cmd = form_cmd(devid, _R, ('\x03', '\x01', '\x65'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 4))
    return to_int(d)
def set_cbr(devid, br):
    cmd = form_cmd(devid, _W, ('\x03', '\x01', '\x65'), from_int(br))
    try:
        if parse_ack(cmd_io(cmd, 1, monitor_attempts=True, attempts=20)): return br
    except MFC_Error: pass
    return 0

    
# note that documentation says it is gas id is one byte, but it is 2 bytes.
def get_process_gas(devid):
    cmd = form_cmd(devid, _R, ('\x66', '\x00', '\x65'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 2))
    return to_short(d)
def set_process_gas(devid, calib_inst):
    cmd = form_cmd(devid, _W, ('\x66', '\x00', '\x65'), from_short(calib_inst))
    if parse_ack(cmd_io(cmd, 1)): return calib_inst
    return 0
def get_numgases(devid):
    cmd = form_cmd(devid, _R, ('\x66', '\x00', '\xA0'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 1))
    return ord(d)

# use onoff='\x00' to disable.
def enable_autozero(devid, onoff='\x01'):
    cmd = form_cmd(devid, _W, ('\x68', '\x01', '\xA5'), onoff)
    if parse_ack(cmd_io(cmd, 2)): return True
    return False

# doc says it return 2 byte, but device returns 4.
def get_sensor_zero_offset(devid):
    cmd = form_cmd(devid, _R, ('\x68', '\x01', '\xA9'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 2))
    return to_short(d[0:2]), to_short(d[2:4]) 

def get_sensor_zero_ref_offset(devid):
    cmd = form_cmd(devid, _R, ('\x68', '\x01', '\xAA'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 2))
    return to_short(d)
def set_sensor_zero_ref_offset(devid, zero):
    cmd = form_cmd(devid, _W, ('\x68', '\x01', '\xAA'), from_short(zero))
    if parse_ack(cmd_io(cmd, 2)): return zero
    return 0

def set_zero_enable(devid, onoff='\x01'):
    cmd = form_cmd(devid, _W, ('\x68', '\x01', '\xBA'), onoff)
    if parse_ack(cmd_io(cmd, 1)): return True
    return False
def get_zero_enable_status(devid):
    cmd = form_cmd(devid, _R, ('\x68', '\x01', '\xBA'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 1))
    return ord(d)


_io_modes = { 'digital': '\x01', 'analog': '\x02' }
_io_modes_codes = { '\x01': 'digital', '\x02': 'analog' }
def get_io_mode(devid):
    cmd = form_cmd(devid, _R, ('\x69', '\x01', '\x03'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 1))
    return _io_modes_codes[d]
def set_io_mode(devid, mode='digital'):
    cmd = form_cmd(devid, _W, ('\x69', '\x01', '\x03'), _io_modes[mode])
    if parse_ack(cmd_io(cmd, 1)): return mode
    return 'Not changed'
# get and set default control mode. (as above), 69, 01, 04.
def get_default_io_mode(devid):
    cmd = form_cmd(devid, _R, ('\x69', '\x01', '\x04'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 1))
    return _io_modes_codes[d]
def set_default_io_mode(devid, mode='digital'):
    cmd = form_cmd(devid, _W, ('\x69', '\x01', '\x04'), _io_modes[mode])
    if parse_ack(cmd_io(cmd, 1)): return mode
    return 'Not changed'


def _code(s, fullscale): return int((0xC000-0x4000)*(s/fullscale) + 0x4000)
def _decode(c, fullscale): return ((c - 0x4000)*fullscale) / (0xC000-0x4000)

# setpoint is always absolute value of flow in sccm. e.g. 35 sccm.
def _set_setpoint(devid, setp, fullscale):
    cmd = form_cmd(devid, _W, ('\x69', '\x01', '\xA4'), from_short(_code(setp, fullscale)))
    if parse_ack(cmd_io(cmd, 1)): return setp
    return -1
def set_ramptime(devid, ramp):
    # ramp time is in ms
    cmd = form_cmd(devid, _W, ('\x6A', '\x01', '\xA4'), from_short(ramp))
    if parse_ack(cmd_io(cmd, 1)): return ramp
    return -1
def _get_flow(devid, fullscale):
    cmd = form_cmd(devid, _R, ('\x6A', '\x01', '\xA9'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 2))
    return _decode(to_short(d), fullscale)
def get_filtered_setp(devid, fullscale): 
    # this is setpoint after ramping has been applied.
    cmd = form_cmd(devid, _R, ('\x6A', '\x01', '\xA6'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 2))
    return _decode(to_short(d), fullscale)
def get_valve_drive_curr(devid):
    cmd = form_cmd(devid, _R, ('\x6A', '\x01', '\xB6'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 2))
    return to_sshort(d)/327.68

def set_freeze_follow_bcast(devid):
    # 1 = act immediately on new set point.
    cmd = form_cmd(devid, _W, ('\x69', '\x01', '\x05'), '\x01')
    if parse_ack(cmd_io(cmd, 1)): return 'Will act imediately on set point'
    return 'Not changed'

# Following two are preferred way to setup flow.
def set_freeze_follow_setp(devid, freeze=1):
    # freeze 0 = freeze curr. setp, 1 = use new setp (previously sent) immediately
    cmd = form_cmd(devid, _R, ('\x69', '\x01', '\x05'), chr(freeze))
    func, d = parse_resp(cmd_io(cmd, 0))
    return
def _set_setpoint_immediately(devid, setp, fullscale, ramptime, freeze='\x01'):
    # freeze 0: store setp and ramptime and no change to curr. setp. freeze_follow_setp
    # can then be used to trigger the stored setpoint. This state is cancelled by
    # a setpoint command. In this state, other requests are served as usual.
    # freeze 1: use setp and ramp rate now.
    # Ramp time is in ms.
    c = _code(setp, fullscale)
    cmd = form_cmd(devid, _W, ('\x69', '\x01', '\xA6'), 
            freeze+from_short(c)+from_short(ramptime))
    if parse_ack(cmd_io(cmd, 1)): return setp
    return -1
def get_flow_long(devid, fullscale):
    cmd = form_cmd(devid, _R, ('\x6A', '\x01', '\xAA'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 8))
    c = _decode(to_short(d[0:2]), fullscale)
    transducer, signal, temp = map(to_sshort, (d[x:x+2] for x in [2, 4, 6]))
    return {'Flow (sccm)': c, 'Upstream pressure transducer (psi)': transducer/100.0, 
            'Valve signal (%V or mA)': signal/327.68, 'Int. Temp. (100*C)': temp/100.0}



# gen2 commands
def get_manuf_id(devid):
    cmd = form_cmd(devid, _R, ('\x03', '\x01', '\xC5'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 1))
    return d
def get_fw_version(devid):
    cmd = form_cmd(devid, _R, ('\x03', '\x01', '\xC6'), '')
    # max ps = 16, fewer acceptable, so
    func, d = parse_resp(cmd_io(cmd, _mps + 1))
    return d
def get_dev_details(devid):
    cmd = form_cmd(devid, _R, ('\x03', '\x01', '\xC7'), '')
    # max ps = 19, fewer acceptable, so
    func, d = parse_resp(cmd_io(cmd, _mps + 1))
    return ['fullscale*10', 'gasid', 'calib1', 'calib2'], map(to_int, (d[x:x+4] for x in [0, 4, 8, 12]))
def get_serial_no(devid):
    cmd = form_cmd(devid, _R, ('\x03', '\x01', '\xC8'), '')
    # max ps = 16, fewer acceptable, so
    func, d = parse_resp(cmd_io(cmd, _mps + 1))
    return d
def get_info(devid):
    return {'Manufacturer ID': get_manuf_id(devid), 'Firmware version': get_fw_version(devid),
            'Device details': get_dev_details(devid), 'Serial no.': get_serial_no(devid)}

def get_recvd_cmd(devid, fullscale):
    cmd = form_cmd(devid, _R, ('\x6A', '\x01', '\xAB'), '')
    func, d = parse_resp(cmd_io(cmd, _mps + 7))
    return {'Freeze follow flag': ord(d[0]), 
            'Target setpoint': _decode(to_short(d[1:3]), fullscale),
            'Next setpoint': _decode(to_short(d[3:5]), fullscale), 
            'Ramp time': to_short(d[5:7])}








