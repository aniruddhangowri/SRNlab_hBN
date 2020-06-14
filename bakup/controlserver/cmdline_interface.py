import sys
from string import split, strip
import json

import socket
cnt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
cnt.connect(('127.0.0.1', 9999))
cntfile = cnt.makefile()

while True:
    try:
        d = {}
        resp = ''
        l = split(strip(sys.stdin.readline()))
        if l[0] == 'END': break
        d = {'dev':l[0], 'cmd':l[1], 'args':None}
        if len(l)==2: d['args'] = [""]
        else: d['args'] = l[2:]
        cnt.send(json.dumps([d])+'\n')
        resp = cntfile.readline()
        d = json.loads(resp)
        for x in d:
            print x['status'], x['dev'], x['cmd'], x['value']
    except: print resp
