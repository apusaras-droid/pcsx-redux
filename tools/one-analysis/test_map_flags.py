import unittest
from map_flags import analyze, decode


class MappingTests(unittest.TestCase):
    def test_unknown_does_not_resynchronize(self):
        result = analyze(bytes.fromhex('ff 68 03 01'))
        self.assertEqual(result['references'], [])
        self.assertEqual(result['stops'][0]['offset'], 0)

    def test_flag_write_and_truncation(self):
        self.assertEqual(decode(bytes.fromhex('68 89 02'), 0)[2][0]['value'], 0)
        result = analyze(bytes.fromhex('68 89'))
        self.assertFalse(result['references'])

    def test_condition_follows_both_edges(self):
        # 52: prefix, flag137, compare1, rhs0, terminator, false target12.
        data = bytes.fromhex('52 01 89 00 01 00 00 0c 00 68 03 01 68 04 00')
        result = analyze(data)
        self.assertEqual([(r['index'], r['access']) for r in result['references']],
                         [(137, 'read_condition'), (4, 'assign'), (3, 'assign')])
        self.assertFalse(result['stops'])

    def test_condition_groups_and_numeric_operand(self):
        data = bytes.fromhex('52 01 03 00 01 01 01 01 01 06 80 02 0a 00 10 00')
        end, edges, refs = decode(data, 0)
        self.assertEqual((end, edges), (16, [16, 16]))
        self.assertEqual([(r['kind'], r['index']) for r in refs], [('flag', 3), ('numeric', 6)])

    def test_loop_terminates(self):
        result = analyze(bytes.fromhex('68 03 01 50 00 00'))
        self.assertEqual(len(result['instructions']), 2)
        self.assertEqual(len(result['references']), 1)

    def test_text_bytes_not_instructions(self):
        data = b'\x10hABC\x81\x66\0\x68\x03\x01'
        result = analyze(data)
        self.assertEqual(len(result['references']), 1)
        self.assertEqual(result['references'][0]['offset'], 8)

    def test_overlap_withholds_references(self):
        data = bytes.fromhex('52 01 89 00 01 00 00 0a 00 68 68 00 00')
        result = analyze(data)
        self.assertTrue(result['overlap'])
        self.assertFalse(result['references'])


if __name__ == '__main__':
    unittest.main()
