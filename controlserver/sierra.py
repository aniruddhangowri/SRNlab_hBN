import serial
from bidict import bidict


import threading
# timeout = 0.025 is minimum to not give communication errors. Raising it to larger values
# increases the response times, for example at 0.1 s timeout, get_pressure_position is
# returned in 240 ms, whereas it takes ~112 ms at 0.03 timeout (~105 ms at 0.025 timeout).
# T3Bi typical response time is less than 20 ms, so it may be rs232-USB bridge that
# is introducing additional delays.
chan_d = {'tvc': {'lock':threading.RLock(), 'portname': "/dev/tty", 'port': None, 'timeout': 0.05, 'cmd_mod':'#'},
            # cmd_modifiers: {\@: echo first char of command sent, \!: echo status and first char,
            # \#: echo status and all chars of command sent}
            'mfc-n2-1': {'lock': threading.RLock(), 'portname': "/dev/tty", 'port': None, 'timeout': 0.05}}

def init_comm():
    #identify which port belongs to tvc, the other belongs to mfc-n2-1.
    # right now we just assign it blindly. 
    chan_d['mfc-n2-1']['port'] = serial.Serial('/dev/ttyUSB1') #, timeout=chan_d['tvc']['timeout'])
    #chan_d['tvc']['port'] = serial.Serial('/dev/ttyUSB0', timeout=chan_d['tvc']['timeout'])

def finish_comm():
    for k in chan_d.keys(): k['port'].close()

class sierra_mfc():
    """Command - Resp format is (on RS232):
    ? Cmd LRC CRLF = read command
    ! Cmd LRC CRLF = write command
    Cmd Val LRC CRLF = resp
    LRC = 8 bit 2's complement of all chars till LRC CRLF bytes.
    Other commands on MFC are: Zero. Reset Zero, Span.
    Calculation of LRC doesnot match one of the 4 examples given in manual."""
    name, devid, port = None, None, None
    fs_range, curr_setp, actv_flow = 0.0, 0.0, 0.0
    gas_name, units = None, None
    errcodes = {-1: 'Reuqested flow is beyond range'}
    ## these can be used directly to avoid calculating them every time.
    ## but not used at the moment, as it will add complexity to cmd_io.
    #cmdstrs = {
    #        'units': '?Unts'+hex(self.lrc('?Unts'))[2:]+'\r\n', 
    #        'gasname': '?Gnam'+hex(self.lrc('?Gnam'))[2:]+'\r\n', 
    #        'serialno': '?Srnm'+hex(self.lrc('?Srnm'))[2:]+'\r\n', 
    #        'versionno': '?Vrnm'+hex(self.lrc('?Vrnm'))[2:]+'\r\n', 
    #        'fullscale': '?Fscl'+hex(self.lrc('?Fscl'))[2:]+'\r\n', 
    #        'flow': '?Flow'+hex(self.lrc('?Flow'))[2:]+'\r\n', 
    #        '': '?Unts'+hex(self.lrc('?Unts'))[2:]+'\r\n', 
    #}
    def __init__(self, name, devid):
        self.name, self.devid = name, devid
        self.io = chan_d[devid[0]]
    def lrc(self, cmd):# calc redundancy check bytes for cmd
        l = 0
        for c in cmd: l += ord(c)
        l = l%256
        l = -l + (1 << 8)
        l = l%256
        return hex(l)[2:]
    def cmd_io(self, cmdstr, calc=0):
        #REM
        #return 'xxxx0.0'
        res, c = '', None
        with self.io['lock']:
            cmdstr = cmdstr + self.lrc(cmdstr)+'\r\n'
            self.io['port'].write(cmdstr)
            while c!='\n':
                c = self.io['port'].read()
                res += c
                print res
        # we don't do LRC check on return values.
        return res[:-4]
    def init_state(self, args):
        self.fs_range, self.curr_setp = args['fs_range'], args['init_val']
        self.set_flow([self.curr_setp])
        self.get_flow([])
    def set_flow(self, args):
        s = float(args[0])
        if 0 <= s <= self.fs_range: 
            self.curr_setp = s
            return 0, [self.cmd_io('!Setr%2.1f'%(s))[4:]]
        else: return -1, [args[0]]
    def get_flow(self, args):
        res = float(self.cmd_io('?Flow')[4:])
        self.actv_flow = res
        return 0, ['%.3f'%(self.actv_flow)] # it can be negative due to noise, but we display positive.
    def get_curr_setp(self, args):
        return 0, [repr(self.curr_setp)]
    def get_fs_range(self, args):
        self.fs_range = float(self.cmd_io('?Fscl')[4:])
        return 0, [repr(self.fs_range)]
    def get_gas_name(self, args):
        self.gas_name = self.cmd_io('?Gnam')[4:]
        return 0, [self.gas_name]
    def get_units(self, args):
        self.units = self.cmd_io('?Unts')[4:]
        return 0, [self.units]
    def get_info(self, args):
        ver = self.cmd_io('?Vern')[4:]
        ser = self.cmd_io('?Srnm')[4:]
        return 0, ['Version no.: '+ver, 'Serial No.: '+ser]


