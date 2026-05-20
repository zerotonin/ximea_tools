# ximea_tools

*« Linux toolbox for XIMEA industrial cameras »*

A research-grade recorder, a PyQt5 GUI, and an external hardware-trigger
("CueWire") integration for XIMEA xiC / xiQ industrial cameras.

[![tests](https://github.com/zerotonin/ximea_tools/actions/workflows/tests.yml/badge.svg)](https://github.com/zerotonin/ximea_tools/actions/workflows/tests.yml)
[![docs](https://github.com/zerotonin/ximea_tools/actions/workflows/docs.yml/badge.svg)](https://github.com/zerotonin/ximea_tools/actions/workflows/docs.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)


## Status

| Sprint | Scope | State |
|---|---|---|
| 1 | Package scaffold, CI, docs skeleton, `_legacy/` archive | in progress |
| 2 | Core recorder rewrite — `camera`, `writer`, `recorder`, CLI | planned |
| 3 | PyQt5 GUI: live preview, ROI rubber-band, settings persistence | planned |
| 4 | CueWire external hardware trigger integration | planned |


## Installation

Tested on Linux (Ubuntu 22.04+), Python 3.11+.

**1. Install the XIMEA Linux SDK** (provides the native `libm3api` and the
`ximea` Python module):

```bash
# Download from https://www.ximea.com/support/wiki/apis/Python
tar xzf XIMEA_Linux_SP.tgz
cd package
sudo ./install
```

**2. Install `ximea_tools`:**

```bash
git clone https://github.com/zerotonin/ximea_tools.git
cd ximea_tools
pip install -e ".[dev]"
```


## Quickstart

CLI (lands in v0.2):

```bash
ximea-record --exposure 10000 --fps 30 --duration 5 \
             --roi 1200x1000+424+44 --output /media/dataSSD
```

GUI (lands in v0.3):

```bash
ximea-gui
```


## Hitting the camera's full framerate (UVC quirks)

Two Linux behaviours frequently throttle UVC webcams (we hit both with
the Microsoft LifeCam Cinema in development):

**1. Auto-exposure mode.** Forcing the camera into manual exposure
(`V4L2_CID_EXPOSURE_AUTO = 1`) often clamps fps far below what the
camera reports.  `ximea_tools` defaults `auto_exposure=True` for that
reason — toggle the *Auto exposure* checkbox in the Camera dock only
when you actually need a fixed exposure (and accept the slower fps).

**2. USB autosuspend.**  Linux will park idle USB devices to save
power; some webcams never quite wake back up to full bandwidth.  Check:

```bash
ls /sys/bus/usb/devices/*/product            # find your camera bus path
cat /sys/bus/usb/devices/1-13/power/control   # 'auto' means it'll suspend
```

Disable temporarily (until reboot):

```bash
echo on | sudo tee /sys/bus/usb/devices/1-13/power/control
```

Persistent fix — drop a udev rule (replace VID/PID with your camera's,
visible in `lsusb`):

```bash
sudo tee /etc/udev/rules.d/99-webcam-no-autosuspend.rules <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="045e", ATTR{idProduct}=="0812", \
    TEST=="power/control", ATTR{power/control}="on"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```


## Citation


## Citation

If you use this software, please cite the metadata in `CITATION.cff`. A
Zenodo DOI is minted on each tagged release.


## License

MIT — see `LICENSE`.


## Author

Bart R.H. Geurten · Department of Zoology, University of Otago, Dunedin,
New Zealand · [ORCID 0000-0002-1816-3241](https://orcid.org/0000-0002-1816-3241)
