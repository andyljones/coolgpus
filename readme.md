This script lets you set a custom GPU fan curve on a headless Linux server.

```text
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 430.40       Driver Version: 430.40       CUDA Version: 10.1     |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  GeForce RTX 208...  On   | 00000000:08:00.0 Off |                  N/A |
| 75%   60C    P2   254W / 250W |   9560MiB / 11019MiB |    100%      Default |
+-------------------------------+----------------------+----------------------+
|   1  GeForce RTX 208...  On   | 00000000:41:00.0  On |                  N/A |
| 90%   70C    P2   237W / 250W |   9556MiB / 11016MiB |     99%      Default |
+-------------------------------+----------------------+----------------------+
```

### Instructions
```
pip install coolgpus
sudo $(which coolgpus) --speed 99 99
``` 
If you hear your server take off, it works! Now interrupt it and re-run either with Sensible Defaults (TM),
```
sudo $(which coolgpus)
```
or you can pass your own fan curve with 
```
sudo $(which coolgpus) --temp 17 84 --speed 15 99 
```
This will make the fan speed increase linearly from 15% at 17C to 99% at 84C.  You can also increase `--hyst` if you want to smooth out oscillations, at the cost of the fans possibly going faster than they need to.

If your system uses systemd and you want to run this as a service, create a systemd unit file at `/etc/systemd/system/coolgpus.service`:

```
[Unit]
Description=Headless GPU Fan Control
After=syslog.target

[Service]
# You can find the script location with `which coolgpus`
ExecStart=/home/ajones/conda/bin/coolgpus

[Install]
WantedBy=multi-user.target
```
and then enable and start it with
```
sudo systemctl enable coolgpus
sudo systemctl start coolgpus
```

### Troubleshooting
* You've got a display attached: it won't work, but see [this issue](https://github.com/andyljones/coolgpus/issues/1) for progress.
* `coolgpus: command not found`: the pip script folder probably isn't on your PATH. On Ubuntu with the apt-get-installed pip, look in `~/.local/bin`.
* General troubleshooting: 
    * Check that `XOrg`, `nvidia-settings` and `nvidia-smi` can all be called from your terminal. 
    * Check if `sudo coolgpus` works. 
    * Open `coolgpus` in a text editor, add a `import pdb; pdb.set_trace()` somewhere, and [explore till you hit the error](https://docs.python.org/3/library/pdb.html#debugger-commands). 

### Why's this necessary?
If you want to install multiple GPUs in a single machine, you have to use blower-style GPUs else the hot exhaust builds up in your case. Blower-style GPUs can get _very loud_, so to avoid annoying customers nvidia artifically limits their fans to ~50% duty. At 50% duty and a heavy workload, blower-style GPUs will hot up to 85C or so and throttle themselves. 

Now if you're on Windows nvidia happily lets you override that limit by setting a custom fan curve. If you're on Linux though you need to use `nvidia-settings`, which - as of Sept 2019 - requires a display attached to each GPU you want to set the fan for. This is a pain to set up, as is checking the GPU temp every few seconds and adjusting the fan speed. 

This script does all that for you.

### How it works
When you run `fans.py`, it sets up a temporary X server for each GPU with a fake display attached. Then, it loops over the GPUs every few seconds and sets the fan speed according to their temperature. When the script dies, it returns control of the fans to the drivers and cleans up the X servers.

### It doesn't work
Check that you've got `XOrg`, `nvidia-settings` and `nvidia-smi` on the `PATH`. Check you don't have a display attached. Otherwise, add breakpoints and print statements till you figure it out!

### Credit
This is based on [this 2016 script](https://github.com/boris-dimitrov/set_gpu_fans_public) by [Boris Dimitrov](dimiroll@gmail.com), which is in turn based on [this 2011 script](https://sites.google.com/site/akohlmey/random-hacks/nvidia-gpu-coolness) by [Axel Kohlmeyer](akohlmey@gmail.com).
