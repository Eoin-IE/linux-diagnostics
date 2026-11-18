# Linux System Diagnostics

A Python script that automates Brendan Gregg's "60-second Linux performance analysis" checklist and prints a readable
diagnostic summary.

## Why I made this?

I made this because I was learning both about Linux troubleshooting and how to use python to run Linux commands and read logs.

## What it does

- Automates the 10-command sweep from Brendan Gregg's Netflix "60-second analysis" methodology
- Checks CPU load, memory, disk, and network health in one pass
- Reads kernel logs (`dmesg`) for OOM kills and segfaults
- Parses `vmstat`, `mpstat`, `pidstat`, `iostat`, `sar`, and `top` for performance metrics
- Checks `/proc/loadavg`, `/proc/meminfo`, and `/proc/net/dev` directly
- Flags issues as `OK`, `WARNING`, or `CRITICAL` with a human-readable message

## Background: The 60-Second Rule

Brendan Gregg (former Netflix performance architect) published "Linux Performance Analysis in 60,000 Milliseconds"
in 2015, outlining ten standard commands to run in the first minute of a performance investigation.
The goal is to quickly check errors and saturation first, then utilization, before deciding where to dig deeper.

## Requirements

- Linux (uses `/proc`, `dmesg`, `vmstat`, `mpstat`, `pidstat`, `iostat`, `sar`, `top`)
- Python 3
- `sysstat` package for `mpstat`, `pidstat`, `iostat`, and `sar`:

  ```bash
  sudo apt install sysstat   # Debian/Ubuntu
  sudo dnf install sysstat   # Fedora/RHEL
  ```

## Usage

Must be run as root (needs `dmesg` and `/proc` access):

```bash
sudo python3 diagnostics.py
```

## Example output

```text
--- Diagnostic Summary ---

Check: Load Average
Status: OK
Message: Load normal. 1-min: 0.42, CPUs: 8
Metrics:
  - 1min: 0.42
  - 5min: 0.38
  - 15min: 0.31
  - runnable_threads: 1
  - cpu_count: 8
----------------------------------------
...
```

## Notes

- Some checks depend on `sysstat` tools being installed — missing tools will cause that check to return empty metrics rather than crash.
- Thresholds (e.g. 90% disk util, 80% CPU per core, 5 TCP retrans/s) are hardcoded at the top of each check function and easy to tune.