class tvc():
    name = None
    state, actv_ch, low_fs, high_fs = 'M5411', 'H', 1, 1000
    setps = {
            # the setpoints which are not initialised are set to close position.
            'A':['Position', 0.0, 100.0],
            'B':['Position', 0.0, 100.0],
            'C':['Position', 0.0, 100.0],
            'D':['Position', 0.0, 100.0],
            'E':['Position', 0.0, 100.0]
            #'analog':{'mode':'pressure', 'val':0.0} #not clear how to use analog setpoint.
            }
    setp_params = {
            # the setpoints which are not initialised are set to close position.
            'A':[10000, 20],
            'B':[2000, 20],
            'C':[1000, 20],
            'D':[1000, 20],
            'E':[1000, 20]
            }
    actv_setp, valve_state = None, None
    slowpump = {'state': 'disable', 'pressure': 0.0, 'rate': 20.0}
    fallback_state = 'Close'
    def __init__(self, name, devid):
        self.name = name
    def init_state(self, args):
        # open or close the valve
        if args['manual-setp']=='Open': _valve_open()
        # set the sensor ranges
        if args['reset_sensor_range']:
            _set_sensor_high_range(args['high_sensor_fs_range'])
            _set_sensor_low_range(args['low_sensor_fs_range'])
        self.get_sensor_ranges([])
        # see if slowpump is enabled, set accordingly.
        self.slowpump = args['slowpump']
        #_set_slowpump_rate(self.slowpump['rate'])
        #_set_slowpump_enable(self.slowpump['state'])
        #_set_slowpump_pressure(self.slowpump['pressure'])
        # set safety state
        self.fallback_state = args['fallback_state']
        _set_ss(self.fallback_state)
        # set crossover parameters
        #get and set the setpoint values
        for s in args['setpoints']:
            self.setps[s[0]] = s[1:]
            _set_setp_values(s[0], self.setps[s[0]])
        # activate a setpoint if needed
        if args['actv_setpoint'] != 'manual': self.activate_setp(args['actv_setpoint'])
        #self.get_actv_setp_ch([])

        #other initialisation steps are
        # _set_sensor_low_range('EL03')  # for low range sensor at 1 torr.
        # _set_sensor_high_range('EH10') # for high sensor range to 1000 torr
        # _set_xover_delay(90) # change the delay for autocrossover
        # _set_high_chan_xover_pt(0.9) # change the % of FS range of high sensor when crossover occurs.
        # _set_low_chan_xover_pt(100) # similar for low gauge

    def get_pressure(self, args):
        return 'OK', [_get_valve_pressure(self.actv_ch, self.high_fs, self.low_fs)]
    def get_position(self, args):
        return 'OK', [_get_valve_position()]
    def get_pressure_position(self, args):
        # the combined commands reduce the time taken to 40 ms, compared to
        # 150 ms for doing them separately. It also introduces some problems
        # in getting response on time.
        #p, v, st = 0, 0, self.state
        #try: p, st = _cmd_io('R5\nR7').split('\n', 2)
        # if len(st)>5, then we are reading another response, which will
        # cause problem in next request. Don't know how to get around this.
        #except KeyError: # because cmd_io doesn't get a '0' at start.
        #    lst = _cmd_io('R5\nR6\nR7').split('\n')
        #    for l in lst:
        #        if l[0] == 'V': v = l
        #        elif l[0] == 'M': st = l
        #        elif l[0] == 'P' or l[1] == 'P': p = l
        
        #p, st = _cmd_io('R5\nR7').split('\n',1) # this is done to make response fast.
        #print st
        #self.state = st
        #self.actv_ch = _sensor_ch_status[st[4]][0]
        #if self.actv_ch == 'H': p = 0.01*float(p[2:])*self.high_fs
        #else: p = float(p[2:])*self.low_fs

        # there is no need to determine which channel is in use when the mode
        # is auto. In this case following formula works alright.
        # the code above was written assuming that I have to find out which
        # channel is in use to determine the fs range being referred to.
        p = _cmd_io('R5')
        p = 0.01*float(p[2:])*self.high_fs
        v = float(_cmd_io('R6')[2:])
        #self.actv_ch = _get_valve_state()['Active Sensor'][0]
        #p1, p2 = _get_valve_pressure(self.actv_ch, self.high_fs, self.low_fs), _get_valve_position()
        #return 'OK', ['%.3f/%.2f'%(p1, p2)]
        return 'OK', ['%.5f,%.4f'%(p, v)]
    def valve_open(self, args):
        _valve_open()
        return 'OK', ['open']
    def valve_close(self, args):
        _valve_close()
        return 'OK', ['close']
    def get_setp_state(self, args):
        setpname = args[0]
        if setpname not in self.setps:
            return 'Error', ['Setpoint '+setpname+' is not valid']
        self.setps[setpname] = _get_setp_values(setpname)
        return 'OK', [setpname, self.setps[setpname]]
    def set_setp_state(self, args):
        """args: setpointname mode value"""
        setpname, mode, v1, v2 = args[0], args[1], float(args[2]), float(args[3])
        if setpname not in self.setps or mode not in _setp_mode.values() or \
                not (0 <= v1 <= 100) or not (0.1 <= v2 <= 100):
            return 'Error', ['Setpoint '+setpname+' or mode '+mode+' or its value '\
                    +repr(v1)+'or its softstart rate '+repr(v2)+' is not invalid.']
        values = [mode, v1, v2]
        _set_setp_values(setpname, values)
        self.setps[setpname] = values
        return 'OK', [setpname, values]
    def get_sensor_ranges(self, args):
        self.high_fs = float(_get_sensor_high_range()[:-5])
        self.low_fs = float(_get_sensor_low_range()[:-5])
        return 'OK', [self.high_fs, self.low_fs]
    def get_actv_setp_ch(self, args):
        res = _get_valve_state()
        self.actv_setp = res['Setpoint']
        self.valve_state = res['Valve']
        self.actv_ch = res['Active Sensor'][0]
        return 'OK', [self.actv_setp]
    def activate_setp(self, args):
        resp = _activate_setp(args[0])
        # check for errors!
        self.actv_setp = args[0]
        return 'OK', [self.actv_setp, self.setps[self.actv_setp]]
    def set_setp_params(self, args):
        setpname, i1, i2 = args[0], int(args[1]), int(args[2])
        if setpname not in self.setps or not (1 <= i1 <= 32767) or not (1 <= i2 <= 32767):
            return 'Error', ['Setpoint '+setpname+' or its gain or phase'\
                    +repr(i1)+','+repr(i2)+' is invalid']
        _set_setp_gain(setpname, i1)
        _set_setp_phase(setpname, i2)
        return 'OK', [setpname, i1, i2]
    def get_setp_params(self, args):
        setpname = args[0]
        if setpname not in self.setps:
            return 'Error', ['Setpoint '+setpname+' is not valid']
        self.setp_params[setpname] = [_get_setp_gain(setpname), _get_setp_phase(setpname)]
        return 'OK', [setpname, self.setp_params[setpname]]


