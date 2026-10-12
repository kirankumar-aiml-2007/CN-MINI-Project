import socket
import os
import time
import sys

from protocol.protocol import (
    BUFFER_SIZE,
    MAX_FILENAME_SIZE,
    HEADER_SEPARATOR,
    TRANSFER_SUCCESS,
    TRANSFER_FAILED,
)
from utils.checksum import calculate_sha256


def parse_servers(args):
    """Turn ['10.0.0.2:5000', '10.0.0.3'] into [(ip, port), ...]."""
    servers = []
    for a in args:
        ip, _, port = a.partition(":")
        servers.append((ip, int(port) if port else 5000))
    return servers


def send_to_server(file_path, filename, file_size, file_hash, ip, port):
    """Send the file to one server. Returns (success, speed_MBps, message)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(30)
        sock.connect((ip, port))

        name_bytes = filename.encode("utf-8")
        header = (
            f"{len(name_bytes)}|{filename}|{file_size}|{file_hash}"
        ).encode("utf-8") + HEADER_SEPARATOR
        sock.sendall(header)

        sent = 0
        start = time.perf_counter()
        with open(file_path, "rb") as f:
            while True:
                data = f.read(BUFFER_SIZE)
                if not data:
                    break
                sock.sendall(data)
                sent += len(data)
                
        elapsed = time.perf_counter() - start
        speed = (sent / (1024 * 1024)) / elapsed if elapsed > 0 else 0

        sock.shutdown(socket.SHUT_WR)
        response = sock.recv(1024)

        if response == TRANSFER_SUCCESS:
            return True, speed, "stored and verified"
        if response == TRANSFER_FAILED:
            return False, speed, "server reported checksum failure"
        return False, speed, "unknown server response"

    except ConnectionRefusedError:
        return False, 0, "server not running"
    except socket.timeout:
        return False, 0, "connection timed out"
    except ConnectionResetError:
        return False, 0, "connection reset"
    except OSError as e:
        return False, 0, f"network/file error: {e}"
    finally:
        sock.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m client.client <file_path> [ip:port ...]")
        print("Examples:")
        print("  python -m client.client tests/test_small.txt")
        print("  python -m client.client tests/test_small.txt 10.0.0.2:5000 10.0.0.3:5000")
        sys.exit(1)

    file_path = sys.argv[1]

    try:
        servers = parse_servers(sys.argv[2:]) or [("127.0.0.1", 5000)]
    except ValueError:
        print("ERROR: Server must be written as ip:port (port must be a number).")
        sys.exit(1)

    if not os.path.isfile(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    filename = os.path.basename(file_path)
    if len(filename.encode("utf-8")) > MAX_FILENAME_SIZE:
        print("ERROR: Filename is too long.")
        sys.exit(1)

    file_size = os.path.getsize(file_path)

    try:
        file_hash = calculate_sha256(file_path)  # computed once, reused for all servers
    except OSError as error:
        print(f"ERROR: Could not read file: {error}")
        sys.exit(1)

    print("=" * 60)
    print("TCP FILE BACKUP CLIENT (replicating)")
    print("=" * 60)
    print(f"File    : {file_path} ({file_size} bytes)")
    print(f"SHA-256 : {file_hash}")
    print(f"Servers : {', '.join(f'{ip}:{p}' for ip, p in servers)}\n")

    results = []
    for ip, port in servers:
        print(f"-> Sending to {ip}:{port} ...")
        ok, speed, msg = send_to_server(file_path, filename, file_size, file_hash, ip, port)
        results.append((ip, port, ok, speed, msg))
        print(f"   {'✓' if ok else '✗'} {msg} ({speed:.2f} MB/s)\n")

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for ip, port, ok, speed, msg in results:
        print(f"{ip}:{port:<6} {'OK  ' if ok else 'FAIL'}  {msg}")

    succeeded = sum(1 for r in results if r[2])
    print(f"\n{succeeded}/{len(results)} backups verified")
    sys.exit(0 if succeeded == len(results) else 1)


if __name__ == "__main__":
    main()