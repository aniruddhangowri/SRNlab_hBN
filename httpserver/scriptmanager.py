from string import split, strip, join
from tempfile import NamedTemporaryFile
import json

def _validate(data):
    # nothing being done here for now. only comment removal.
    lines = [x for x in map(strip, split(data, '\n')) if x!='' and x[0]!='#' ]
    script = ''
    t0, t, d, c, a = None, None, None, None, None
    for l in lines:
        #print l
        t, others = l.split(' ', 1)
        t = int(t)
        if t0 == None: t0 = t
        t = str(t-t0)
        script += ' '.join([t, others])+'\n'
    return script

import os.path
script_format = """timestamp dev cmd args.
args can be empty. others cannot be. Timestamp is in milisecond"""
def _save_script(data):
    # parse data to a script and offer it for saving
    script = _validate(data)
    #print script
    f = NamedTemporaryFile(suffix='.txt', dir='./public/tmp-scripts/', delete=False)
    f.write(script)
    f.close()
    return '/static/tmp-scripts/'+os.path.basename(f.name)

def _convert_script(script, starttime=0):
    # comments are left as they are
    # recognises time format: hh:mm:ss.ms e.g. ::2.340
    # recognises time offsets +::5
    # can include other files (recursion is not tackled), a comment is added to show the inclusion.
    # return the cannonical format.
    lines = [x for x in map(strip, split(script, '\n')) if x!='' and x[0]!='#' ]
    canon = ''
    t_1, t0, t, d, c, a, addtime = starttime, 0, None, None, None, None, False
    for l in lines:
        t, others = l.split(' ', 1)
        if t[0]=='+': addtime, t = True, t[1:]
        h, m, s = t.split(':')
        if h=='': h=0
        else: h = int(h)
        if m=='': m=0
        else: m = int(m)
        s = float(s)
        s, ms = s//1, s%1
        t = int((h*3600 + m*60 + s + ms)*1000)
        if addtime: t = t_1 + t
        addtime = False
        t_1 = t
        t = str(t-t0)
        d, xothers = others.split(' ', 1)
        if d == 'call':
            subs_fname = strip(xothers) # this assumes that xothers has only the filename and nothing else.
            preamble, postscript = '# called the script:'+subs_fname+'\n', '# script:'+subs_fname+' ends here.\n'
            subscript = _convert_script(' '.join(open(subs_fname).readlines()), starttime=t_1)
            canon += ''.join([preamble, subscript, postscript])
        else: canon += ' '.join([t, others])+'\n'
    return canon

def process_req(data):
    #print data
    resp = []
    for d in data:
        if d['cmd'] == 'save':
            d['args'] = [_save_script(d['args'][0])]
            resp.append(d)
            return json.dumps(resp)
        if d['cmd'] == 'load':
            pass

import sys
# on commandline script in easy-write format is converted to canonical form, e.g. try
# python ./scriptmanager.py script1.txt
# where script1.txt contains:
#   0:0:2.2 dev cmd args args1
#    ::5.6 dev cmd a
#    +::1.0 dev cmd b
#    +::2.0 call script2.txt
#    ::10.0 dev cmd z
# and script2.txt contains:
#   +::1.3 this is script script2.txt
#    +::1.0 call c calling script c from script2.txt
if __name__ =='__main__':
    s = ' '.join(open(sys.argv[1]).readlines())
    print _convert_script(s)
