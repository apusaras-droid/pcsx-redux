"""Extract ONE Disc 1's observed opening scenario and compare it with a RAM dump.

Offsets apply only to the studied SLPS-01972 image. No game data is bundled.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from disc import Disc
from lzss import decompress

RESOURCE_OFFSET = 0x229000
RAM_OFFSET = 0xEA728


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('ram', type=Path)
    parser.add_argument('output', type=Path, help='New directory for local artifacts')
    args = parser.parse_args()
    ram = args.ram.read_bytes()
    if len(ram) != 2 * 1024 * 1024:
        raise ValueError('Expected a 2 MiB RAM dump')
    disc = Disc(args.image)
    try:
        entry = next(e for e in disc.inventory() if e['path'] == '/DATA.BIN;1')
        if RESOURCE_OFFSET + 4 > entry['size']:
            raise ValueError('Resource outside DATA.BIN')
        lba = entry['lba'] + RESOURCE_OFFSET // 2048
        header = disc.read(lba, 4)
        size = struct.unpack('<I', header)[0]
        if not 4 <= size <= min(1024 * 1024, entry['size'] - RESOURCE_OFFSET):
            raise ValueError('Unexpected compressed resource size')
        compressed = disc.read(lba, size)
    finally:
        disc.file.close()
    expanded = decompress(compressed, len(ram) - RAM_OFFSET)
    if not expanded:
        raise ValueError('Empty resource')
    observed = ram[RAM_OFFSET:RAM_OFFSET + len(expanded)]
    report = {
        'disc_file': '/DATA.BIN;1', 'file_offset': hex(RESOURCE_OFFSET),
        'lba': lba, 'ram_address': hex(0x80000000 + RAM_OFFSET),
        'decompressor_pc': '0x80020340',
        'compressed_bytes': len(compressed), 'expanded_bytes': len(expanded),
        'compressed_sha256': hashlib.sha256(compressed).hexdigest(),
        'expanded_sha256': hashlib.sha256(expanded).hexdigest(),
        'ram_region_sha256': hashlib.sha256(observed).hexdigest(),
        'ram_matches': expanded == observed,
        'scope': 'One opening scenario resource; not a complete script interpreter',
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'scenario.bin').write_bytes(expanded)
    (args.output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not report['ram_matches']:
        raise SystemExit('RAM mismatch: use the observed opening checkpoint and matching disc revision')


if __name__ == '__main__':
    main()
