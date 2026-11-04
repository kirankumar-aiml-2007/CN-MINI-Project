
import hashlib
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests" / "test_10mb.bin"


def get_free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_server(process, port):
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("Backup server stopped unexpectedly.")

        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)

    raise TimeoutError("Backup server did not start.")


def calculate_hash(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        while chunk := file.read(4096):
            digest.update(chunk)

    return digest.hexdigest()


def main():
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Test file not found: {SOURCE}")

    port = get_free_port()

    with tempfile.TemporaryDirectory() as temp:
        storage = Path(temp) / "backup"

        server = subprocess.Popen(
            [
                sys.executable, "-m", "server.server",
                "127.0.0.1", str(port), str(storage)
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        try:
            wait_for_server(server, port)

            result = subprocess.run(
                [
                    sys.executable, "-m", "client.client",
                    str(SOURCE), f"127.0.0.1:{port}"
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=180
            )

            print(result.stdout)

            if result.returncode != 0:
                print(result.stderr)
                raise RuntimeError("Large file transfer failed.")

            received = storage / SOURCE.name

            if not received.is_file():
                raise RuntimeError("Backup file was not created.")

            if calculate_hash(SOURCE) != calculate_hash(received):
                raise RuntimeError("File integrity verification failed.")

            print("SUCCESS: Large file transfer verified.")

        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
