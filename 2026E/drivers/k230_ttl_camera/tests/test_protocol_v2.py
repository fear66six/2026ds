#!/usr/bin/env python3
"""Protocol V2 unit tests (no hardware)."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "jetson"))
sys.path.insert(0, str(HERE))

from protocol import (  # noqa: E402
    JPG_HEADER_SIZE,
    JPG_HEADER_STRUCT,
    MAGIC_JPG,
    PROTOCOL_VERSION,
    WIDTH,
    HEIGHT,
    crc32,
    pack_jpg_header,
    unpack_jpg_header,
)


class ProtocolV2Tests(unittest.TestCase):
    def test_header_size(self):
        self.assertEqual(JPG_HEADER_SIZE, 40)
        self.assertEqual(struct.calcsize(JPG_HEADER_STRUCT), 40)

    def test_roundtrip(self):
        payload = b"\xff\xd8" + bytes(range(256)) * 4
        c = crc32(payload)
        hdr = pack_jpg_header(0, 9, 7, 3, 123456, len(payload), c, 11, 22)
        self.assertEqual(len(hdr), 40)
        meta = unpack_jpg_header(hdr)
        self.assertEqual(meta["magic"], MAGIC_JPG)
        self.assertEqual(meta["version"], PROTOCOL_VERSION)
        self.assertEqual(meta["session_id"], 9)
        self.assertEqual(meta["request_id"], 7)
        self.assertEqual(meta["frame_id"], 3)
        self.assertEqual(meta["capture_timestamp_ms"], 123456)
        self.assertEqual(meta["width"], WIDTH)
        self.assertEqual(meta["height"], HEIGHT)
        self.assertEqual(meta["jpeg_length"], len(payload))
        self.assertEqual(meta["crc32"], c)
        self.assertEqual(meta["capture_ms"], 11)
        self.assertEqual(meta["encode_ms"], 22)

    def test_endian_little(self):
        hdr = pack_jpg_header(0, 0x01020304, 0x0A0B0C0D, 1, 2, 3, 4, 5, 6)
        # request_id at offset: 4+1+1+2+4 = 12
        self.assertEqual(hdr[12:16], bytes([0x0D, 0x0C, 0x0B, 0x0A]))

    def test_bad_crc_detect(self):
        payload = b"\xff\xd8abc"
        hdr = pack_jpg_header(0, 1, 1, 1, 1, len(payload), crc32(payload), 1, 1)
        meta = unpack_jpg_header(hdr)
        self.assertNotEqual(crc32(payload + b"x"), meta["crc32"])

    def test_short_header(self):
        with self.assertRaises(ValueError):
            unpack_jpg_header(b"KJPG" + b"\x00" * 10)

    def test_find_magic_amid_garbage(self):
        payload = b"\xff\xd8" + b"\x00" * 10
        c = crc32(payload)
        hdr = pack_jpg_header(0, 1, 2, 3, 4, len(payload), c, 1, 1)
        stream = b"xxxxHELLO" + hdr + payload
        idx = stream.find(MAGIC_JPG)
        self.assertGreaterEqual(idx, 0)
        meta = unpack_jpg_header(stream[idx : idx + JPG_HEADER_SIZE])
        self.assertEqual(meta["request_id"], 2)
        jpeg = stream[idx + JPG_HEADER_SIZE : idx + JPG_HEADER_SIZE + meta["jpeg_length"]]
        self.assertEqual(crc32(jpeg), meta["crc32"])

    def test_chunked_reassembly(self):
        payload = bytes([i % 256 for i in range(5000)])
        c = crc32(payload)
        hdr = pack_jpg_header(0, 1, 1, 1, 1, len(payload), c, 1, 1)
        blob = hdr + payload
        # simulate short reads
        chunks = [blob[i : i + 137] for i in range(0, len(blob), 137)]
        reasm = b"".join(chunks)
        self.assertEqual(reasm, blob)
        meta = unpack_jpg_header(reasm[:JPG_HEADER_SIZE])
        self.assertEqual(meta["width"], 1280)
        self.assertEqual(meta["height"], 720)

    def test_illegal_status_field(self):
        hdr = pack_jpg_header(6, 1, 1, 1, 1, 0, 0, 0, 0)
        meta = unpack_jpg_header(hdr)
        self.assertEqual(meta["status"], 6)

    def test_wrong_wh_in_header(self):
        hdr = pack_jpg_header(0, 1, 1, 1, 1, 10, 0, 0, 0, width=640, height=480)
        meta = unpack_jpg_header(hdr)
        self.assertEqual(meta["width"], 640)
        self.assertNotEqual(meta["width"], WIDTH)

    def test_max_jpeg_bound_constant(self):
        from protocol import MAX_JPEG_BYTES

        self.assertEqual(MAX_JPEG_BYTES, 2 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
