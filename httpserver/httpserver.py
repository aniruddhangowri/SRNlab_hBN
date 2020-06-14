import os, os.path
import string
import json
import random


import socket
cnt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
cnt.connect(('127.0.0.1', 9999))
cntfile = cnt.makefile()
def command_handler(d):
    global cnt, cntfile
    cnt.send(json.dumps(d)+'\n')
    return cntfile.readline()

def dummy_command_handler(d):
    r = {}
    r['dev'], r['cmd'], d = d['dev'], d['cmd']
    r['value'] = random.random()
    r['status'] = 'OK'
    return json.dumps(r)

import cherrypy

class FurnaceControl(object):
    @cherrypy.expose
    def index(self):
        return file('index.html')
    #@cherrypy.expose
    #def svg(self):
    #    return file('svg.html')

class FurnaceController(object):
    exposed = True

    @cherrypy.tools.accept(media='text/plain')
    def GET(self):
        return ''
        #return cherrypy.session['mystring']
    
    # json_out is not needed since controlserver communicates on json already.
    #@cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def POST(self):
        data = cherrypy.request.json
        #cherrypy.log(json.dumps(data))
        return command_handler(data) 

    def PUT(self, another_string):
        pass

    def DELETE(self):
        pass
        #cherrypy.session['mystring'] = another_string
        #cherrypy.session.pop('mystring', None)

from readlog import get_plotdata

class Logs(object):
    @cherrypy.expose
    def index(self):
        return file('logs.html')

class LogGenerator(object):
    exposed = True
    
    @cherrypy.tools.accept(media='text/plain')
    def GET(self):
        return ''
    
    # json_out is not needed since controlserver communicates on json already.
    #@cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def POST(self):
        data = cherrypy.request.json
        #cherrypy.log(json.dumps(data))
        return get_plotdata(data) 

    def PUT(self, another_string):
        pass

    def DELETE(self):
        pass
        #cherrypy.session['mystring'] = another_string
        #cherrypy.session.pop('mystring', None)

import scriptmanager
class ScriptHandler(object):
    exposed = True
    
    @cherrypy.tools.accept(media='text/plain')
    def GET(self):
        return ''
    
    # json_out is not needed since controlserver communicates on json already.
    #@cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def POST(self):
        data = cherrypy.request.json
        #cherrypy.log(json.dumps(data))
        return scriptmanager.process_req(data) 

    def PUT(self, another_string):
        pass

    def DELETE(self):
        pass
        #cherrypy.session['mystring'] = another_string
        #cherrypy.session.pop('mystring', None)



if __name__ == '__main__':
    conf = {
        'global': {
            'log.screen': False,
            'log.access_file': os.path.abspath(os.getcwd())+'/access_log.txt',
            'log.error_file': os.path.abspath(os.getcwd())+'/error_log.txt',
            'server.socket_port': 8080,
            'server.socket_host': '0.0.0.0'
            },
        '/': {
            'tools.sessions.on': True,
            'tools.sessions.storage_type': "file",
            'tools.sessions.storage_path': os.path.abspath(os.getcwd())+'/sessions',
            #tools.sessions.timeout = 60
            'tools.staticdir.root': os.path.abspath(os.getcwd())
        },
        '/generator': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'text/plain')],
        },
        '/logs': {
            'tools.sessions.on': True,
            'tools.sessions.storage_type': "file",
            'tools.sessions.storage_path': os.path.abspath(os.getcwd())+'/sessions',
            #tools.sessions.timeout = 60
            'tools.staticdir.root': os.path.abspath(os.getcwd())
        },
        '/loggenerator': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'text/plain')],
        },
        '/scripthandler': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'text/plain')],
        },
        '/static': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': './public'
        }
    }
    webapp = FurnaceControl()
    webapp.generator = FurnaceController()
    webapp.logs = Logs()
    webapp.loggenerator = LogGenerator()
    webapp.scripthandler = ScriptHandler()
    print """
    Connected to the controlserver and processing requests at http://localhost:8080.
    You can view logs at http://localhost:8080/logs/.

    To exit, press Ctrl-C in this window."""
    cherrypy.quickstart(webapp, '/', conf)