class TVC_Error(Exception):
    def __init__(self, value, dat):
        self.value = value + repr(dat)
    def __str__(self):
        return repr(self.value)


    
def _get_all_state():
    return {
            'Valve type': _get_valve_type(),
            'Pressure control mode': _get_press_cntrl_mode(),
            'Pressure units': _get_press_units(),
            'Crossover params, A(ms), H(Torr), L(Torr)': [_get_auto_chan_xover_delay(),\
                    _get_high_chan_xover_pt(), _get_low_chan_xover_pt()],
            'Pressure ranges (Torr), H, L': [_get_sensor_high_range(), _get_sensor_low_range()],
            'Sensor signal-input range': _get_sensor_sigin_range(),
            'Setpoints': _get_setp_status(),
            'Valve State': _get_valve_state(),
            'Valve control state': _get_cntrl_state(),
            'Slowpump enabled with rate': [_get_slowpump_enable(), _get_slowpump_rate()],
            'Valve, encoder position': [_get_valve_position(), _get_encoder()]
            }

def _get_setp_status(s=None):
    slist = ['A','B', 'C', 'D', 'E']
    if s is not None: slist = [s]
    state = {}
    for x in slist: state[x] = _get_setp_values(x)
    if s is None: state['Analog'] = _get_analog_setp_range()
    return state


