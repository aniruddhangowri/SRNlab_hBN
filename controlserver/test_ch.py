
def funcmap(devname, devid):
    return { 'set': set_value, 'get': get_value, 'init_state': init_state}

def init_comm():
    return

def set_value(xs):
    return 'OK', xs[0]

def get_value(xs):
    return 'OK', xs[0]

def init_state(xs):
    return xs



