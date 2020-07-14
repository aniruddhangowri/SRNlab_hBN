"""
Overview of Labjack module
--------------------------------------------------------------------------------------------------------------
03/07/2020 - Overview created

The primary goal of the labjack module is to provide an interface to Labjack devices and peripherials connected
thereof. 
Peripherials connected to Labjack are either solenoid valves (sw) which use DIO ports or MKS Mass-Flow-controllers
(MFC) which are analog devices and require an analog output and input ports.
Please refer to reactor schematic and connection schematic for more info on how connections are established.
Essentially, all digital IO are handled by Labjack U3 and all analog communication are handled by Labjack U6.
Please refer U3 and U6 datasheets from Labjack website for detailed information.
Analog outputs in U6 are limited to two ports DAC1 and DAC2. Therefore, LJTick-DAC accessory was used to increase
analog output ports to 10 + 2 (in-built).
Each LJTick-DAC has 4 pins which connects to two DIO ports (one for SCL and one for SDA) the rest connected
to Vs and GND.
Each LJTick-DAC has two analog output ports DACA and DACB which can be independently controlled.
Once again, please refer LJTick-DAC datasheet available from Labjack website.
Communication to LJTick-DAC is mediated by U6 through I2C communication protocol.

If you would like a vivid understanding, think of LJTick-DAC as an external black-box to which you are communicating
through U6 using the DIO ports. This understanding will be essential later on.

For each MFC connected using LJTick-DAC (connected to some specific DIO on U6) the output will be one 
of DACA or DACB. The analog input from MFC will be connected to any AIN port as part of U6. Therefore, for
every MFC connected through LJTick-DAC, there will be a DIO_pin, aio_out and aio_in as defined in devconfig.
If the MFC is just connected through the built-in analog output, there will be only an aio_out and aio_in.

All sw's are connected to U3 using the PS12DC module which is connected to the DB15 connector on U3.
You should refer the U3 datasheet for pin information on the DB15.
Additionally, it has to be noted that the ports FIO and EIO in U3 are flexible IO ports. It means that they can 
be configured to be a digital IO port or an analog IN port. 
As of this documentation, the analog output ports DAC0 and DAC1 on U3 are not assigned.

If you intend to modify any of the script, please update this section with date and the modification carried out.
and a humble advice.... If it ain't broke, don't fix it.


"""




def funcmap(devname, devid):
    if devid[0]=='AIO':
        m = analog_mfc(devname, devid[1], devid[2], devid[3])
        c = {'init_state': m.init_state, 'get_flow': m.get_flow, 'set_flow': m.set_flow, 
                'get_curr_setp': m.get_curr_setp, 'get_fs_range': m.get_fs_range, 'handle': m}
        """ devid[1] - Labjack device key (for calling chan_d['port'])
            devid[2] - aio_in pin
            devid[3] - aio_out pin """
        return c
    if devid[0]=='AIO-DAC':
        m = LJTickDAC(devname, devid[1], devid[2], devid[3], devid[4])
        c = {'init_state': m.init_state, 'get_flow': m.get_flow, 'set_flow': m.set_flow, 
                'get_curr_setp': m.get_curr_setp, 'get_fs_range': m.get_fs_range, 'handle': m}
        """ devid[1] - Labjack device key (for calling chan_d['port'])
            devid[2] - dio_pin to which SCL pin of LJTick-DAC is connected
            devid[3] - aio_in pin
            devid[4] - aio_out (A or B) """
        return c
    if devid[0]=='DIO':
        sw = Switch(devname, devid[1], devid[2])
        c = {'init_state': sw.init_state, 'get_state': sw.get_state, 'set_state': sw.set_state, 
                'set_def_state': sw.set_def_state, 'handle': sw }
        """ devid[1] - Labjack device key (for calling chan_d['port'])
            devid[2] - dio pin """
        return c


import threading
import u6
import u3
# below LabJackException is handled only for initializing the lj handle.
# This exception was occurring when there was a spike in powerline, and
# the U6() handle became invalid due to that.
#

chan_d = {'U3':{'lock':threading.RLock(),'port':None}, 'U6':{'lock':threading.RLock(),'port':None}}

#chan_d = {'lock': threading.RLock(), 'port': {}} >>>>>>> Modified on 14-Jul-20
"""chan_d has been modified to hold two seperate threading-Rlocks, one for each Labjack devices.
The new structure is a dictionary with the Labjack device identifier as the key whose value is another dictionary
with a thread lock and corresponding device object as initialized in the routing init_comm() below.
Thus chan_d enables interfacing multiple Labjack devices on seperate threads.
In the future if the need arises to interface more than two Labjack device, then chan_d would just need a new 
dictionary entry correesponding to it.
Modifications to the code inside the classes have been made accordingly to reflect the structural changes."""


