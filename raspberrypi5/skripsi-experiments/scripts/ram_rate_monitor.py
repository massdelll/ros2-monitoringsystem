
#!/usr/bin/env python3

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path


def read_ram():
    values = {}

    with open("/proc/meminfo", "r") as f:
        for line in f:
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])

    total = values["MemTotal"]
    available = values["MemAvailable"]
    used = total - available

    return total, available, used


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rate", type=int, choices=[1, 2, 3], required=True)
    parser.add_argument("--environment", choices=["native", "docker"], required=True)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--run", type=int, default=1)
    args = parser.parse_args()

    output_dir = Path.home() / "skripsi-experiments/data/ram/rate"
    output_dir.mkdir(parents=True, exist_ok=True)

    output = output_dir / (
        f"ram_{args.environment}_{args.rate}msgps_run{args.run}.csv"
    )

    start = time.monotonic()
    deadline = start + args.duration
    next_sample = start

    with output.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "elapsed_seconds", "environment",
            "message_rate", "duration_seconds", "run",
            "ram_total_mib", "ram_available_mib",
            "ram_used_mib", "ram_used_percent"
        ])

        while next_sample < deadline:
            time.sleep(max(0, next_sample - time.monotonic()))

            total, available, used = read_ram()
            elapsed = time.monotonic() - start

            writer.writerow([
                datetime.now().isoformat(timespec="milliseconds"),
                round(elapsed, 3), args.environment, args.rate,
                args.duration, args.run,
                round(total / 1024, 2),
                round(available / 1024, 2),
                round(used / 1024, 2),
                round(used / total * 100, 2)
            ])
            f.flush()
            next_sample += 1

    print(f"Pengukuran RAM selesai: {output}")


if __name__ == "__main__":
    main()
