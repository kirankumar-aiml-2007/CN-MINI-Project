
import csv
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "benchmarks.csv"
RUNS = 3


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 tests/run_benchmarks.py <file> <mode> <ip:port> [...]")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    mode = sys.argv[2]
    servers = sys.argv[3:]

    if not file_path.is_file():
        print(f"File not found: {file_path}")
        sys.exit(1)

    file_size = file_path.stat().st_size
    RESULTS.parent.mkdir(parents=True, exist_ok=True)

    new_file = not RESULTS.exists()

    with open(RESULTS, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)

        if new_file:
            writer.writerow([
                "Date", "Mode", "File", "Size_Bytes",
                "Run", "Time_Seconds", "Throughput_MBps", "Status"
            ])

        for run in range(1, RUNS + 1):
            command = [
                sys.executable, "-m", "client.client",
                str(file_path), *servers
            ]

            start = time.perf_counter()

            try:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                elapsed = time.perf_counter() - start
                success = result.returncode == 0

            except subprocess.TimeoutExpired:
                elapsed = 300
                success = False
                result = None

            throughput = (
                (file_size * len(servers)) / (1024 * 1024 * elapsed)
                if elapsed > 0 and success else 0
            )

            status = "SUCCESS" if success else "FAILED"

            writer.writerow([
                datetime.now().astimezone().isoformat(timespec="seconds"),
                mode,
                file_path.name,
                file_size,
                run,
                round(elapsed, 3),
                round(throughput, 3),
                status
            ])
            csvfile.flush()

            print(f"Run {run}: {status}")
            print(f"Time: {elapsed:.3f} seconds")
            print(f"Aggregate throughput: {throughput:.3f} MB/s")

            if result:
                print(result.stdout)

            if not success:
                print("Benchmark stopped because transfer failed.")
                sys.exit(1)

    print(f"Results saved to: {RESULTS}")


if __name__ == "__main__":
    main()
