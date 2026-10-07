import socket
import os
import time
import sys

from protocol.protocol import (
    BUFFER_SIZE,
    MAX_FILENAME_SIZE,
    HEADER_SEPARATOR,
    TRANSFER_SUCCESS,
    TRANSFER_FAILED
)

from utils.checksum import calculate_sha256


# ============================================================
# COMMAND-LINE ARGUMENTS
# ============================================================

if len(sys.argv) < 2 or len(sys.argv) > 4:
    print("Usage:")
    print("python -m client.client <file_path> [server_ip] [port]")
    print()
    print("Examples:")
    print("python -m client.client tests/test_small.txt")
    print("python -m client.client tests/test_10mb.bin 127.0.0.1 5000")
    print("python -m client.client tests/test_10mb.bin 192.168.1.10 5000")
    sys.exit(1)


FILE_PATH = sys.argv[1]

# Default values
SERVER_IP = sys.argv[2] if len(sys.argv) >= 3 else "127.0.0.1"
SERVER_PORT = int(sys.argv[3]) if len(sys.argv) >= 4 else 5000


# ============================================================
# FILE VALIDATION
# ============================================================

if not os.path.isfile(FILE_PATH):
    print(f"ERROR: File not found: {FILE_PATH}")
    sys.exit(1)


filename = os.path.basename(FILE_PATH)

if len(filename.encode("utf-8")) > MAX_FILENAME_SIZE:
    print("ERROR: Filename is too long.")
    sys.exit(1)


file_size = os.path.getsize(FILE_PATH)


# ============================================================
# CALCULATE ORIGINAL SHA-256
# ============================================================

try:
    original_hash = calculate_sha256(FILE_PATH)
except OSError as error:
    print(f"ERROR: Could not read file: {error}")
    sys.exit(1)


print("=" * 60)
print("TCP FILE BACKUP CLIENT")
print("=" * 60)

print(f"File path : {FILE_PATH}")
print(f"File name : {filename}")
print(f"File size : {file_size} bytes")
print(f"SHA-256   : {original_hash}")
print(f"Server    : {SERVER_IP}:{SERVER_PORT}")


# ============================================================
# CONNECT TO SERVER
# ============================================================

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    client_socket.settimeout(30)

    print("\nConnecting to backup server...")

    client_socket.connect((SERVER_IP, SERVER_PORT))

    print("✓ Connected to server")


    # ========================================================
    # CREATE APPLICATION HEADER
    # ========================================================

    filename_bytes = filename.encode("utf-8")

    header = (
        str(len(filename_bytes))
        + "|"
        + filename
        + "|"
        + str(file_size)
        + "|"
        + original_hash
    ).encode("utf-8") + HEADER_SEPARATOR


    # ========================================================
    # SEND HEADER
    # ========================================================

    client_socket.sendall(header)

    print("✓ File information sent")


    # ========================================================
    # SEND FILE DATA
    # ========================================================

    bytes_sent = 0

    start_time = time.perf_counter()

    with open(FILE_PATH, "rb") as file:

        while True:

            data = file.read(BUFFER_SIZE)

            if not data:
                break

            client_socket.sendall(data)

            bytes_sent += len(data)


    # ========================================================
    # TRANSFER PERFORMANCE
    # ========================================================

    end_time = time.perf_counter()

    transfer_time = end_time - start_time

    if transfer_time > 0:
        speed = (bytes_sent / (1024 * 1024)) / transfer_time
    else:
        speed = 0


    print(f"✓ File sent successfully")
    print(f"  Bytes sent     : {bytes_sent}")
    print(f"  Transfer time  : {transfer_time:.4f} seconds")
    print(f"  Transfer speed : {speed:.2f} MB/s")


    # ========================================================
    # SIGNAL END OF TRANSMISSION
    # ========================================================

    client_socket.shutdown(socket.SHUT_WR)


    # ========================================================
    # RECEIVE SERVER RESPONSE
    # ========================================================

    response = client_socket.recv(1024)

    if response == TRANSFER_SUCCESS:

        print("\n✓ INTEGRITY VERIFIED")
        print("✓ BACKUP SUCCESSFUL")

    elif response == TRANSFER_FAILED:

        print("\n✗ BACKUP FAILED")

    else:

        print("\nERROR: Unknown server response.")


except FileNotFoundError:

    print("ERROR: File not found.")

except ConnectionRefusedError:

    print("ERROR: Backup server is not running.")

except socket.timeout:

    print("ERROR: Connection timed out.")

except ConnectionResetError:

    print("ERROR: Server connection was reset.")

except OSError as error:

    print(f"ERROR: Network/File error: {error}")

finally:

    client_socket.close()

    print("\nConnection closed.")