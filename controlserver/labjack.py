def funcmap(devname, devid):
    if devid[0]=='AIO':
        m = analog_mfc(devname, devid[1], devid[2])
        c = {'init_state': m.init_state, 'get_flow': m.get_flow, 'set_flow': m.set_flow, 
                'get_curr_setp': m.get_curr_setp, 'get_fs_range': m.get_fs_range, 'handle': m}
        return c
    if devid[0]=='DIO':
        sw = Switch(devname, devid[1])
        c = {'init_state': sw.init_state, 'get_state': sw.get_state, 'set_state': sw.set_state, 
                'set_def_state': sw.set_def_state, 'handle': sw }
        return c


import threading
import u6
# below LabJackException is handled only for initializing the lj handle.
# This exception was occurring when there was a spike in powerline, and
# the U6() handle became invalid due to that.
#
chan_d = {'lock': threading.RLock(), 'port': None}
def init_comm():
    global chan_d
    chan_d['port'] = u6.U6()


from bidict import bidict
class Switch():
    name, num = None, None
    def_st, curr_st = 'noflow', None
    _onoff = bidict({'noflow':0, 'flow':1})

    def __init__(self, name, dio_num):
        self.name = name
        self.num = dio_num
    def init_state(self, args): #def_st, curr_st):
        if args['default'] == 'flow': 
            self.def_st = 'flow'
            self._onoff = bidict({'flow':0, 'noflow':1})
        c = args['init_val']
        if c != self.def_st:
            self.set_state(c)
        self.curr_st = c
    
    def get_state(self, args):
        with chan_d['lock']:
            try: r = chan_d['port'].getDIOState(self.num)
            except u6.LabJackException: init_comm()
        print r
        self.curr_st = self._onoff[:r]
        return 'OK', [self.curr_st]

    def set_state(self, args):
        st = args[0]
        if st not in self._onoff.keys(): return 'Error', ['Invalid requested state: '+st]
        #if st == self.curr_st: return 'OK', [st] # do it anyway for now.
        with chan_d['lock']:
            try: r = chan_d['port'].setDIOState(self.num, self._onoff[st])
            except u6.LabJackException: init_comm()
        self.curr_st = st
        return 'OK', [st]

    def set_def_state(self, args):
        with chan_d['lock']:
            try: r = chan_d['port'].setDIOState(self.num, self._onoff[self.def_st])
            except u6.LabJackException: init_comm()
        self.curr_st = self.def_st
        return 'OK', [self.def_st]


# setup for read/write of analog channels
# see help(u6.AIN24) for explanation.
_gain_index = 0 # 1X
_res_index = 1 # high speed ADC
_settling_factor = 0 # auto 
_differential_inp = False # since we measure w.r.t. gnd, which is also
# common to the setpoint voltage (through DACs)
_ranges = [20, 2, 0.2, 0.02]
_strranges = ['+- 10V', '+- 1V', '+- 0.1V', '+- 0.01V']

def _get_AIN(board, ain_num):
    #res = board.getFeedback(u6.AIN24(ain_num, _res_index, _gain_index, _settling_factor, _differential_inp))
    #return board.binaryToCalibratedAnalogVoltage(_gain_index, res[0])
    # following is same as above two lines.
    try: return board.getAIN(ain_num, _res_index, _gain_index, _settling_factor, _differential_inp)
    except u6.LabJackException:
        init_comm()
        return 0.0

def _set_DAC_output(board, dac_num, volts):
    # scale volts to bits:
    if dac_num == 0: bits = int(board.calInfo.dac0Slope*volts + board.calInfo.dac0Offset)
    elif dac_num == 1: bits = int(board.calInfo.dac1Slope*volts + board.calInfo.dac1Offset)
    try: board.getFeedback(u6.DAC16(dac_num, bits))
    except u6.LabJackException: init_comm()

class analog_mfc():
    name, in_id, out_id = None, None, None
    max_volt = 5.0 # depends on MFC's analog input range, normally 5.0 V.
    fs_range, curr_setp, actv_flow = None, 0.0, 0.0
    
    def __init__(self, name, aio_in, aio_out):
        self.name = name
        self.in_id, self.out_id = aio_in, aio_out
        chan_d['port'].getCalibrationData()
    
    def init_state(self, args): #fs_range, initial_setp):
        self.fs_range, self.curr_setp = args['fs_range'], args['init_val']
        self.set_flow([self.curr_setp])
        self.get_flow([])
    def _volt2sccm(self, v):
        return (v*self.fs_range)/self.max_volt
    def _sccm2volt(self, s):
        return (s*self.max_volt)/self.fs_range

    def get_flow(self, args):
        with chan_d['lock']:
            r = _get_AIN(chan_d['port'], self.in_id)
        self.actv_flow = self._volt2sccm(r)
        return 'OK', ['%.3f'%(self.actv_flow)]
    
    def set_flow(self, args):
        s = float(args[0])
        if 0 <= s <= self.fs_range:
            with chan_d['lock']:
                r = _set_DAC_output(chan_d['port'], self.out_id, self._sccm2volt(s))
            self.curr_setp = s
            return 'OK', [repr(s)]
        else: return 'Error', ['Flow is beyond range(0, %f'%(self.fs_range)+'): '+args[0]]
    
    def get_curr_setp(self, args):
        return 'OK', [repr(self.curr_setp)]
    
    def get_fs_range(self, args):
        return 'OK', [repr(self.fs_range)]



