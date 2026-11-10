
#!/usr/bin/env python3

import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


DURATION_SECONDS = 30
SAMPLE_INTERVAL_SECONDS = 1
TOPIC_NAME = "/sensor_data"

PAYLOAD_LABELS = {
    144: "payload1",
    256: "payload2",
    384: "payload3",
}


def read_cpu_counters():
    """Membaca statistik CPU sistem dari /proc/stat."""
    with open("/proc/stat", "r", encoding="utf-8") as file:
        values = list(map(int, file.readline().split()[1:]))

    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)

    return total, idle


def calculate_cpu_percent(previous, current):
    """Menghitung persentase penggunaan CPU dari selisih counter."""
    previous_total, previous_idle = previous
    current_total, current_idle = current

    total_delta = current_total - previous_total
    idle_delta = current_idle - previous_idle

    if total_delta <= 0:
        return 0.0

    return max(
        0.0,
        min(100.0, (total_delta - idle_delta) / total_delta * 100.0)
    )


def read_ram_stats():
    """Membaca statistik RAM sistem dari /proc/meminfo."""
    values = {}

    with open("/proc/meminfo", "r", encoding="utf-8") as file:
        for line in file:
            key, raw_value = line.split(":", 1)
            values[key] = int(raw_value.strip().split()[0])

    # Nilai /proc/meminfo dikonversi dari KiB menjadi MiB.
    total = values["MemTotal"] / 1024
    available = values["MemAvailable"] / 1024
    used = total - available
    used_percent = used / total * 100 if total else 0.0

    return total, available, used, used_percent


class PayloadMonitor(Node):
    def __init__(self, scenario, metric, payload_bytes, output_dir):
        super().__init__("payload_resource_monitor")

        self.scenario = scenario
        self.metric = metric
        self.payload_bytes = payload_bytes
        self.output_dir = Path(output_dir)

        self.started = False
        self.finished = False
        self.start_monotonic = None
        self.next_sample = 1
        self.previous_cpu = None
        self.rows = []
        self.matched_messages = 0

        label = PAYLOAD_LABELS[payload_bytes]
        filename = f"{metric}-{scenario}-{label}.csv"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = self.output_dir / filename

        self.subscription = self.create_subscription(
            String,
            TOPIC_NAME,
            self.message_callback,
            10,
        )

        # Timer memeriksa waktu secara berkala. Sampel tetap
        # dijadwalkan pada detik ke-1 sampai detik ke-30.
        self.timer = self.create_timer(0.05, self.timer_callback)

        self.get_logger().info(
            f"Menunggu payload {payload_bytes} byte pada {TOPIC_NAME}"
        )
        self.get_logger().info(
            f"Skenario={scenario}, parameter={metric}, "
            f"durasi={DURATION_SECONDS} detik"
        )

    def message_callback(self, msg):
        actual_size = len(msg.data.encode("utf-8"))

        if actual_size != self.payload_bytes:
            return

        self.matched_messages += 1

        if not self.started:
            self.started = True
            self.start_monotonic = time.monotonic()
            self.previous_cpu = read_cpu_counters()

            self.get_logger().info(
                f"Payload target pertama terdeteksi: {actual_size} byte. "
                "Pengukuran dimulai."
            )

    def timer_callback(self):
        if not self.started or self.finished:
            return

        elapsed = time.monotonic() - self.start_monotonic

        if elapsed < self.next_sample:
            return

        # Ambil tepat satu sampel untuk setiap detik yang dijadwalkan.
        # Jika sistem terlambat, jangan membuat sampel palsu.
        sample_second = self.next_sample

        timestamp = datetime.now().astimezone().isoformat(
            timespec="milliseconds"
        )

        common = {
            "timestamp": timestamp,
            "elapsed_seconds": sample_second,
            "scenario": self.scenario,
            "payload_bytes": self.payload_bytes,
            "duration_seconds": DURATION_SECONDS,
            "matched_messages": self.matched_messages,
        }

        if self.metric == "cpu":
            current_cpu = read_cpu_counters()
            cpu_percent = calculate_cpu_percent(
                self.previous_cpu, current_cpu
            )
            self.previous_cpu = current_cpu

            row = {
                **common,
                "cpu_percent": round(cpu_percent, 4),
                "unit": "%",
            }

        else:
            total, available, used, used_percent = read_ram_stats()

            row = {
                **common,
                "ram_total_mib": round(total, 2),
                "ram_available_mib": round(available, 2),
                "ram_used_mib": round(used, 2),
                "ram_used_percent": round(used_percent, 4),
                "unit": "MiB",
            }

        self.rows.append(row)

        self.get_logger().info(
            f"Detik {sample_second}/{DURATION_SECONDS}: "
            + (
                f"CPU={row['cpu_percent']:.2f}%"
                if self.metric == "cpu"
                else f"RAM used={row['ram_used_mib']:.2f} MiB"
            )
        )

        self.next_sample += SAMPLE_INTERVAL_SECONDS

        if sample_second >= DURATION_SECONDS:
            self.save_csv()
            self.finished = True
            self.get_logger().info(
                f"Pengukuran selesai. CSV: {self.output_path}"
            )
            rclpy.shutdown()

    def save_csv(self):
        if not self.rows:
            self.get_logger().error("Tidak ada sampel yang berhasil dicatat.")
            return

        fieldnames = list(self.rows[0].keys())

        with self.output_path.open(
            "w", newline="", encoding="utf-8"
        ) as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.rows)


def main():
    parser = argparse.ArgumentParser(
        description="Monitor CPU/RAM berdasarkan ukuran payload ROS 2."
    )
    parser.add_argument(
        "--scenario",
        choices=["native", "docker"],
        required=True,
    )
    parser.add_argument(
        "--metric",
        choices=["cpu", "ram"],
        required=True,
    )
    parser.add_argument(
        "--payload",
        type=int,
        choices=[144, 256, 384],
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        default=str(
            Path.home() / "skripsi-experiments" / "data" / "payload"
        ),
    )

    args = parser.parse_args()

    rclpy.init()

    node = PayloadMonitor(
        args.scenario,
        args.metric,
        args.payload,
        args.output_dir,
    )

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\nPengukuran dihentikan secara manual.")
    finally:
        if rclpy.ok():
            rclpy.shutdown()
        node.destroy_node()


if __name__ == "__main__":
    main()
