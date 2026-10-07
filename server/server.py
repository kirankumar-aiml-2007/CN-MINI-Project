import socket
import os
import shutil
import sys

from protocol.protocol import (
    BUFFER_SIZE,
    MAX_FILENAME_SIZE,
    HEADER_SEPARATOR,
    MAX_HEADER_SIZE,
    SHA256_LENGTH,
    TRANSFER_SUCCESS,
    TRANSFER_FAILED
)

from utils.checksum import calculate_sha256


# ============================================================
# COMMAND-LINE ARGUMENTS
# ============================================================

if len(sys.argv) > 3:
    print("Usage:")
    print("python -m server.server [bind_ip] [port]")
    print()
    print("Examples:")
    print("python -m server.server")
    print("python -m server.server 127.0.0.1 5000")
    print("python -m server.server 0.0.0.0 5000")
    sys.exit(1)


# Default values
SERVER_IP = sys.argv[1] if len(sys.argv) >= 2 else "0.0.0.0"
SERVER_PORT = int(sys.argv[2]) if len(sys.argv) >= 3 else 5000


# ============================================================
# BACKUP DIRECTORIES
# ============================================================

PRIMARY_FOLDER = "backup/primary"
SECONDARY_FOLDER = "backup/secondary"

os.makedirs(PRIMARY_FOLDER, exist_ok=True)
os.makedirs(SECONDARY_FOLDER, exist_ok=True)


# ============================================================
# CREATE SERVER SOCKET
# ============================================================

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Allows quick restart after stopping the server
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

try:

    server_socket.bind((SERVER_IP, SERVER_PORT))

    server_socket.listen(5)

    print("=" * 60)
    print("TCP BACKUP SERVER")
    print("=" * 60)

    print(f"Listening on : {SERVER_IP}:{SERVER_PORT}")
    print(f"Primary      : {PRIMARY_FOLDER}")
    print(f"Secondary    : {SECONDARY_FOLDER}")

    print("\nServer is waiting for clients...\n")


    # ========================================================
    # PERSISTENT SERVER
    # ========================================================

    while True:

        connection, address = server_socket.accept()

        print("=" * 60)
        print(f"Client connected: {address[0]}:{address[1]}")


        try:

            connection.settimeout(30)


            # =================================================
            # RECEIVE HEADER
            # =================================================

            header_data = b""

            while HEADER_SEPARATOR not in header_data:

                chunk = connection.recv(1)

                if not chunk:
                    raise ConnectionError("Client disconnected before sending header.")

                header_data += chunk

                if len(header_data) > MAX_HEADER_SIZE:
                    raise ValueError("Header is too large.")


            header_line = header_data.split(HEADER_SEPARATOR, 1)[0]

            header = header_line.decode("utf-8")

            parts = header.split("|")

            if len(parts) != 4:
                raise ValueError("Invalid header format.")


            filename_length = int(parts[0])
            filename = parts[1]
            file_size = int(parts[2])
            expected_hash = parts[3]


            # =================================================
            # VALIDATE HEADER
            # =================================================

            actual_filename_length = len(filename.encode("utf-8"))

            if filename_length != actual_filename_length:
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

            primary_path = os.path.join(
                PRIMARY_FOLDER,
                filename
            )

            secondary_path = os.path.join(
                SECONDARY_FOLDER,
                filename
            )


            print(f"Filename       : {filename}")
            print(f"File size      : {file_size} bytes")
            print(f"Expected SHA256: {expected_hash}")


            # =================================================
            # RECEIVE FILE INTO PRIMARY BACKUP
            # =================================================

            bytes_received = 0

            print("\nReceiving file...")

            with open(primary_path, "wb") as file:

                while bytes_received < file_size:

                    remaining = file_size - bytes_received

                    chunk_size = min(BUFFER_SIZE, remaining)

                    data = connection.recv(chunk_size)

                    if not data:
                        raise ConnectionError(
                            "Client disconnected during file transfer."
                        )

                    file.write(data)

                    bytes_received += len(data)


            print(f"✓ Received {bytes_received} bytes")


            # =================================================
            # VERIFY PRIMARY BACKUP
            # =================================================

            print("\nVerifying primary backup...")

            primary_hash = calculate_sha256(primary_path)

            print(f"Primary SHA256 : {primary_hash}")

            if primary_hash != expected_hash:

                print("✗ PRIMARY HASH MISMATCH")

                connection.sendall(TRANSFER_FAILED)

                continue

            print("✓ PRIMARY HASH MATCH")


            # =================================================
            # CREATE SECONDARY BACKUP
            # =================================================

            print("\nCreating secondary backup...")

            shutil.copy2(
                primary_path,
                secondary_path
            )

            print("✓ Secondary copy created")


            # =================================================
            # VERIFY SECONDARY BACKUP
            # =================================================

            print("\nVerifying secondary backup...")

            secondary_hash = calculate_sha256(secondary_path)

            print(f"Secondary SHA256: {secondary_hash}")


            if secondary_hash != primary_hash:

                print("✗ SECONDARY HASH MISMATCH")

                connection.sendall(TRANSFER_FAILED)

                continue


            print("✓ SECONDARY HASH MATCH")


            # =================================================
            # FINAL SUCCESS
            # =================================================

            connection.sendall(TRANSFER_SUCCESS)

            print("\n✓ INTEGRITY VERIFIED")
            print("✓ PRIMARY BACKUP VERIFIED")
            print("✓ SECONDARY BACKUP VERIFIED")
            print("✓ BACKUP SUCCESSFUL")


        except ValueError as error:

            print(f"ERROR: Invalid request: {error}")

            try:
                connection.sendall(TRANSFER_FAILED)
            except OSError:
                pass


        except ConnectionError as error:

            print(f"ERROR: Connection problem: {error}")


        except OSError as error:

            print(f"ERROR: File/Network error: {error}")

            try:
                connection.sendall(TRANSFER_FAILED)
            except OSError:
                pass


        finally:

            connection.close()

            print("\nClient connection closed.")
            print("Server is waiting for the next client...\n")


except ValueError:

    print("ERROR: Port must be a valid number.")

except OSError as error:

    print(f"ERROR: Could not start server: {error}")

except KeyboardInterrupt:

    print("\n\nServer stopped by user.")

finally:

    server_socket.close()

    print("Server socket closed.")