#module = {'U3':u3,'U6':u6}
## Module is for the explicit purpose of LabjackException handling.
## LabjackException is a class defined in LabjackPython module which is turn inherits the exception class.
## U6 module has imported the LabjackException from LabjackPython and does not seem to have added to or modified it.
# Therefore, it should not cause a problem when called from U6 or U3. However, if it causes problems, then
# there might be a need to call LabjackException specifically from corresponding module.


def init_comm():
    global chan_d
    chan_d['U6']['port'] = u6.U6()
    chan_d['U3']['port'] = u3.U3()
    chan_d['U3']['port'].configU3(FIOAnalog=0,EIOAnalog=0,FIODirection=0,EIODirection=0)
    """ We assume that U3 houses all the switches using a PS12DC. Therefore all the flexible IO lines (FIO and EIO)
     need to be configured to be digital.
     The arguments Analog and Direction are binary encoded 8-bit values with each bit corresponding to a an 
     individual port.
     U3 class provides an in-built routine "configU3" which can be used for this purpose.
     For example, if we need to configure just FIO2 and FIO5 to be analog inputs with the rest being Digital IO.
     This would correspond to a binary string, '01001000' whose integer value is 72. 
     Therefore, FIOAnalog=72 should be passed on as the argument.
     One can imagine the arguments FIOAnalog, EIOAnalog, FIODirection and EIODirection to be like registers.
     In this case, we require all the IO's to be Digital outputs hence the value 0 for all the arguments.
      """

""" init_comm initializes the dictionary chan_d with a thread-Rlock for each Labjack device and the corresponding
    device object as a seperate dictionary. 
    It is assumed here that there are is only one U6 and U3 device connected. The code u6.U6() and u3.U3() assume
    OpenFirstFound argument to be TRUE. Refer the U6.py or U3.py official module for better understanding.
    If multiple U6's are connected for example, then the routine "OpenALlU6" can be used which itself would return
    a dictionary. """

""" If there are a tandem of devices that are connected, then one has to look at specific functions present in each
    corresponding device library, or the function "listALL" present in LabjackPython module can be used.
    Here chan_d['port'] is a global handle and accessed by all the class instances. Implementing multiple 
    labjack devices would require specifying the handle inside of the class definition itself. """

from bidict import bidict
class Switch():
    name, num = None, None
    def_st, curr_st = 'noflow', None
    _onoff = bidict({'noflow':0, 'flow':1})

    def __init__(self, name, LJdev, dio_num):
        self.name = name
        self.dev=LJdev
        """ Created a new variable which will hold the device object key to which it is connected
        Using the key in chan_d should return the corresponding device objects along with a thread lock
        The lock and the device objects are accessible through chan_d[self.dev]['lock'] and chan_d[self.dev]['port']
        respectively. """
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
        with chan_d[self.dev]['lock']:
            try: r = chan_d[self.dev]['port'].getDIOState(self.num)
            except u6.LabJackException: init_comm()
        print (r)
        # Not sure where this gets printed??
        self.curr_st = self._onoff[:r]
        return 'OK', [self.curr_st]

    def set_state(self, args):
        st = args[0]
        if st not in self._onoff.keys() : return 'Error', ['Invalid requested state: '+st]
        #if st == self.curr_st: return 'OK', [st] # do it anyway for now.
        with chan_d[self.dev]['lock']:
            #try: r = chan_d[self.dev]['port'].setDIOState(self.num, self._onoff[st]) //Unused variable r warning
            try: chan_d[self.dev]['port'].setDIOState(self.num, self._onoff[st])
            except u6.LabJackException: init_comm()
        self.curr_st = st
        return 'OK', [st]

    # Function to reset to default state.    
    def set_def_state(self, args):
        with chan_d[self.dev]['lock']:
            #try: r = chan_d[self.dev]['port'].setDIOState(self.num, self._onoff[self.def_st]) /// Unused variable warning
            try: chan_d[self.dev]['port'].setDIOState(self.num, self._onoff[self.def_st])
            except u6.LabJackException: init_comm()
        self.curr_st = self.def_st
        return 'OK', [self.def_st]


# setup for read/write of analog channels
# see help(u6.AIN24) for explanation.
_gain_index = 0 # 1X
## Gain sets the range for the AIN.
## Gain values of x1, x10, x100 and x1000 correspond to ranges +-10, +-1, +-0.1 and +-0.01V respectively.
_res_index = 1 # high speed ADC
## Resolution index as the name suggests is an index to quantify the voltage resolution.
## Higher the Resolution index higher the voltage resolution, lower the noise at the cost of increased sample times

