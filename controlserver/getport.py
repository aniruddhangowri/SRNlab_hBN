import serial

def _check_for_tvcport(portnames):
    _cmd_mod = '#'
    def _cmd_io(port, cmdstr, eps=50):
        res = ''
        port.write(_cmd_mod+cmdstr+'\n')
        if eps==0: return
        else: res = port.read(eps)[:-1]
        if len(res)==0: # time out occurred
            return None
        if res[0] != '0': return None
        return res[1:]

    build = '01.04.05  Nov 05 2008 17:29:52 VMD:02.00'
    for pn in portnames:
        port = serial.Serial(pn, timeout=0.05)
        b = _cmd_io(port, 'R66')
        if b==build: return pn
    return 'No port found'

def associate_ports():
    import glob
    ttyusbs = glob.glob('/dev/ttyUSB*')
    tvcport = _check_for_tvcport(ttyusbs)
    mfcn2port = [x for x in ttyusbs if x!=tvcport][0]
    return {'tvc': tvcport, 'mfc-n2-1': mfcn2port}

