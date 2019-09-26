import os
import re
import time
from subprocess import check_output, Popen, PIPE, STDOUT
from tempfile import mkdtemp
from contextlib import contextmanager

# This is a clamped linear fan curve, going from 20% below 40C to 99% above 75C.
# I don't think it's optimal, but gets the fan-speed-cap-removal job done.
TEMPS  = (40, 75)
SPEEDS = (20, 99)

# EDID for an arbitrary display
EDID = b'\x00\xff\xff\xff\xff\xff\xff\x00\x10\xac\x15\xf0LTA5.\x13\x01\x03\x804 x\xee\x1e\xc5\xaeO4\xb1&\x0ePT\xa5K\x00\x81\x80\xa9@\xd1\x00qO\x01\x01\x01\x01\x01\x01\x01\x01(<\x80\xa0p\xb0#@0 6\x00\x06D!\x00\x00\x1a\x00\x00\x00\xff\x00C592M9B95ATL\n\x00\x00\x00\xfc\x00DELL U2410\n  \x00\x00\x00\xfd\x008L\x1eQ\x11\x00\n      \x00\x1d'

# X conf for a single screen server with fake CRT attached
XORG_CONF = """Section "ServerLayout"
    Identifier     "Layout0"
    Screen      0  "Screen0"     0    0
EndSection

Section "Screen"
    Identifier     "Screen0"
    Device         "VideoCard0"
    Monitor        "Monitor0"
    DefaultDepth   8
    Option         "UseDisplayDevice" "DFP-0"
    Option         "ConnectedMonitor" "DFP-0"
    Option         "CustomEDID" "DFP-0:{edid}"
    Option         "Coolbits" "20"
    SubSection "Display"
                Depth   8
                Modes   "160x200"
    EndSubSection
EndSection

Section "ServerFlags"
    Option         "AllowEmptyInput" "on"
    Option         "Xinerama"        "off"
    Option         "SELinux"         "off"
EndSection

Section "Device"
    Identifier  "Videocard0"
    Driver      "nvidia"
        Screen      0
        Option      "UseDisplayDevice" "DFP-0"
        Option      "ConnectedMonitor" "DFP-0"
        Option      "CustomEDID" "DFP-0:{edid}"
        Option      "Coolbits" "29"
        BusID       "PCI:{bus}"
EndSection

Section "Monitor"
    Identifier      "Monitor0"
    Vendorname      "Dummy Display"
    Modelname       "160x200"
    #Modelname       "1024x768"
EndSection
""" 

def decimalize(bus):
    """Converts a bus ID to an xconf-friendly format by dropping the domain and converting each hex component to 
    decimal"""
    return ':'.join([str(int('0x' + p, 16)) for p in re.split('[:.]', bus[9:])])

def gpu_buses():
    return check_output(['nvidia-smi', '--format=csv,noheader', '--query-gpu=pci.bus_id']).decode().splitlines()

def temperature(bus):
    [temp] = check_output(['nvidia-smi', '--format=csv,noheader', '--query-gpu=temperature.gpu', '-i', bus]).decode().splitlines()
    return int(temp)

def config(bus):
    """Writes out the X server config for a GPU to a temporary directory"""
    tempdir = mkdtemp(prefix='cool-gpu-' + bus)
    edid = os.path.join(tempdir, 'edid.bin')
    conf = os.path.join(tempdir, 'xorg.conf')

    with open(edid, 'wb') as e, open(conf, 'w') as c:
        e.write(EDID)
        c.write(XORG_CONF.format(edid=edid, bus=decimalize(bus)))

    return conf

def xserver(display, bus):
    """Starts the X server for a GPU under a certain display ID""" 
    conf = config(bus)
    proc = Popen(['Xorg', display, '-once', '-config', conf], stdout=PIPE, stderr=STDOUT)
    return proc

@contextmanager
def xservers(buses):
    """A context manager for launching an X server for each GPU in a list. Yields the mapping from bus ID to 
    display ID, and cleans up the X servers on exit."""
    displays, servers = {}, {}
    try:
        for d, bus in enumerate(buses):
            displays[bus] = ':' + str(d)
            print('Starting xserver for display ' + displays[bus])
            servers[bus] = xserver(displays[bus], bus)
        yield displays
    finally:
        for bus, server in servers.items():
            print('Terminating xserver for display ' + displays[bus])
            server.terminate()

def target_speed(temp):
    (lt, ut), (ls, us) = TEMPS, SPEEDS
    load = float(temp - lt)/float(ut - lt)
    load = min(max(load, 0), 1)
    return int(us*load + ls*(1 - load))

def assign(display, command):
    # Our duct-taped-together xorg.conf leads to some innocent - but voluminous - warning messages about
    # failing to authenticate. Here we dispose of them by redirecting STDERR to STDOUT and calling it in
    # check_output.
    check_output(['nvidia-settings', '-a', command], env={'DISPLAY': display}, stderr=STDOUT)

def set_speed(display, target):
    assign(display, '[gpu:0]/GPUFanControlState=1')
    assign(display, '[fan:0]/GPUTargetFanSpeed='+str(int(target)))

def manage_fans(displays):
    """Launches an X server for each GPU, then continually loops over the GPU fans to set their speeds according
    to the GPU temperature. When interrupted, it releases the fan control back to the driver and shuts down the
    X servers"""
    try:
        while True:
            for bus, display in displays.items():
                temp = temperature(bus)
                target = target_speed(temp)
                set_speed(display, target)
                print('GPU at '+display+' is '+str(temp)+'C, setting target speed to '+str(target))
            time.sleep(5)
    finally:
        for bus, display in displays.items():
            assign(display, '[gpu:0]/GPUFanControlState=0')
            print('Released fan speed control for GPU at '+display)

def run():
    buses = gpu_buses()
    with xservers(buses) as displays:
        manage_fans(displays)

if __name__ == '__main__':
    run()