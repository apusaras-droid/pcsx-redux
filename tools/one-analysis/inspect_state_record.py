"""Read the observed ONE state record in a 2 MiB RAM dump (not a card image)."""
import argparse
import json
import struct
from pathlib import Path


def inspect(ram):
    if len(ram) != 2 * 1024 * 1024:
        raise ValueError('Expected 2 MiB RAM; memory-card images are not supported')
    record = ram[0x1B3110:0x1B3190]
    flags = record[0x28:0x3A]
    stored = struct.unpack_from('<H', record, 0x7C)[0]
    calculated = sum(record[:0x6D]) & 0xFFFF
    return {
        'record_address': '0x801b3110', 'record_bytes': 128,
        'numeric_variables': list(record[:20]),
        'flag_bytes_hex': flags.hex(),
        'set_flag_indices': [i for i in range(144) if flags[i >> 3] & (1 << (i & 7))],
        'checksum_stored': stored, 'checksum_calculated': calculated,
        'checksum_matches': stored == calculated,
        'numeric_matches_live_ram': record[:20] == ram[0xFA840:0xFA854],
        'flags_match_live_ram': flags == ram[0xFA808:0xFA81A],
        'limitations': 'Internal snapshot only; unknown fields retained in RAM. Matching a checksum does not prove a valid card save. Live state may have advanced since snapshot.'
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ram', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = inspect(args.ram.read_bytes())
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
