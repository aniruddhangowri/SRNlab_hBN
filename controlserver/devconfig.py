# this is a map of how devices are attached to channels.
#
# In a control system there will be many hardware channels (e.g.
# RS-232, RS-485, Ethernet, USB buses etc.). On each of those
# channels there can be multiple devices which are identified by
# a number or a tag. For example ethernet can be connected to 
# many devices which are identified by their IP addresses. We
# bundle all the code related to one hardware channel in one
# module and provide a map to functions of each of devices that
# channel has. This way, all channel specific code is in one
# place (example: channel init code), and locking of channel 
# can be done inside the module itself (when multiple clients
# are sending requests for the devices at the same time).
#
# In our case, throttle valve controller (tvc) occupies RS-232
# line, two GF40 MFCs occupy RS-485 bus, switches and MKS1179 MFC
# are on labjack. The identification numbers are according to
# hardware/device configuration.
#
# In following: map= { devname: [channelname, idnumber] .. }

_tvc = {
    'conn': 'rs232', 'devid': ['tvc'], 
    'init_params': {
        'manual-setp': 'Close', # this is the initial state
        'setpoints': [# name, mode, val, softstartval
            ['A', 'Position', 100.0, 100.0],
            ['B', 'Pressure', 100.0, 100.0],
            ['C', 'Position', 100.0, 100.0],
            ['D', 'Position', 100.0, 100.0],
            ['E', 'Position', 0.0, 100.0]
            # don't know how to use analog setpoint, so not listed here.
            ],
        'actv_setpoint': 'manual', # can be manual or A/B/C/D/E from above.
        'slowpump': {'state': 'both', 'rate': 20.0, 'pressure': 0.0},
        'fallback_state': 'Close',
        # high and low gauge ranges and auto crossover parameters can also
        # be set here. Needed only when you are changing gauges. See the init_params
        # function of tvc class in rs232.py file.
        # Currently it is set to 1000 Torr, 1 Torr, 100 msec xover delay, 0.1%
        # of high sensor xover point and 100% of low sensor xover point.
        'reset_sensor_range': False, # make this true to set the following ranges.
        'high_sensor_fs_range': 1000, 'low_sensor_fs_range': 1
        # 1000 torr and 10 torr are default ranges.
        }
    }

#_mfc_ch4_1 = {'conn':'rs485', 'devid':32, 'init_params': {'fs_range': 92.0, 'init_val': 0.0}}
_mfc_ch4_2 = {'conn':'rs485', 'devid':33, 'init_params': {'fs_range': 10.0, 'init_val': 0.0}}

# this is MKS analog MFC (1179). One more annlog MFC can use devid:[3:1]
# For more analog MFCs, there are two LJTick-DAC in reserve. These can fit
# on FIO0-1 block and FIO2-3 block to give ~4 more 14 bit analog DACs.
# This reduces the number of DIO lines to 16 from total available 20.
# The DIO lines are used to control pneumatic switches, so number of switches
# that can be controlled is reduced in that case. 


# In the case of multiple Labjacks, we may need additional identifiers for distinguishing
# Since the connection protocol for Labjack is the same, we can continue to use the same library
# However, we would need to distinguish between the two Labjacks. This can be added to the devid list
# but it needs to be ascertained that it does not cause compatibility issues in the code
# From the outset, it does not seem to be the case.


_mfc_h2_2 = {'conn':'labjack', 'devid':['AIO', 3, 1], 'init_params': {'fs_range': 2000.0, 'init_val': 0.0}}
_mfc_h2_1 = {'conn':'labjack', 'devid':['AIO', 2, 0], 'init_params': {'fs_range': 2000.0, 'init_val': 0.0}}

_mfc_n2_1 = {'conn':'rs232', 'devid':['mfc-n2-1'], 'init_params': {'fs_range': 50.0, 'init_val': 1.0}}

# On the relay board which controls the switches, there are 12 switches which
# controlled by EIO/CIO (8/4) lines. EIO are addressed as digital I/O bits 8 
# through 15, and the CIO are addressed as bits 16-19. These lines are mapped
# to the pneumatic switches:
# Switch name: pneum. switch number: switchboard sw num: DIO line address:
# before-inlet: 1: 9: 17
# ch4-1-by: 2: 8: 16
# ch4-2-by: 3: 7: 15
# h2-1-by: 4: 6: 14
# ch4-1-in: 5: 5: 13
# ch4-2-by: 6: 4: 12
# h2-1-by: 7: 3: 11
# before-pump: 8: 2: 10
# ventline: 9: 1: 09
# n2-1-by: 10: 0: 08
# There are 2 more switch positions vacant on the switchboard. More switches
# can be obtained by purchasing another Labjack PS12DC switchboard and driving
# it using an Arduino (see PS12DC webpage). Of course, another pneumatic switch
# row is needed.

