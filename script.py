import os
import re
import subprocess
import sys


def check_loadavg():
    cpu_count = os.cpu_count() or 1

    with open("/proc/loadavg", "r") as loadavg:
        load_data = loadavg.read().split()
        one_min = float(load_data[0])
        five_min = float(load_data[1])
        fifteen_min = float(load_data[2])
        runnable_threads, _ = load_data[3].split("/")
        runnable_threads = int(runnable_threads)

    status = "OK"
    message = f"Load normal. 1-min: {one_min}, CPUs: {cpu_count}"

    if runnable_threads > cpu_count:
        status = "WARNING"
        message = f"CPU contention detected! Runnable threads ({runnable_threads}) exceed CPU cores ({cpu_count})."
    elif one_min > (cpu_count * 1.5):
        status = "WARNING"
        message = f"High load average! 1-min load ({one_min}) is 150% greater than core count."

    return {
        "check": "Load Average",
        "status": status,
        "message": message,
        "metrics": {
            "1min": one_min,
            "5min": five_min,
            "15min": fifteen_min,
            "runnable_threads": runnable_threads,
            "cpu_count": cpu_count,
        },
    }


def check_kernel_ring_buffer():
    result = subprocess.run(
        "dmesg -T | tail -n 50", shell=True, capture_output=True, text=True, check=False
    )
    pattern = re.compile(r"(oom-killer|out of memory|segfault)", re.IGNORECASE)
    status = "OK"
    warning_messages = []

    for line in result.stdout.splitlines():
        if pattern.search(line):
            status = "CRITICAL"
            warning_messages.append(line)

    if warning_messages:
        message = f"Kernel anomaly detected: {warning_messages[-1].strip()}"
    else:
        message = "No critical kernel anomalies found in recent buffer."

    return {
        "check": "Kernel Ring Buffer (dmesg)",
        "status": status,
        "message": message,
        "metrics": {
            "lines_scanned": len(result.stdout.splitlines()),
            "anomalies_detected": len(warning_messages),
        },
    }


def check_vmstat():
    result = subprocess.run(
        "vmstat 1 2", shell=True, capture_output=True, text=True, check=False
    )
    line = result.stdout.splitlines()[-1]
    parts = line.split()

    r = int(parts[0])
    b = int(parts[1])
    si = int(parts[6])
    so = int(parts[7])
    wa = int(parts[15])

    status = "OK"
    messages = []

    # Threshold checks
    if si > 0 or so > 0:
        status = "CRITICAL"
        messages.append(f"Memory thrashing detected (si: {si}, so: {so})")
    if wa > 30:
        status = (
            "CRITICAL" if status != "CRITICAL" else status
        )  # Keep CRITICAL if already set, or handle accordingly
        messages.append(f"High I/O wait time: {wa}%")
    if b > 5:
        status = "CRITICAL"
        messages.append(f"High blocked processes: {b}")

    message = (
        "; ".join(messages) if messages else "vmstat metrics within normal parameters."
    )

    return {
        "check": "VMStat Performance",
        "status": status,
        "message": message,
        "metrics": {"r": r, "b": b, "si": si, "so": so, "wa": wa},
    }


def check_mpstat():
    result = subprocess.run(
        "mpstat -P ALL 1 2", shell=True, capture_output=True, text=True, check=False
    )
    for line in result.stdout.splitlines():
        if "all" in line:
            target_line = line

    parts = target_line.split()
    # index of all skipping the timestamp in case of HH:MM:SS or HH:MM:SS AM/PM
    all_index = parts.index("all")

    usr = float(parts[all_index + 1])
    sys_cpu = float(parts[all_index + 3])
    iowait = float(parts[all_index + 4])
    idle = float(parts[all_index + 10])

    status = "OK"
    messages = []

    # Threshold checks
    if idle < 10.0:
        status = "CRITICAL"
        messages.append(f"Low CPU idle time: {idle}%")
    if iowait > 20.0:
        status = "CRITICAL" if status != "CRITICAL" else status
        messages.append(f"High CPU I/O wait: {iowait}%")

    message = (
        "; ".join(messages)
        if messages
        else "CPU performance metrics within normal parameters."
    )

    return {
        "check": "CPU Performance (mpstat)",
        "status": status,
        "message": message,
        "metrics": {"usr": usr, "sys": sys_cpu, "iowait": iowait, "idle": idle},
    }