def _valve_open(): return _cmd_io('O', eps=0)
def _valve_close(): return _cmd_io('C', eps=0)
def _valve_hold(): return _cmd_io('H', eps=0)
def _stop_calib_valve(): return _cmd_io('Q', eps=0)
def _reset(): return _cmd_io('IX', eps=0)
def _get_valve_type(): return _cmd_io('RJT')
_press_cntrl_modes = bidict({'1':'PID', '0':'Model'})
def _get_press_cntrl_mode(): return _press_cntrl_modes[_cmd_io('R51')[1]]
def _set_press_cntrl_mode(m):
    try: return _cmd_io('V'+_press_cntrl_modes[:m])
    except KeyError: return 'Allowed modes are PID|Model, given:'+m
_p_units = bidict({ '00':'Torr', '01':'mTorr', '02': 'mBar', '03': 'uBar', '04': 'kPa', '05': 'Pa', '06': 'cm H2O', '07': 'in H2O' })
def _get_press_units(): return _p_units[_cmd_io('R34')[1:3]]
def _set_press_units(u):
    try: res = _cmd_io('F'+_p_units[:u]); return _p_units[res[1:3]]
    except KeyError: return 'Allowed units are Torr|mTorr|mBar, given:'+u
def _learn_system(): return _cmd_io('L', eps=0)
#def learn_valve_steps(): _cmd_io('J'); return '' #only needed after repairs
_actv_chan = bidict({'A':'Auto', 'H':'High', 'L':'Low'}) # high = ch1, low = ch2
_valve_status = bidict({'0':'controlling', '2':'open', '4':'close'})
_pressure_status = bidict({'0':'<=10% FS', '1':'>10% FS'})
_sensor_ch_status = bidict({ '0': 'LAD', '1':'HAD', '3':'HHD', '4':'LAE',\
        '5':'HAE', '7':'HHE', '8':'LLD', ':':'LLE'})
