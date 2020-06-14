import sys
import json
from string import strip, split
import datetime
import pickle
import numpy as np
from collections import defaultdict
import os

# change this to whereever the data is stored, e.g. datadir = './log/'
datadir = '../controlserver/log/'

try:
    logview = open('../controlserver/logview.txt')
    logview.seek(0, 2)
except:
    pass


# this pickles the log files (i.e. converts the json format to python json
# objects) for faster loading when analysing the data. It also removes some
# not so useful information (so that the data reduces to 1/4th size). The
# retained data is: time (starts at 0), tvc pressure and all mfc flows.
# The resulting files have '.processed' appeneded in filenames.
# Filesize can be reduced 10 times further with compression (not done here
# at the moment).
def _pickle_logfiles(fnames):
    flowdict = {'flow': 1, 'noflow':0}
    devdict = defaultdict(list)
    for f in fnames:
        logfile = open(f);

        t0 = None
        for l in logfile:
            if l=='\n': continue
            i1, i2 = l.find(')'), l.find('[')
            if i2==-1: continue
            ip, t, msg = l[:i1+1], strip(l[i1+2:i2-2]), l[i2:]
            try: s = json.loads(msg)
            except: pass
            t = datetime.datetime.strptime(t, '%Y-%m-%d %H:%M:%S,%f')
            #print ip, t, msg
            if t0==None: t0 = t
            tdiff = t-t0
            tsec = tdiff.seconds + tdiff.microseconds/1E6
            for d in s:
                if 'status' not in d: continue
                if d['status'] == 'Error': continue
                points = devdict[d['dev']]
                if d['dev'][:2] == 'sw':
                    points.append([tsec, flowdict[d['value'][0]]])
                if d['dev'][:3] == 'mfc':
                    if d['cmd'] == 'get_flow':
                        points.append([tsec, float(d['value'][0])])
                if d['dev'][:3] == 'tvc':
                    if d['cmd'][:9] == 'get_press':
                        press, pos = map(float, split(d['value'][0], ','))
                        points.append([tsec, press])
        devdict1 = {}
        for k, v in devdict.iteritems():
            devdict1[k] = np.array(v)
        pickle.dump(devdict1, open(f+'.processed', 'w+'))

# this is a wrapper for above function. Just checks all '.txt' files in
# log directory (except logview.txt) and converts them to processed.
# skips a file if it is already processed.
def _procfiles():
    global datadir
    txtfiles = [f for f in os.listdir(datadir) if f[-3:]=='txt']
    procedfiles = [f for f in os.listdir(datadir) if f[-9:]=='processed']
    for t in txtfiles:
        if t=='logview.txt': continue
        t1 = t+'.processed'
        if t1 not in procedfiles: 
            _pickle_logfiles([datadir+t])
            print 'processed:', t1

# this runs when program loads.
import threading
def background_proc():
    proc_thread = threading.Thread(target=_procfiles)
    proc_thread.start()
background_proc()

# this is used to load the processed files for analysis.
# used from get_view (see below).
_d, _fname = None, ''
def _loaddata(fname):
    global _d, _fname
    if _d == None or _fname != fname:
        _fname = fname
        _d = pickle.load(open(_fname))
    return _d

# _tail just returns last line of data. can be used to see the
# increments process from a webpage.
def _tail(f):
    #loc = f.tell()
    retlines = []
    for l in f.readlines():
        if 'status' in l:
            retlines.append('[{'+split(l, ': [{')[1])
    # we send only the latest data point.
    return retlines[-1]
    
# returns data for plotting. The 'data' argument should have following format (used from logs.html).
### {"cmd": "get_view", "args": {'fname':selectedfile, 'plots':["tvc"], 'plotname':"tvc", 'range':[range_lo, range_lo+range]}}, or
### {"cmd": "get_view", "args": {'fname':selectedfile, 'plots': ["mfc-ch4-1", "mfc-ch4-2", "mfc-h2-1", "mfc-n2-1"], 'plotname':"mfcs", 'range':[range_lo, range_lo+range]}} ]. For another example see get_textdata below.
# cmd can be get_view or single_view. get_view returns a range of points from the
# stored data, single_view only the most recent. Latter can be used for live viewing.
# selectedFile is the processed log file name, e.g. 'controllerlog.txt.processed'
# Range is the point number lo to point number hi, displaylen argument can be smaller than difference
# between the two, then some data is skipped to return on displaylen number of points.
# fmt can be 'json' or 'python'. The former is used from logs.html.
def get_plotdata(data, displaylen=100, fmt='json'): # fmt can be json or python
    global logview
    global datadir
    d = None
    if data['cmd']=='get_filelist':
        files = [f for f in os.listdir(datadir) if f[-9:]=='processed']
        data['args'] = files
        return json.dumps(data)
    if data['cmd']=='get_view':
        args = data['args']
        dstr = {}
        #args[0] is filename, [1] is list of devices, [2] is plot name
        lo, hi = map(int, args['range'])
        d = _loaddata(datadir+args['fname'])
        for i in range(len(args['plots'])):
            skip = 1
            ary = d[args['plots'][i]][lo:hi]
            #print len(ary), displaylen
            datnum = 1
            if len(ary) > displaylen: skip = int(len(ary)/displaylen)
            if len(ary) < displaylen: displaylen = len(ary)
            if fmt=='json': 
                dstr = ''
                dstr += "var dat%d = new Float32Array(%d); dat%d = ["%(i, displaylen, i)
                for j in range(displaylen): dstr += "[%f, %f], "%(ary[j*skip][0], ary[j*skip][datnum])
                dstr += "];"
            else: dstr[args['plots'][i]] = [[ary[j*skip][0], ary[j*skip][datnum]] for j in range(displaylen)]
        data['args']['dat'] = dstr
        if fmt=='python': return data
        return json.dumps(data)
    if data['cmd']=='get_single':
        return _tail(logview)

# When run on console, this yields requested data in tabular format (which can be directly fed to gnuplot)
# python ./readlog.py filename rangelo rangehi plots      (plots can be empty, then all fields are returned)
# e.g. python ./readlog.py krishnaa.txt.processed 0 10000 tvc mfc-ch4-1    (other fields are mfc-ch4-2, mfc-n2-1, mfc-h2-1)
# or python ./readlog.py krishnaa.txt.processed 0 10000
if __name__ == '__main__':
    fname = sys.argv[1]
    rangelo, rangehi = int(sys.argv[2]), int(sys.argv[3])
    what = sys.argv[4:] 
    if what == []: what=['tvc', 'mfc-ch4-1', 'mfc-ch4-2', 'mfc-h2-1', 'mfc-n2-1']
    cmddata = {"cmd": "get_view", "args": {'fname': fname, 'plots':what, 'range':[rangelo, rangehi]}}
    out = get_plotdata(cmddata, displaylen=rangehi-rangelo, fmt='python')['args']['dat']
    tab_data = []
    for k in out.keys():
        tab_data += [[k, out[k]]]
    datlen = len(tab_data[0][1])
    print '#Time(s)\t',
    for i in range(len(tab_data)): print tab_data[i][0]+'\t',
    print
    for j in range(datlen):
        print tab_data[0][1][j][0],'\t', 
        for i in range(len(tab_data)):
            print tab_data[i][1][j][1],'\t',
        print 


