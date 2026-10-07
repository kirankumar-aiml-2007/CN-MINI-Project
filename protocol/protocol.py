# ============================================================
# TCP BACKUP SYSTEM
# PROTOCOL MODULE
# ============================================================

# Maximum file data per TCP send/receive operation
BUFFER_SIZE = 4096

# Maximum filename size
MAX_FILENAME_SIZE = 255

# End of header marker
HEADER_SEPARATOR = b"\n"

# Maximum complete header size
MAX_HEADER_SIZE = 1024

# SHA-256 produces 64 hexadecimal characters
SHA256_LENGTH = 64

# Server responses
TRANSFER_SUCCESS = b"FILE_RECEIVED"
TRANSFER_FAILED = b"TRANSFER_FAILED"