def _get_valve_state():
    s = _cmd_io('R7')
    return {'Setpoint': _setp_ctrl_resp[s[1]], 'Valve': _valve_status[s[2]],
            'Pressure': _pressure_status[s[3]], 'Active Sensor': _sensor_ch_status[s[4]]}
def _set_actv_chan(c):
    try: return _cmd_io('L'+_actv_chan[:c])
    except KeyError: return 'Allowed channels are Auto|High|Low, given:'+c
def _set_auto_chan_xover_delay(ms):
    i = int(ms)
    if i < 0 or i > 999: return 'Time should be 0<t<1000, given:'+ms
    return _cmd_io('LD%03i'%(i)) #100 msec default, leave as it is.
def _get_auto_chan_xover_delay(): return {'Delay (ms):': _cmd_io('RD')[2:]}
# following is 0.9% of full scale (i.e. 1000 torr in our case). We want it to be ~ 0.1
def _set_high_chan_xover_pt(v):
    f = float(v)
    if f < 0 or f > 1: return 'A number <1 is required, given:'+v
    return _cmd_io('LHC%.1f'%(f))
def _get_high_chan_xover_pt(): return {'High channel x-over pt (in % of high)': _cmd_io('RHC')[2:]}
def _set_low_chan_xover_pt(v): 
    i = int(v)
    if i < 0 or i > 100: return 'A number 0<x<100 is required, given:'+v
    return _cmd_io('LLC%03i'%(i))
def _get_low_chan_xover_pt(): return {'Low channel x-over pt (in % of high)': _cmd_io('RLC')[2:]}
_safety_states = bidict({'0':'Open', '1':'Close', '2':'Hold', '3': 'Safe', '4': 'Cycle'})
def _set_ss(state): 
    try: return _cmd_io('SS'+_safety_states[:state])
    except KeyError: return 'Allowed states are Open|Close|Hold|Safe|Cycle, given:'+state
def _get_ss(): return {'Valve safety state': _safety_states[_cmd_io('RSS')[2]]} 
# sensor must be connected before changing the sigin-range.
_sensor_sigin_ranges = bidict({'0':'1', '1':'5', '2':'10'})
def _set_sensor_sigin_range(r): 
    try: return _cmd_io('G'+_sensor_sigin_ranges[:r])
    except KeyError: return 'Allowed ranges are 1|5|10, given:'+r
def _get_sensor_sigin_range(): return repr(_sensor_sigin_ranges[_cmd_io('R35')[1]])+' V'
_sensor_ranges = bidict({'03':'1 Torr', '06': '10 Torr', '08': '100 Torr', '10': '1000 Torr'}) # using only ranges we need.
def _set_sensor_low_range(r): 
    # to change the range of the gauges attached on T3Bi, one has
    # to enter the calibration mode. If any other command yields
    # "command ignored" response, check if it needs Calib. mode.
    try:
        resp = _cmd_io('CAL1234') # to enter protected mode.
        resp0 = _cmd_io('EL'+_sensor_ranges[:r+' Torr'])
        resp = _cmd_io('USR') # come back to user mode.
        return resp0
        # _cmd_io('ROM') can be used to check the mode of instrument.
    except KeyError: return 'Allowed ranges are 1|10|1000, given:'+r
def _get_sensor_low_range(): return _sensor_ranges[_cmd_io('R55')[2:4]] # initial is 10 torr
def _set_sensor_high_range(r):
    try:
        resp = _cmd_io('CAL1234')
        resp0 = _cmd_io('EH'+_sensor_ranges[:r+' Torr'])
        resp = _cmd_io('USR')
        return resp0
    except KeyError: return 'Allowed ranges are 1|10|1000, given:'+r
def _get_sensor_high_range(): return _sensor_ranges[_cmd_io('R33')[2:4]] # initial is 1000 torr
# sets the minimum valve position for pressure control mode, 0-30 %, 0 is default.
def _vset_pump_speed_pedestal(v): 
    f = float(v)
    if f < 0 or f > 30: return 'A number 0<x<30 is required, given:'+v
    return _cmd_io('SCP%02i'%(f))
