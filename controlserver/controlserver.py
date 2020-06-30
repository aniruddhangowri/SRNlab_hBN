import logging
import SocketServer
import json
import threading
import os

logging.basicConfig(level=logging.DEBUG, format='%(name)s, %(asctime)s: %(message)s')
logdir = '../controlserver/log/'
default_logfile = logdir+'log_controlserver.txt'
default_logview = 'logview.txt' # this is the name of symlink.
#handler = logging.handlers.RotatingFileHandler(log_filename, maxBytes=10*1024*1024, backupCount=10)

def change_logfile(logger, f=default_logfile):
    try:
        logger.handlers[0].stream.close()
        logger.removeHandler(logger.handlers[0])
    except: pass
    file_handler = logging.FileHandler(f)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(name)s, %(asctime)s: %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    # update the symlink to it.
    try: os.unlink(default_logview)
    except: pass
    finally: os.symlink(f, default_logview)

import rs232
import rs485
import labjack
import test_ch

chans = {'rs232':rs232, 'rs485':rs485, 'labjack':labjack, 'test_ch':test_ch}
#chans = {'rs232':rs232, 'labjack':labjack, 'test_ch':test_ch}
for k,v in chans.iteritems(): v.init_comm()

# Initializing connections to components.
# In the case of labjack, function init_comm initializes a dictionary of a thread-Rlock instance
# and port corresponding to a U6 device

import devconfig
funcmap = {}
for k, v in devconfig.devlist.iteritems():
    funcmap[k] = chans[v['conn']].funcmap(k, v['devid'])

# now funcmap has the functions available for each of the devices.
# funcmap is a dictionary of the all components (MFCs, SW etc) associated with the all the functions
# corresponding to it.
# There is a seperate function, "funcmap" that is present in each of the connection libraries
# For each device present in devconfig.devlist, funcmap creates a new class instances for each port on U6
# It is assumed that only one U6 is connected. Eventually, when multiple labjack devices are connected then
# each class should also have a handle for the corresponding device


print "\n\tReading configuration from devconfig.py and initialising the devices."
for d in devconfig.devlist.iterkeys():
    if 'init_state' in funcmap[d]: 
        print "initialising", d
        funcmap[d]['init_state'](devconfig.devlist[d]['init_params'])
# generate the index.html (i.e. the UI seen in browser)
#devconfig.gen_html_ui()
print "\n\tDevice initialisation finished."

def get_response(l, devid, func, args):
    l[devid] = func(args)

class Handler(SocketServer.StreamRequestHandler):
    def __init__(self, request, client_address, server):
        self.logger = logging.getLogger(repr(client_address))
        self.client = client_address
        self.socket = request
        self.thread = threading.currentThread()
        change_logfile(self.logger)
        self.logger.debug('Started talking to '+str(self.client[0])+':'+
                str(self.client[1])+' on '+self.thread.getName())
        SocketServer.StreamRequestHandler.__init__(self, request, client_address, server)
        return

    def setup(self):
        self.logger.debug('Setup')
        return SocketServer.StreamRequestHandler.setup(self)

    def finish(self):
        self.logger.debug('Finish')
        return SocketServer.StreamRequestHandler.finish(self)

    def handle(self):
        while True:          
            line = self.rfile.readline()
            self.logger.debug(line)
            res = []
            try:
                d = json.loads(line)
                t, resps = [], {}
                for r in d:
                    if r['dev'] == 'controller':
                        if r['cmd'] == 'startnew':
                            fname = r['args'][0]
                            change_logfile(self.logger, logdir+fname)
                            print 'changing logfile to', fname
                        elif r['cmd'] == 'stoplog':
                            change_logfile(self.logger)
                            print 'changing logfile to default'
                        res = d
                        resps = {'controller':['OK', '']}
                        continue
                    func = funcmap[r['dev']][r['cmd']]
                    res.append({'dev':r['dev'], 'cmd':r['cmd']})
                    t.append(threading.Thread(target=get_response, args=(resps, r['dev'], func, r['args'])))
                [x.start() for x in t]
                [x.join() for x in t]
                # now we have responses in resps, so
                for i in range(len(res)):
                    res[i]['status'] = resps[res[i]['dev']][0]
                    res[i]['value'] = resps[res[i]['dev']][1]
            except Exception as e:
                res.append({'status':'Error', 'error': repr(e)+line})
            finally:
                self.logger.debug(json.dumps(res))
                self.wfile.write(json.dumps(res)+'\n')
        return
            

class multiServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    allow_reuse_address = True
    pass

if __name__ == '__main__':
    import socket
    import threading

    server = multiServer(('0.0.0.0',9999), Handler)
    print '\n\tListening on:', server.server_address, ' for requests.'
    server.serve_forever()

