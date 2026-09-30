# USB Power for macOS

A small, local control panel for switching USB-C port power with [uhubctl](https://github.com/mvp/uhubctl). It includes a command-line tool and a browser interface. It was built for a Mac with an Apple USB2 hub at location `2-1` and two ports.

![macOS](https://img.shields.io/badge/macOS-local%20only-08795c)

## Requirements

- macOS with a USB hub that supports per-port power switching (`ppps` in `uhubctl` output)
- `uhubctl` (`brew install uhubctl`)
- Python 3.9 or newer for the web interface

Find the hub and port that correspond to your device with `uhubctl`. Switching a USB-C port may switch its USB2 and USB3 companion ports together. Test the selected port with the device connected before relying on a schedule.

## Install

```bash
git clone https://github.com/gallonyin/usb-power-mac.git
cd usb-power-mac
./install.sh
```

The installer links `usb-power` into `~/.local/bin`. Keep the cloned directory in place because the command and launchd jobs point to it. The installer backs up an existing command before replacing it.

## Use

```bash
usb-power                # help
usb-power hub            # current hub location; defaults to 2-1
usb-power hub 2-1        # change the saved hub location
usb-power status 2       # read power status
usb-power on 2           # turn on
usb-power off 2          # turn off
usb-power cycle on 2     # start a daily schedule, charging immediately
usb-power cycle status 2
usb-power cycle off 2    # stop schedule, leave the port powered on
usb-power web            # open the local control panel
```

Port defaults to `1`. Double-click `open-usb-power.command` to open the control panel without typing a command. The page binds only to `127.0.0.1:8765`; close the terminal running it to stop the page. The schedule runs separately through a macOS LaunchAgent and continues when the page is closed.

## Fixed schedule

Each port has its own optional schedule: **6 hours on, 18 hours off**, repeated every 24 hours from the time the schedule is enabled. A LaunchAgent checks every 5 minutes. After login or wake, it applies the phase calculated from the original start time. Stopping the schedule turns the port on.

This is a timer, not battery-aware charging. It cannot guarantee that a phone stays powered: workload, charging speed, battery age, Mac sleep, shutdown, power loss, and failed USB switching can all change the outcome. Observe the phone's charge after an 18-hour off period before leaving it unattended. Where available, a built-in battery charge limit is more precise for battery care.

## Privacy and security

The web interface has no cloud service, binds to loopback only, and requires a session token for changes. It uses Python's standard library and invokes the local CLI. Do not expose port 8765 through a proxy or tunnel.

## Development

```bash
bash -n usb-power install.sh open-usb-power.command
python3 -m unittest discover -s tests
```

## License

MIT. See [LICENSE](LICENSE).
