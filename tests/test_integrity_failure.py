
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get_free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_server(process, port):
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("Server stopped unexpectedly.")

        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)

    raise TimeoutError("Server did not start.")


def main():
    port = get_free_port()
    filename = "integrity_test.txt"
    payload = b"This file must fail integrity verification."

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

            with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
                wrong_hash = "0" * 64

                header = (
                    f"{len(filename.encode())}|{filename}|"
                    f"{len(payload)}|{wrong_hash}\n"
                ).encode()

                sock.sendall(header)
                sock.sendall(payload)
                sock.shutdown(socket.SHUT_WR)

                response = b""
                while len(response) < len(b"TRANSFER_FAILED"):
                    data = sock.recv(1024)
                    if not data:
                        break
                    response += data

            if response != b"TRANSFER_FAILED":
                raise RuntimeError(f"Unexpected server response: {response!r}")

            if (storage / filename).exists():
                raise RuntimeError("Invalid file was stored.")

            if (storage / (filename + ".part")).exists():
                raise RuntimeError("Temporary file was not deleted.")

            print("SUCCESS: Invalid file rejected.")
            print("SUCCESS: Temporary file deleted.")

        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