_settling_factor = 0 # auto 
## The settling registers set the time from a step change in the input signal to when the signal is sampled
## by the ADC, as measured in us. In general, more settling time is required as gain and resolution are increased
## "Auto" settling ensures that the device meets specifications at any gain and resolution.
_differential_inp = False 
# Specifies if the reference voltage is w.r.t ground (False) or w.r.t another AIN
# We measure w.r.t. gnd, which is also common to the setpoint voltage (through DACs)


################################################################################################
_ranges = [20, 2, 0.2, 0.02]
_strranges = ['+- 10V', '+- 1V', '+- 0.1V', '+- 0.01V']
## These two variables are not referenced anywhere else on this scipt. Unsure of their role.
###################################################################################################

def _get_AIN(board, ain_num):
    #res = board.getFeedback(u6.AIN24(ain_num, _res_index, _gain_index, _settling_factor, _differential_inp))
    #return board.binaryToCalibratedAnalogVoltage(_gain_index, res[0])
    # following is same as above two lines.
    try: return board.getAIN(ain_num, _res_index, _gain_index, _settling_factor, _differential_inp)
    except u6.LabJackException:
        init_comm()
        return 0.0

## function getFeedback is a function that is part of class U6 (and probably also present in other Labjac devices)
## Essentially getFeedback accepts a commandlist and sends to the respective board and returs with the response
## getAIN also uses getFeedback to communicate with the device (U6) using the "AIN24AR" module.
## This function essentially sets the parameters set earlier to be used by the Analog input port.
## For any analog input from a MFC (for example) connected to an AIN port, this function is executed inside
## "analog_mfc" class to read data from the MFC.

def _set_DAC_output(board, dac_num, volts):
    # scale volts to bits:
    if dac_num == 0: bits = int(board.calInfo.dac0Slope*volts + board.calInfo.dac0Offset)
    elif dac_num == 1: bits = int(board.calInfo.dac1Slope*volts + board.calInfo.dac1Offset)
    try: board.getFeedback(u6.DAC16(dac_num, bits))
    except u6.LabJackException: init_comm()

""" _set_DAC_output is used inside analog_mfc class to set a voltage to one of two DACs
    Function can be incorporated into analog_mfc class itself. Need to confirm if there might be any issues """

class analog_mfc():
    name,dev,in_id,out_id = None, None, None, None
    max_volt = 5.0 # depends on MFC's analog input range, normally 5.0 V.
    fs_range, curr_setp, actv_flow = None, 0.0, 0.0
    
    def __init__(self, name, LJdev, aio_in, aio_out):
        self.name = name
        self.dev=LJdev
        ## Created a new variable which will hold the device object key (which is a string) to which it is connected
        ## Using the key in chan_d['port'] should return the corresponding device objects
        self.in_id, self.out_id = aio_in, aio_out
        chan_d[self.dev]['port'].getCalibrationData()
    
    def init_state(self, args): #fs_range, initial_setp):
        self.fs_range, self.curr_setp = args['fs_range'], args['init_val']
        self.set_flow([self.curr_setp])
        self.get_flow([])
    def _volt2sccm(self, v):
        return (v*self.fs_range)/self.max_volt
    def _sccm2volt(self, s):
        return (s*self.max_volt)/self.fs_range

    def get_flow(self, args):
        with chan_d[self.dev]['lock']:
            try: r = _get_AIN(chan_d[self.dev]['port'], self.in_id)
            except u6.LabJackException: init_comm()
        # Modified this routine to handle LabjackException
        self.actv_flow = self._volt2sccm(r)
        return 'OK', ['%.3f'%(self.actv_flow)]
    
    def set_flow(self, args):
        s = float(args[0])
        if 0 <= s <= self.fs_range:
            with chan_d[self.dev]['lock']:
                _set_DAC_output(chan_d[self.dev]['port'], self.out_id, self._sccm2volt(s))
            self.curr_setp = s
            return 'OK', [repr(s)]
        else: return 'Error', ['Flow is beyond range(0, %f'%(self.fs_range)+'): '+args[0]]
    
    def get_curr_setp(self, args):
        return 'OK', [repr(self.curr_setp)]
    
    def get_fs_range(self, args):
        return 'OK', [repr(self.fs_range)]


