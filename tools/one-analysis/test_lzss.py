import struct
import unittest

from lzss import decompress


def stream(payload):
    return struct.pack('<I', len(payload) + 4) + payload


class DecoderTests(unittest.TestCase):
    def test_literals_and_partial_flag_group(self):
        self.assertEqual(decompress(stream(b'\xffABC')), b'ABC')

    def test_overlapping_reference(self):
        self.assertEqual(decompress(stream(b'\x01A\xee\xf2')), b'AAAAAA')

    def test_initial_zero_window(self):
        self.assertEqual(decompress(stream(b'\x00\x00\x00')), bytes(3))

    def test_ring_wrap(self):
        payload = b''.join(b'\xff' + bytes(range(i, i + 8)) for i in (0, 8, 16))
        self.assertEqual(decompress(stream(payload + b'\x00\x00\x00')), bytes(range(24)) + bytes((18, 19, 20)))

    def test_limits_and_unknown_scratch(self):
        for data in (b'', struct.pack('<I', 100), stream(b'\0\xee\xf0')):
            with self.assertRaises(ValueError):
                decompress(data)
        with self.assertRaises(ValueError):
            decompress(stream(b'\xffAB'), max_output=1)

    def test_incomplete_reference_matches_original_return(self):
        self.assertEqual(decompress(stream(b'\0\x12')), b'')


if __name__ == '__main__':
    unittest.main()
