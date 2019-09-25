import os
import re
import time
from subprocess import check_output, Popen, PIPE, STDOUT
from tempfile import mkdtemp
from contextlib import contextmanager

# These are the steps on the fan curve, as taken from Boris Dimitriov's script
# I don't think it's optimal, but it does the job of removing the fan speed cap
# Temps are in degrees centigrade, as reported by nvidia-smi, and speeds are a throttle percentage
TEMPS  = [30, 34, 38, 40, 43, 49, 54, 61, 65, 70, 77, float('Inf')]
SPEEDS = [20, 30, 40, 45, 50, 60, 65, 75, 80, 85, 90, 95]

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
    """Drop the domain and convert each hex part to decimal"""
    return ':'.join([str(int('0x' + p, 16)) for p in re.split('[:.]', bus[9:])])

def gpu_buses():
    return check_output(['nvidia-smi', '--format=csv,noheader', '--query-gpu=pci.bus_id']).decode().splitlines()

def temperature(bus):
    [temp] = check_output(['nvidia-smi', '--format=csv,noheader', '--query-gpu=temperature.gpu', '-i', bus]).decode().splitlines()
    return int(temp)

def config(bus):
    tempdir = mkdtemp(prefix='cool-gpu-' + bus)
    edid = os.path.join(tempdir, 'edid.bin')
    conf = os.path.join(tempdir, 'xorg.conf')

    with open(edid, 'wb') as e, open(conf, 'w') as c:
        e.write(EDID)
        c.write(XORG_CONF.format(edid=edid, bus=decimalize(bus)))

    return conf

def xserver(display, bus):
    conf = config(bus)
    proc = Popen(['Xorg', display, '-once', '-config', conf], stdout=PIPE, stderr=STDOUT)
    return proc

@contextmanager
def xservers(buses):
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
    for threshold, speed in zip(TEMPS[::-1], SPEEDS[::-1]):
        if temp < threshold:
            target = speed
    return target

def assign(display, command):
    # Our duct-taped-together xorg.conf leads to some innocent - but voluminous - warning messages about
    # failing to authenticate. Here we dispose of them by redirecting STDERR to STDOUT and calling it in
    # check_output.
    check_output(['nvidia-settings', '-a', command], env={'DISPLAY': display}, stderr=STDOUT)

def set_speed(display, target):
    assign(display, '[gpu:0]/GPUFanControlState=1')
    assign(display, '[fan:0]/GPUTargetFanSpeed='+str(target))

def manage_fans(displays):
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