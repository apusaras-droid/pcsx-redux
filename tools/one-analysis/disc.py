"""Read a single-track MODE2/2352 ISO9660 image without modifying it."""
import argparse
import json
import struct
from pathlib import Path


class Disc:
    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open('rb')
        self.sectors = self.path.stat().st_size // 2352
        pvd = self.read(16, 2048)
        if pvd[:7] != b'\x01CD001\x01':
            raise ValueError('Expected an ISO9660 PVD at LBA 16 in MODE2/2352')
        if struct.unpack_from('<H', pvd, 128)[0] != 2048:
            raise ValueError('Unsupported logical block size')
        self.root = self.record(pvd[156:])

    def read(self, lba, size):
        if lba < 0 or size < 0 or lba + (size + 2047) // 2048 > self.sectors:
            raise ValueError('Read outside image')
        result = bytearray()
        for sector in range(lba, lba + (size + 2047) // 2048):
            self.file.seek(sector * 2352)
            raw = self.file.read(2352)
            if len(raw) != 2352 or raw[15] != 2:
                raise ValueError(f'Not a MODE2 sector: {sector}')
            # Return the first 2048 data bytes, as needed for ISO directory and
            # ordinary Form1 files. XA/Form2 media require a separate decoder.
            result.extend(raw[24:2072])
        return bytes(result[:size])

    @staticmethod
    def record(data):
        if len(data) < 34 or data[0] < 34 or data[32] + 33 > data[0]:
            raise ValueError('Malformed directory record')
        lba, size = struct.unpack_from('<I', data, 2)[0], struct.unpack_from('<I', data, 10)[0]
        if lba != struct.unpack_from('>I', data, 6)[0] or size != struct.unpack_from('>I', data, 14)[0]:
            raise ValueError('Inconsistent ISO endian fields')
        return {'lba': lba, 'size': size, 'flags': data[25], 'name': data[33:33 + data[32]].decode('ascii')}

    def inventory(self):
        entries, visited = [], set()

        def visit(directory, parent):
            key = directory['lba']
            if key in visited:
                raise ValueError('Repeated directory extent')
            visited.add(key)
            data = self.read(key, directory['size'])
            offset = 0
            while offset < len(data):
                length = data[offset]
                if length == 0:
                    offset = ((offset // 2048) + 1) * 2048
                    continue
                if offset + length > len(data):
                    raise ValueError('Truncated directory')
                entry = self.record(data[offset:offset + length])
                offset += length
                if entry['name'] in ('\0', '\1'):
                    continue
                entry['path'] = parent + '/' + entry['name']
                entries.append(entry)
                if entry['flags'] & 2:
                    visit(entry, entry['path'])
        visit(self.root, '')
        return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    disc = Disc(args.image)
    try:
        entries = disc.inventory()
    finally:
        disc.file.close()
    args.output.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(entries)} ISO entries written to {args.output}')


if __name__ == '__main__':
    main()
