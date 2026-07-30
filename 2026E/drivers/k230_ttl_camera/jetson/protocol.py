"""K230 TTL JPEG protocol V2 — single source of truth (CPython + MicroPython).

Header (little-endian), fixed 40 bytes:
  MAGIC(4s) VERSION(B) STATUS(B) HEADER_LENGTH(H)
  SESSION_ID(I) REQUEST_ID(I) FRAME_ID(I) CAPTURE_TIMESTAMP_MS(I)
  WIDTH(H) HEIGHT(H) JPEG_LENGTH(I) CRC32(I)
  CAPTURE_MS(H) ENCODE_MS(H)
"""

try:
    import ustruct as struct
except ImportError:
    import struct

try:
    from ubinascii import crc32 as _crc32
except ImportError:
    try:
        from binascii import crc32 as _crc32
    except ImportError:
        import zlib

        def _crc32(data, value=0):
            return zlib.crc32(data, value) & 0xFFFFFFFF

# Fixed production parameters (do not fork at runtime)
PROTOCOL_VERSION = 2
MAGIC_JPG = b"KJPG"
WIDTH = 1280
HEIGHT = 720
JPEG_QUALITY = 65
BAUDRATE = 460800
UART_TX_PIN = 50
UART_RX_PIN = 51
DISCARD_FRAMES = 2
CHUNK_SIZE = 4096
MAX_JPEG_BYTES = 2 * 1024 * 1024

DEFAULT_TTL_BY_ID = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A028646-if00"
TTL_VID = 0x1A86
TTL_PID = 0x55D3

STATUS_OK = 0
STATUS_BAD_COMMAND = 1
STATUS_BAD_ARGUMENT = 2
STATUS_CAMERA_NOT_READY = 3
STATUS_CAPTURE_FAILED = 4
STATUS_JPEG_ENCODE_FAILED = 5
STATUS_INTERNAL_ERROR = 6
STATUS_SEND_FAILED = 7

JPG_HEADER_STRUCT = "<4sBBHIIIIHHIIHH"
JPG_HEADER_SIZE = struct.calcsize(JPG_HEADER_STRUCT)

assert JPG_HEADER_SIZE == 40, JPG_HEADER_SIZE
assert PROTOCOL_VERSION == 2


def crc32(data):
    if not data:
        return 0
    return _crc32(data) & 0xFFFFFFFF


def format_request_id(request_id):
    return "%08d" % (int(request_id) & 0xFFFFFFFF)


def parse_request_id(token):
    return int(str(token).strip(), 10)


def pack_jpg_header(
    status,
    session_id,
    request_id,
    frame_id,
    capture_timestamp_ms,
    jpeg_length,
    jpeg_crc,
    capture_ms,
    encode_ms,
    width=WIDTH,
    height=HEIGHT,
):
    return struct.pack(
        JPG_HEADER_STRUCT,
        MAGIC_JPG,
        PROTOCOL_VERSION,
        int(status) & 0xFF,
        JPG_HEADER_SIZE,
        int(session_id) & 0xFFFFFFFF,
        int(request_id) & 0xFFFFFFFF,
        int(frame_id) & 0xFFFFFFFF,
        int(capture_timestamp_ms) & 0xFFFFFFFF,
        int(width) & 0xFFFF,
        int(height) & 0xFFFF,
        int(jpeg_length) & 0xFFFFFFFF,
        int(jpeg_crc) & 0xFFFFFFFF,
        int(capture_ms) & 0xFFFF,
        int(encode_ms) & 0xFFFF,
    )


def unpack_jpg_header(buf):
    if len(buf) < JPG_HEADER_SIZE:
        raise ValueError("short header")
    (
        magic,
        ver,
        status,
        hdr_len,
        session_id,
        request_id,
        frame_id,
        capture_ts,
        width,
        height,
        jpeg_len,
        crc,
        capture_ms,
        encode_ms,
    ) = struct.unpack(JPG_HEADER_STRUCT, buf[:JPG_HEADER_SIZE])
    return {
        "magic": magic,
        "version": ver,
        "status": status,
        "header_length": hdr_len,
        "session_id": session_id,
        "request_id": request_id,
        "frame_id": frame_id,
        "capture_timestamp_ms": capture_ts,
        "width": width,
        "height": height,
        "jpeg_length": jpeg_len,
        "crc32": crc,
        "capture_ms": capture_ms,
        "encode_ms": encode_ms,
    }