def _get_pump_speed_pedestal(): return _cmd_io('RCP')

# Speedup compensation parameter: used to compensate for measurement delays due
# to gauges. there is one compensation constant and one filter constant (5-10
# times smaller than former). 
def _speedup_compensator(i): return _cmd_io('SUE%1i'%(i))
def _get_speedup_compensator(): return _cmd_io('RUE')
def _set_speedup_constant(v): 
    f = float(v)
    if f < 0.01 or f > 0.1: return 'A number 0.01<x<0.1 is required, given:'+v
    return _cmd_io('SUT%1.2f'%(f))
def _get_speedup_constant(): return _cmd_io('RUT')
def _set_speedup_filter(v): 
    f = float(v)
    if f < 0.01 or f > 0.1: return 'A number 0.01<x<0.1 is required, given:'+v
    return _cmd_io('SUF%1.2f'%(f))
def _set_speedup_filter(): return _cmd_io('RUF')

# how does analog setpoint work?
# Following a dozen functions can be compressed in 2 if the codes used
# in commands and response were uniform. 
_setp_ctrl_cmd = bidict({'1':'A', '2':'B', '3':'C', '4':'D', '5':'E', '6':'analog', '7':'open', '8':'close'})
_setp_ctrl_resp = bidict({'0':'analog', '1':'A', '2':'B', '3':'C', '4':'D', '5':'E', '6':'open', '7':'close', '8':'stop', '9':'learning'})
_setp_ctrl_req = bidict({'25':'analog', '26':'A', '27':'B', '28':'C', '29':'D', '30':'E'})
_setp_phase_req = bidict({'41':'A', '42':'B', '43':'C', '44':'D', '45':'E', '53':'analog'})
_setp_gain_req = bidict({'46':'A', '47':'B', '48':'C', '49':'D', '50':'E', '54':'analog'})
_setp_proc_lmt_relays = bidict({'1':'lowPL1', '2':'highPL1', '3':'lowPL2', '4':'highPL2'})
_setp_proc_lmt_relays_req = bidict({'11':'lowPL1', '12':'highPL1', '13':'lowPL2', '14':'highPL2'})
_setp_mode = bidict({'0': 'Position', '1':'Pressure'})
_analog_setp_ranges = bidict({'0':'+-5', '1':'+-10'})
_setp_ctrl1 = bidict({'0':'analog', '1':'A', '2':'B', '3':'C', '4':'D', '5':'E', '6':'open', '7':'close', '8':'stop', '9':'learning'})

def _set_setp_mode(spoint, mode): 
    try: 
        s = _cmd_io('T'+_setp_ctrl_cmd[:spoint]+_setp_mode[:mode])
        return _setp_ctrl_resp[s[1]], _setp_mode[s[2]]
    except KeyError: return 'Setpoints are A|B|C|D|E|analog, modes are pressure|position. Given:'+spoint+mode
def _get_setp_mode(spoint):
    try: s = _cmd_io('R'+_setp_ctrl_req[:spoint])
    except KeyError: return 'Setpoints are A|B|C|D|E|analog. Given:'+spoint
    #return _setp_ctrl_resp[s[1]], _setp_mode[s[2]]
    return _setp_mode[s[2]]
def _set_analog_setp_range(v):
    if v not in ['5', '10']: return 'Analog setpoint ranges can be 5|10 V, given:'+v
    return _cmd_io('A'+_analog_setp_ranges[:'+-'+v])
def _get_analog_setp_range(): 
    s = _cmd_io('R24')
    return _analog_setp_ranges[s[1]]