# the devid is the DIO address number. Default is the default state of the
# switch (normally open or normall closed), we denote these by "flow" and "noflow".
# For BY-series switches, "noflow" is actually diverting the flow to another
# line. flow/noflow are mapped to 0,1 according to default state. 0 is always
# equal to default state.
_sw_before_inlet = {'conn':'labjack', 'devid':['DIO', 17], 'init_params': {'default': 'noflow', 'init_val':'noflow'}}
_sw_ch4_1_by = {'conn':'labjack', 'devid':['DIO', 16], 'init_params': {'default': 'noflow', 'init_val':'noflow'}}
_sw_ch4_2_by = {'conn':'labjack', 'devid':['DIO', 15], 'init_params': {'default': 'noflow', 'init_val':'noflow'}}
_sw_h2_1_by = {'conn':'labjack', 'devid':['DIO', 14], 'init_params': {'default': 'noflow', 'init_val':'noflow'}}
_sw_ch4_1_in = {'conn':'labjack', 'devid':['DIO', 12], 'init_params': {'default': 'noflow', 'init_val':'noflow'}}
_sw_ch4_2_in = {'conn':'labjack', 'devid':['DIO', 13], 'init_params': {'default': 'noflow', 'init_val':'noflow'}}
_sw_h2_1_in = {'conn':'labjack', 'devid':['DIO', 11], 'init_params': {'default': 'noflow', 'init_val':'noflow'}}
_sw_before_pump = {'conn':'labjack', 'devid':['DIO', 10], 'init_params': {'default': 'noflow', 'init_val':'noflow'}}
_sw_ventline = {'conn':'labjack', 'devid':['DIO', 9], 'init_params': {'default': 'noflow', 'init_val':'noflow'}}
_sw_n2_1_by = {'conn':'labjack', 'devid':['DIO', 8], 'init_params': {'default': 'noflow', 'init_val':'noflow'}}

devlist = { 'tvc':_tvc,\
        'mfc-h2-2':_mfc_h2_2, 'mfc-ch4-2':_mfc_ch4_2,\
        'mfc-h2-1':_mfc_h2_1, 'mfc-n2-1':_mfc_n2_1, 
        'sw-before-pump':_sw_before_pump,\
        'sw-before-inlet':_sw_before_inlet, 'sw-ch4-1-in':_sw_ch4_1_in,\
        'sw-ch4-1-by':_sw_ch4_1_by, 'sw-ch4-2-in':_sw_ch4_2_in,\
        'sw-ch4-2-by':_sw_ch4_2_by, 'sw-h2-1-in':_sw_h2_1_in,\
        'sw-h2-1-by':_sw_h2_1_by, 'sw-ventline':_sw_ventline,\
        'sw-n2-1-by':_sw_n2_1_by}
def gen_init_js():
    print 'function init_state() {'
    for d,p in devlist.iteritems():
        if d=='tvc':
            if p['init_params']['manual-setp'] == 'Close': print "$(\"#tvc-close\").prop(\'checked\', true);"
            else: print "$(\"#tvc-open\").prop(\'checked\', true);"
            for s in p['init_params']['setpoints']:
                print "$(\"#setp-%c\").prop(\'checked\', false);"%(s[0])
                print "$(\"#setp%c-val\").val(\"%f\");"%(s[0], s[2])
                print "$(\"#setp%c-mode\").val(\"%s\");"%(s[0], s[1])
        if d[:2]=='sw': # switches
            if p['init_params']['init_val']=='flow': print "$(\"#b-%s\").text(flow_arrow);"%(d[3:])
            else: print "$(\"#b-%s\").text(noflow_cross);"%(d[3:])
        if d[:3]=='mfc': # mfcs
            print "$(\"#%s-mfc-name\").text(\"%s(%f)\");"%(d[4:], d[4:], p['init_params']['fs_range'])
            print "$(\"#%s-mfc\").val(\"%f\");"%(d[4:], p['init_params']['init_val'])
    print '}'
    print 'init_state();'