""" Some Analog MFC's are connected to directly to an Analog IO port on U6, while some are connected through LJTIckDAC
Devconfig file will be updated with the corresponding device to which the MFCs will be connected.
A separate labjack device will house all the switches.
Existing communication to the U6 board is through the getFeedback routine which calls the "_WriteRead" routine
in LabjackPython.
However, LJTick-DACs hasn been configured to use i2C protocol using the i2c routine as part of U6 
The program host communicates with U6 via USB and U6 in turn communicates to LJTick-DAC using i2C.
As per the datasheet, i2c in U6 is an exclusive master only implementation.
Therefore, there should not be any issues with communicating using i2c."""

import struct

""" Each LJTick has two output analog ports. Therefore for each LJTick, we will have two MFC connected to each 
 of the output.
 The output from the MFC will connected to one of the AIN ports of U6 itself. Therefore, class LJTickDAC
 also inherits class analog_mfc.
 Only the set_flow routine will be modified as a polymorph.
 Communication to the DAC is mediated by U6 through i2c protocol"""

""" class LJTickDAC has been adapted from the LJTickDAC.py example from the official labjackpython github repo.
 Yeah.... I know it's lame."""

class LJTickDAC(analog_mfc):
    """Class to control LJTick-DAC outputs connected to a Labjack device"""
    EEPROM_ADDRESS = 0x50
    DAC_ADDRESS = 0x12
    DAC_Out = {'A':48,'B':49}
    # Dictionary to distinguish output channels DACA and DACB. The values corresponding are not clear,
    # but are used in the i2c statement. Therefore it has been set as the out_id.
    def __init__(self, name, LJdev, dioPin, aio_in, aio_out):
        """LJdev corresponds to key of a Labjack device"""
        super().__init__(name, LJdev, aio_in, self.DAC_Out[aio_out])
        ## Using the analog_mfc init function to initialize the necessary fields
 
        # The pin numbers for the I2C command-response
        self.sclPin = dioPin
        self.sdaPin = self.sclPin + 1

        self.getCalConstants(aio_out)


    def toDouble(self, buff):
        """Converts the 8 byte array into a floating point number.
        buff: An array with 8 bytes.

        """
        right, left = struct.unpack("<Ii", struct.pack("B" * 8, *buff[0:8]))
        return float(left) + float(right)/(2**32)

    def getCalConstants(self,aio_out):
        """Loads or reloads the calibration constants for the LJTick-DAC.
        See datasheet for more info.

        """
        data = chan_d[self.dev]['port'].i2c(LJTickDAC.EEPROM_ADDRESS, [64],
                               NumI2CBytesToReceive=36, SDAPinNum=self.sdaPin,
                               SCLPinNum=self.sclPin)
        response = data['I2CBytes']

        if aio_out=='A':
            self.slope = self.toDouble(response[0:8])
            self.offset = self.toDouble(response[8:16])
        elif aio_out=='B':
            self.slope = self.toDouble(response[16:24])
            self.offset = self.toDouble(response[24:32])
        else:
            msg=f"Wrong analog output port specified on LJTick-DAC for device {self.name}.\
             Please modify the appropriate field in devconfig"
            raise Exception(msg)

        if 255 in response:
            msg = "LJTick-DAC calibration constants seem off. Check that the " \
                  "LJTick-DAC is connected properly."
            raise Exception(msg)

        ## calibration data stored only for corresponding channel.

    def dacupdate(self, volt):
        """Updates the voltages on the LJTick-DAC.

        """
        binaryA = int(volt*self.slope + self.offset)

        with chan_d[self.dev]['lock']:
            try: chan_d[self.dev]['port'].i2c(LJTickDAC.DAC_ADDRESS,
                        [self.out_id, binaryA // 256, binaryA % 256],
                        SDAPinNum=self.sdaPin, SCLPinNum=self.sclPin)
            except u6.LabJackException: init_comm()


    """ With the lock secured, communiation to the corresponding DAC is initiated. This is essential since
        LJTick-DAC can only update one of the outputs at any given time.
        Voltage values will be supplied from the set_flow routine.
        set_flow will be defined inside LJTickDAC class as a polymorph.
        Exception handling has been implemented here to ensure there isn't any errors. """

    def set_flow(self, args):
        s=float(args[0])
        if 0 <= s <= self.fs_range:
            self.dacupdate(self._sccm2volt(s))
            self.curr_setp = s
            return 'OK', [repr(s)]
        else: return 'Error', ['Flow is beyond range(0, %f'%(self.fs_range)+'): '+args[0]]

    """ set_flow routine defined in LJTickDAC will essentially call the update function, passing along the
        voltage as an argument. """

#============================================================================================================================






"""

"""