def _set_setp_value(spoint, v):
    f = float(v)
    try: s = _setp_ctrl1[:spoint]
    except KeyError: return 'Setpoint should be A|B|C|D|E|analog, value should be 0<x<100. Given:'+spoint+v
    if s==6 and int(f) not in [0, 1]: return 'Value for analog setpoint should be 0|1, given:'+v
    elif not 0 <= f <= 100: return 'Value for setpoints should be 0<=x<=100, given:'+v
    s1 = _cmd_io('S'+s+repr(f))
    #return _setp_ctrl_resp[s1[1]], s1[2:]
    return float(s1[2:])
def _get_setp_value(spoint):
    d = bidict({'0':'analog', '1':'A', '2':'B', '3':'C', '4':'D', '10':'E'})
    try: s = _cmd_io('R'+d[:spoint])
    except KeyError: return 'Setpoint should be A|B|C|D|E|analog, given:'+spoint
    #return _setp_ctrl_resp[s[1]], s[2:]
    return float(s[2:])
def _set_setp_gain(spoint, g):
    i = int(g)
    try: s = _setp_ctrl1[:spoint]
    except KeyError: return 'Setpoint should be A|B|C|D|E|analog, value should be 0<x<32767, given:'+spoint+g
    if not 1 <= i <= 32767: return 'Value for setpoint gain should be 0<=x<=32767, given:'+g
    s1 = _cmd_io('M'+s+repr(i))
    #return _setp_ctrl_resp[s1[1]], s1[2:]
    return float(s1[2:])
def _get_setp_gain(spoint):
    try: s = _cmd_io('R'+_setp_gain_req[:spoint])
    except: return 'Setpoint should be A|B|C|D|E|analog, given:'+spoint
    #return _setp_ctrl_resp[s[1]], s[2:]
    return float(s[2:])
def _set_gain_compenstation_factor(v): pass # not implemented yet
def _set_setp_phase(spoint, p): 
    i = int(p)
    try: s = _setp_ctrl1[:spoint]
    except KeyError: return 'Setpoint should be A|B|C|D|E|analog, value should be 0<x<32767, given:'+spoint+p
    if not 1 <= i <= 32767: return 'Value for setpoint phase should be 0<=x<=32767, given:'+p
    s1 = _cmd_io('X'+s+repr(i))
    #return _setp_ctrl_resp[s1[1]], s1[2:]
    return float(s1[2:])
def _get_setp_phase(spoint):
    try: s = _cmd_io('R'+_setp_phase_req[:spoint])
    except KeyError: return 'Setpoint should be A|B|C|D|E|analog, given:'+spoint
    #return _setp_ctrl_resp[s[1]], s[2:]
    return float(s[2:])
def _set_phase_compenstation_factor(v): pass
def _set_softstart_rate(spoint, v):
    f = float(v)
    try: s = _setp_ctrl1[:spoint]
    except KeyError: return 'Setpoint should be A|B|C|D|E|analog|open|close, value should be 0.1<=x<=100, given:'+spoint+v
    if not 0.1 <= f <= 100.0: return 'Value for setpoint softstart should be 0.1<=x<=100, given:'+v
    s1 = _cmd_io('I'+s+repr(f))
    #return _setp_ctrl_resp[s1[1]], s1[2:]
    return float(s1[2:])
_setp_softstart_req = bidict({'15':'A', '16':'B', '17':'C', '18':'D', '19':'E', '20':'analog', '21':'open', '22':'close'})
def _get_softstart_rate(spoint):
    try: s = _cmd_io('R'+_setp_softstart_req[:spoint])
    except KeyError: return 'Setpoint should be A|B|C|D|E|analog|open|close, given:'+spoint
    #return _setp_ctrl_resp[s[1]], s[2:]
    return float(s[2:])
def _get_setp_values(s, brief=True):
    if brief: return [_get_setp_mode(s), _get_setp_value(s), _get_softstart_rate(s)]
    else: return [_get_setp_mode(s), _get_setp_value(s), _get_softstart_rate(s),\
            _get_setp_gain(s), _get_setp_phase(s)]