def check_pidstat():
    num_cores = os.cpu_count() or 1
    cpu_threshold = 80.0 * num_cores

    result = subprocess.run(
        "pidstat 1 2", shell=True, capture_output=True, text=True, check=False
    )
    lines = result.stdout.splitlines()

    max_cpu = 0.0
    top_pid = "N/A"
    top_command = "N/A"

    for line in lines:
        if not line or line.startswith("Linux") or "UID:" in line:
            continue

        parts = line.split()
        if len(parts) >= 8 and parts[1].isdigit():
            try:
                cpu_usage = float(parts[7])
                pid = parts[1]
                command = parts[-1]

                if cpu_usage > max_cpu:
                    max_cpu = cpu_usage
                    top_pid = pid
                    top_command = command
            except (ValueError, IndexError):
                continue

    status = "OK"
    message = f"Top process {top_command} (PID: {top_pid}) using {max_cpu:.1f}% CPU."

    if max_cpu > cpu_threshold:
        status = "CRITICAL"
        message = f"Process {top_command} (PID: {top_pid}) exceeded threshold: {max_cpu:.1f}% CPU (Limit: {cpu_threshold:.1f}%)"

    return {
        "check": "Process CPU Performance (pidstat)",
        "status": status,
        "message": message,
        "metrics": {
            "top_pid": top_pid,
            "top_command": top_command,
            "max_cpu_pct": max_cpu,
            "core_threshold": cpu_threshold,
        },
    }


def check_iostat():
    result = subprocess.run(
        "iostat -xz 1 2", shell=True, capture_output=True, text=True, check=False
    )

    lines = result.stdout.splitlines()
    device_header_count = 0
    target_lines = []

    for line in lines:
        if "Device:" in line:
            device_header_count += 1
            continue  # Skip header line

        if device_header_count == 2 and line.strip():
            target_lines.append(line)  # Skip empty lines

    max_util = 0.0
    max_await = 0.0
    critical_device = "N/A"

    for line in target_lines:
        parts = line.split()
        if len(parts) >= 10:
            try:
                device = parts[0]
                util = float(parts[-1])
                await_val = float(parts[9])

                if util > max_util:
                    max_util = util
                    max_await = await_val
                    critical_device = device
            except (ValueError, IndexError):
                continue

    status = "OK"
    message = f"Disk {critical_device} utilization at {max_util:.1f}% (await: {max_await:.2f}ms)."

    if max_util > 90.0 or max_await > 50.0:
        status = "CRITICAL"
        message = f"High disk saturation on {critical_device}: {max_util:.1f}% util, await: {max_await:.2f}ms"

    return {
        "check": "Disk Performance (iostat)",
        "status": status,
        "message": message,
        "metrics": {
            "device": critical_device,
            "util_pct": max_util,
            "await_ms": max_await,
        },
    }


def check_meminfo():
    mem_data = {}
    with open("/proc/meminfo", "r") as meminfo:
        for line in meminfo:
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val_parts = parts[1].strip().split()
                if val_parts and val_parts[0].isdigit():
                    mem_data[key] = int(val_parts[0])

    total = mem_data.get("MemTotal", 0)
    available = mem_data.get("MemAvailable", mem_data.get("MemFree", 0))

    used_pct = 0.0
    if total > 0:
        used_pct = ((total - available) / total) * 100.0

    status = "OK"
    message = f"Memory utilization at {used_pct:.1f}%."

    if used_pct > 90.0:
        status = "CRITICAL"
        message = f"High memory utilization: {used_pct:.1f}% (Available: {available // 1024} MB)"

    return {
        "check": "Memory Usage (/proc/meminfo)",
        "status": status,
        "message": message,
        "metrics": {"total_kb": total, "available_kb": available, "used_pct": used_pct},
    }


def check_DEV():
    interfaces = {}
    with open("/proc/net/dev", "r") as dev:
        lines = dev.readlines()
        for line in lines[2:]:
            if ":" in line:
                iface, data = line.split(":", 1)
                iface = iface.strip()

                if iface == "lo":
                    continue

                parts = data.split()
                if len(parts) >= 16:
                    try:
                        # Receive
                        rx_errs = int(parts[2])
                        rx_drop = int(parts[3])

                        # Transmit
                        tx_errs = int(parts[10])
                        tx_drop = int(parts[11])

                        interfaces[iface] = {
                            "rx_errs": rx_errs,
                            "rx_drop": rx_drop,
                            "tx_errs": tx_errs,
                            "tx_drop": tx_drop,
                        }
                    except (ValueError, IndexError):
                        continue

    status = "OK"
    messages = []
    total_errs = 0

    for iface, stats in interfaces.items():
        errs = stats["rx_errs"] + stats["tx_errs"] + stats["rx_drop"] + stats["tx_drop"]
        total_errs += errs
        if errs > 0:
            messages.append(f"Interface {iface} has errors/drops (Total: {errs})")

    if messages:
        status = "WARNING"  # or CRITICAL depending on severity
        message = "; ".join(messages)
    else:
        message = "All network interfaces healthy (zero errors/drops)."

    return {
        "check": "Network Interface Errors (/proc/net/dev)",
        "status": status,
        "message": message,
        "metrics": interfaces,
    }


