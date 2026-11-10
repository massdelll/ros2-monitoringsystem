
#!/usr/bin/env python3

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path


def read_cpu():
    with open("/proc/stat", "r") as f:
        values = list(map(int, f.readline().split()[1:]))

    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rate", type=int, choices=[1, 2, 3], required=True)
    parser.add_argument("--environment", choices=["native", "docker"], required=True)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--run", type=int, default=1)
    args = parser.parse_args()

    output_dir = Path.home() / "skripsi-experiments/data/cpu/rate"
    output_dir.mkdir(parents=True, exist_ok=True)

    output = output_dir / (
        f"cpu_{args.environment}_{args.rate}msgps_run{args.run}.csv"
    )

    prev_total, prev_idle = read_cpu()
    start = time.monotonic()
    deadline = start + args.duration
    next_sample = start + 1

    with output.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "elapsed_seconds", "environment",
            "message_rate", "duration_seconds", "run",
            "cpu_usage_percent"
        ])

        while next_sample <= deadline:
            time.sleep(max(0, next_sample - time.monotonic()))

            total, idle = read_cpu()
            delta_total = total - prev_total
            delta_idle = idle - prev_idle

            usage = (
                100 * (delta_total - delta_idle) / delta_total
                if delta_total > 0 else 0
            )

            elapsed = time.monotonic() - start

            writer.writerow([
                datetime.now().isoformat(timespec="milliseconds"),
                round(elapsed, 3), args.environment, args.rate,
                args.duration, args.run, round(usage, 2)
            ])
            f.flush()

            prev_total, prev_idle = total, idle
            next_sample += 1

    print(f"Pengukuran CPU selesai: {output}")


if __name__ == "__main__":
    main()
