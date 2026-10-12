import socket
import os
import sys

from protocol.protocol import (
    BUFFER_SIZE,
    MAX_FILENAME_SIZE,
    HEADER_SEPARATOR,
    MAX_HEADER_SIZE,
    SHA256_LENGTH,
    TRANSFER_SUCCESS,
    TRANSFER_FAILED,
)
from utils.checksum import calculate_sha256


# ============================================================
# COMMAND-LINE ARGUMENTS
# ============================================================

if len(sys.argv) > 4:
    print("Usage: python -m server.server [bind_ip] [port] [storage_dir]")
    print("Examples:")
    print("  python -m server.server")
    print("  python -m server.server 0.0.0.0 5000 backup/h2")
    sys.exit(1)

SERVER_IP = sys.argv[1] if len(sys.argv) >= 2 else "0.0.0.0"
STORAGE_FOLDER = sys.argv[3] if len(sys.argv) >= 4 else "backup/primary"

try:
    SERVER_PORT = int(sys.argv[2]) if len(sys.argv) >= 3 else 5000
except ValueError:
    print("ERROR: Port must be a valid number.")
    sys.exit(1)

os.makedirs(STORAGE_FOLDER, exist_ok=True)


# ============================================================
# HANDLE ONE CLIENT
# ============================================================

def receive_header(connection):
    header_data = b""
    while HEADER_SEPARATOR not in header_data:
        chunk = connection.recv(1)
        if not chunk:
            raise ConnectionError("Client disconnected before sending header.")
        header_data += chunk
        if len(header_data) > MAX_HEADER_SIZE:
            raise ValueError("Header is too large.")

    header_line = header_data.split(HEADER_SEPARATOR, 1)[0]
    parts = header_line.decode("utf-8").split("|")
    if len(parts) != 4:
        raise ValueError("Invalid header format.")

    filename_length = int(parts[0])
    filename = parts[1]
    file_size = int(parts[2])
    expected_hash = parts[3]

    if filename_length != len(filename.encode("utf-8")):
        raise ValueError("Filename length mismatch.")
    if filename_length == 0:
        raise ValueError("Filename cannot be empty.")
    if filename_length > MAX_FILENAME_SIZE:
        raise ValueError("Filename is too long.")
    if file_size < 0:
        raise ValueError("Invalid file size.")
    if len(expected_hash) != SHA256_LENGTH:
        raise ValueError("Invalid SHA-256 length.")
    try:
        int(expected_hash, 16)
    except ValueError:
        raise ValueError("Invalid SHA-256 value.")

    # Prevent path traversal
    filename = os.path.basename(filename)
    if not filename:
        raise ValueError("Invalid filename.")

    return filename, file_size, expected_hash


def handle_client(connection):
    part_path = None
    try:
        connection.settimeout(30)

        filename, file_size, expected_hash = receive_header(connection)

        final_path = os.path.join(STORAGE_FOLDER, filename)
        part_path = final_path + ".part"

        print(f"Filename       : {filename}")
        print(f"File size      : {file_size} bytes")
        print(f"Expected SHA256: {expected_hash}")
        print("\nReceiving file...")

        bytes_received = 0
        with open(part_path, "wb") as file:
            while bytes_received < file_size:
                chunk_size = min(BUFFER_SIZE, file_size - bytes_received)
                data = connection.recv(chunk_size)
                if not data:
                    raise ConnectionError("Client disconnected during file transfer.")
                file.write(data)
                bytes_received += len(data)

        print(f"✓ Received {bytes_received} bytes")

        actual_hash = calculate_sha256(part_path)
        print(f"Actual SHA256  : {actual_hash}")

        if actual_hash != expected_hash:
            print("✗ HASH MISMATCH - discarding file")
            os.remove(part_path)
            part_path = None
            connection.sendall(TRANSFER_FAILED)
            return

        # Only now does the file become a real backup
        os.replace(part_path, final_path)
        part_path = None

        connection.sendall(TRANSFER_SUCCESS)
        print("✓ INTEGRITY VERIFIED")
        print(f"✓ BACKUP STORED: {final_path}")

    except ValueError as error:
        print(f"ERROR: Invalid request: {error}")
        try:
            connection.sendall(TRANSFER_FAILED)
        except OSError:
            pass

    except ConnectionError as error:
        print(f"ERROR: Connection problem: {error}")

    except socket.timeout:
        print("ERROR: Client timed out.")

    except OSError as error:
        print(f"ERROR: File/Network error: {error}")
        try:
            connection.sendall(TRANSFER_FAILED)
        except OSError:
            pass

    finally:
        # Never leave a partial file that could look like a backup
        if part_path and os.path.exists(part_path):
            try:
                os.remove(part_path)
            except OSError:
                pass
        connection.close()
        print("\nClient connection closed.")
        print("Server is waiting for the next client...\n")


# ============================================================
# MAIN SERVER LOOP
# ============================================================

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((SERVER_IP, SERVER_PORT))
        server_socket.listen(5)

        print("=" * 60)
        print("TCP BACKUP SERVER")
        print("=" * 60)
        print(f"Listening on : {SERVER_IP}:{SERVER_PORT}")
        print(f"Storage      : {STORAGE_FOLDER}")
        print("\nServer is waiting for clients...\n")

        while True:
            connection, address = server_socket.accept()
            print("=" * 60)
            print(f"Client connected: {address[0]}:{address[1]}")
            handle_client(connection)

    except OSError as error:
        print(f"ERROR: Could not start server: {error}")
    except KeyboardInterrupt:
        print("\n\nServer stopped by user.")
    finally:
        server_socket.close()
        print("Server socket closed.")


if __name__ == "__main__":
    main()