def check_tcp():
    result = subprocess.run(
        "sar -n TCP,ETCP 1 2", shell=True, capture_output=True, text=True, check=False
    )
    lines = result.stdout.splitlines()

    active = 0.0
    passive = 0.0
    retrans = 0.0

    for line in reversed(lines):
        parts = line.split()
        if (
            len(parts) == 5
            and ":" in parts[0]
            and parts[1].replace(".", "", 1).isdigit()
        ):
            try:
                active = float(parts[1])
                passive = float(parts[2])
                break
            except ValueError:
                continue

    for line in reversed(lines):
        parts = line.split()
        if len(parts) == 6 and ":" in parts[0]:
            try:
                retrans = float(parts[3])
                break
            except ValueError:
                continue

    status = "OK"
    message = f"TCP rates normal: {active:.2f} active/s, {passive:.2f} passive/s, {retrans:.2f} retrans/s."

    if retrans > 5.0:
        status = "WARNING"
        message = f"Elevated TCP retransmissions: {retrans:.2f} retrans/s."

    return {
        "check": "TCP Network Rates (sar)",
        "status": status,
        "message": message,
        "metrics": {
            "active_per_sec": active,
            "passive_per_sec": passive,
            "retrans_per_sec": retrans,
        },
    }


def check_top():
    result = subprocess.run(
        "top -b -n 1", shell=True, capture_output=True, text=True, check=False
    )
    lines = result.stdout.splitlines()

    load_avg = (0.0, 0.0, 0.0)
    top_process = "N/A"
    top_cpu = 0.0

    for line in lines:
        if "load average:" in line:
            # Extract load averages from the header line
            parts = line.split("load average:")
            if len(parts) > 2 or len(parts) == 2:
                loads = [float(x.strip().strip(",")) for x in parts[1].split(",")]
                if len(loads) >= 3:
                    load_avg = (loads[0], loads[1], loads[2])
        elif "%CPU" in line or "PID" in line:
            # Header line for processes; the rows follow right after
            continue
        elif (
            line.strip()
            and not line.startswith("top")
            and not line.startswith("Tasks")
            and not line.startswith("%Cpu")
            and not line.startswith("KiB")
            and not line.startswith("MiB")
        ):
            # Process rows start here
            parts = line.split()
            if len(parts) >= 12 and parts[0].isdigit():
                try:
                    pid = parts[0]
                    user = parts[1]
                    cpu = float(parts[8])
                    command = parts[-1]
                    if cpu > top_cpu:
                        top_cpu = cpu
                        top_process = f"{command} (PID: {pid}, User: {user})"
                except (ValueError, IndexError):
                    continue

    status = "OK"
    message = f"Load averages: {load_avg[0]}, {load_avg[1]}, {load_avg[2]}. Top process: {top_process} at {top_cpu}% CPU."

    if load_avg[0] > 20.0:
        status = "CRITICAL"
        message = f"High 1-min load average: {load_avg[0]}. Top process: {top_process}"

    return {
        "check": "System Snapshot (top)",
        "status": status,
        "message": message,
        "metrics": {
            "load_1min": load_avg[0],
            "load_5min": load_avg[1],
            "load_15min": load_avg[2],
            "top_process": top_process,
            "top_cpu_pct": top_cpu,
        },
    }


def main():
    if os.geteuid() != 0:
        sys.exit("Error: Please run this script with sudo.")

    results = {
        "loadavg": check_loadavg(),
        "dmesg": check_kernel_ring_buffer(),
        "vmstat": check_vmstat(),
        "mpstat": check_mpstat(),
        "pidstat": check_pidstat(),
        "iostat": check_iostat(),
        "meminfo": check_meminfo(),
        "dev": check_DEV(),
        "tcp": check_tcp(),
        "top": check_top(),
    }

    # Example of accessing results[check_top()] or results["loadavg"]
    load_result = results["loadavg"]

    print("--- Diagnostic Summary ---")
    print(f"Check: {load_result['check']}")
    print(f"Status: {load_result['status']}")
    print(f"Message: {load_result['message']}")
    print("Metrics:")
    for key, value in load_result["metrics"].items():
        print(f"  - {key}: {value}")


if __name__ == "__main__":
    main()
