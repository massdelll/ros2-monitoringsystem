
import csv
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = Path.home() / "skripsi-experiments"
DATA = BASE / "data" / "rate"
OUTPUT = BASE / "plots" / "rate"

RATES = [1, 2, 3]


def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def average_metric(environment, rate, metric):
    path = DATA / f"{metric}_{environment}_{rate}msgps_run{rate}.csv"

    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")

    rows = read_csv(path)
    values = [float(row[metric_column(metric)]) for row in rows]

    return mean(values)


def metric_column(metric):
    if metric == "cpu":
        return "cpu_usage_percent"
    return "ram_used_mib"


def make_chart(metric):
    native_values = [
        average_metric("native", rate, metric) for rate in RATES
    ]
    docker_values = [
        average_metric("docker", rate, metric) for rate in RATES
    ]

    plt.figure(figsize=(8, 5))
    plt.plot(RATES, native_values, marker="o", label="Native")
    plt.plot(RATES, docker_values, marker="o", label="Docker")

    plt.xlabel("Message Rate (pesan/detik)")

    if metric == "cpu":
        plt.ylabel("Rata-rata Utilisasi CPU (%)")
        plt.title("Perbandingan Rata-rata CPU berdasarkan Message Rate")
    else:
        plt.ylabel("Rata-rata RAM Terpakai (MiB)")
        plt.title("Perbandingan Rata-rata RAM berdasarkan Message Rate")

    plt.xticks(RATES)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    filename = OUTPUT / f"{metric}_native_vs_docker_rate.png"
    plt.savefig(filename, dpi=300)
    plt.close()

    print(f"Diagram tersimpan: {filename}")

    for rate, native, docker in zip(RATES, native_values, docker_values):
        print(
            f"{rate} pesan/detik | "
            f"Native={native:.2f} | Docker={docker:.2f}"
        )


if __name__ == "__main__":
    make_chart("cpu")
    make_chart("ram")