def _set_setp_values(s, v, brief=True):
    if brief: return [_set_setp_mode(s, v[0]), _set_setp_value(s, v[1]), _set_softstart_rate(s, v[2])]
    else: return [_set_setp_mode(s, v[0]), _set_setp_value(s, v[1]), _set_softstart_rate(s, v[2]),\
            _set_setp_gain(s, v[3]), _set_setp_phase(s, v[4])]
def _activate_setp(spoint):
    try: return _cmd_io('D'+_setp_ctrl_resp[:spoint])[1]
    except: return 'Setpoints are A|B|C|D|E|analog. Given:'+spoint
# to get active setpoint, use get_valve_state

#def sensor_zero(): _cmd_io('Z1'); return recv()
#def special_zero(): _cmd_io('Z2'); return recv()
#def remove_zeros(): _cmd_io('Z3'); return recv()

_slowpump_conds = bidict({'0':'disable', '1':'both', '2':'dec', '3':'inc'})
# gentle pump in torr/s.
# not sure what the recipenum in the documents mean. Hopefully following
# interpretation is correct.
def _set_slowpump_pressure(v, recipenum=_slowpump_conds[:'both']):
    # the pressure in % of high pressure sensor.
    f = float(v)
    if not 0 <= f <= 100: return 'FS range should be between 0 and 100, got:'+repr(v) 
    return _cmd_io('S%c%.1f'%(recipenum, f))[2:]
def _set_slowpump_rate(v):
    f = float(v)
    if f <= 0: return 'Rate (Torr/s) should be >0, got:'+repr(v)
    return _cmd_io('SR%.1f'%(f))[2:]
def _get_slowpump_rate(): s = _cmd_io('RSR'); return s[2:]
def _set_slowpump_enable(c): 
    try: return _slowpump_conds[_cmd_io('SE'+_slowpump_conds[:c])[2]]
    except KeyError: return 'Slowpump condition should be disable|inc|dec|both, given:'+c
def _get_slowpump_enable(): return _slowpump_conds[_cmd_io('RSE')[2]]

def _get_valve_pressure(actv_ch, h_range, l_range):
    v1 = _cmd_io('R5')
    for i in range(len(v1)):
        if v1[i] == 'P': break
    v = float(v1[i+1:])
    if actv_ch == 'H': return 0.01*v*h_range
    return 0.01*v*l_range
def _get_valve_position(): return float(_cmd_io('R6')[1:])
def _get_encoder(): return _cmd_io('REN')[2:]  # how is encoder different than valve position?
def _get_interlock(): return _cmd_io('RIN')[2]


_mode = {'0':'local', '1':'remote'}
_learn_state = {'0':'not learning', '2':'learning'}
_valve_ctrl = {'0':'open', '1':'close', '2':'stop', '3':'A', '4':'B',\
        '5':'C', '6':'D', '7':'E', '8':'analog'}
def _get_cntrl_state():
    s = _cmd_io('R37')
    return {'Mode': _mode[s[1]], 'Learn': _learn_state[s[2]], 'Valve': _valve_ctrl[s[3]]}
def _get_version(): return {'Firmware Ver':_cmd_io('R38'), 'Build': _cmd_io('R66')}
_cksum_ok = {'0': 'OK', '1': 'Error'}
def _get_cksum(): return _cksum_ok[_cmd_io('R52')[2]]


# Backfill feature: when pressure is changing to a new setpoint, the backfill
# signal can be generated on one of the I/O pins to activate a pneumatic valve,
# to help in changing pressure.
# Pressure limit (for stopping this feature), pressure threshold (at which point
# it activates) and delay can be changed. We don't use this feature, although
# this can be connected to valve at the pump.

# Learn the system feature: the valve can learn pumping speed curve for the system
# and use it in better control. This is called "Model based control". 

