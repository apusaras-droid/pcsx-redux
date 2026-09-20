"""Survey the studied ONE SLPS-01972 disc; retain evidence locally as JSON.

Table addresses are revision-specific. A valid row is a candidate, not proof
that it is reachable in gameplay or that its label describes its full meaning.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path
from disc import Disc
from lzss import decompress


def survey(image):
    disc = Disc(image)
    try:
        entries = disc.inventory()
        executable = next(e for e in entries if e['name'] == 'SLPS_019.72;1')
        exe = disc.read(executable['lba'], executable['size'])
        if exe[:8] != b'PS-X EXE':
            raise ValueError('Not a PS-X executable')
        base, size = struct.unpack_from('<II', exe, 24)

        def at(address, length):
            offset = address - base
            if offset < 0 or offset + length > min(size, len(exe) - 2048):
                raise ValueError('Pointer outside executable payload')
            return exe[2048 + offset:2048 + offset + length]

        def string_pointer(table, index):
            ptr = struct.unpack('<I', at(table + index * 4, 4))[0]
            raw = bytearray()
            for offset in range(64):
                value = at(ptr + offset, 1)[0]
                if not value:
                    return raw.decode('ascii')
                raw.append(value)
            raise ValueError('Unterminated string')

        rows, stop = [], '256-index limit'
        for index in range(256):
            try:
                name = string_pointer(0x80061F98, index)
                locator = string_pointer(0x8005DD88, index)
                if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,31}', name) or not re.fullmatch(r'\d{7,10}', locator):
                    raise ValueError('Not a label/location row')
                minute, second, frame = (int(locator[i:i + 2]) for i in (0, 2, 4))
                sectors = int(locator[6:])
                if second >= 60 or frame >= 75 or not 1 <= sectors <= 512:
                    raise ValueError('Invalid position/length')
                lba = (minute * 60 + second) * 75 + frame - 150
                owner = next((e for e in entries if not e['flags'] & 2 and e['lba'] <= lba
                              and (lba - e['lba'] + sectors) * 2048 <= e['size']), None)
                data = disc.read(lba, sectors * 2048)
                row = dict(index=index, label=name, locator=locator, lba=lba, read_sectors=sectors,
                           container=owner['path'] if owner else None,
                           container_offset=hex((lba - owner['lba']) * 2048) if owner else None)
                try:
                    expanded = decompress(data)
                    row.update(expanded_bytes=len(expanded), expanded_sha256=hashlib.sha256(expanded).hexdigest())
                except ValueError as error:
                    row['decode_error'] = str(error)
                rows.append(row)
            except (ValueError, UnicodeError) as error:
                stop = f'Index {index}: {error}; table extent is not proven'
                break

        strings = []
        for match in re.finditer(rb'[\x20-\x7e]{6,}', exe[2048:]):
            text = match.group().decode('ascii')
            if re.search(r'SCENARIO|\.(str|xa|bin)|\$Id:|error|debug', text, re.I):
                strings.append(dict(address=hex(base + match.start()), text=text))
        pvd = disc.read(16, 2048)
        metadata = {key: pvd[start:end].decode('ascii', errors='replace').rstrip(' \0')
                    for key, start, end in [('system', 8, 40), ('volume', 40, 72),
                                           ('publisher', 318, 446), ('preparer', 446, 574),
                                           ('application', 574, 702), ('created_raw', 813, 830)]}
        samples = []
        for entry in entries:
            if entry['flags'] & 2:
                continue
            positions = sorted(set([entry['lba'], entry['lba'] + max(0, (entry['size'] - 1) // 2048)]))
            for lba in positions:
                disc.file.seek(lba * 2352)
                raw = disc.file.read(2352)
                samples.append(dict(path=entry['path'], lba=lba, subheader=raw[16:24].hex(),
                                    payload_prefix=raw[24:56].hex()))
        return dict(metadata=metadata, inventory=entries, candidate_scenarios=rows,
                    table_scan_stop=stop, executable_strings=strings, sector_samples=samples,
                    limitations='Fixed executable table addresses; samples do not classify whole files; labels do not prove intent.')
    finally:
        disc.file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = survey(args.image)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(f"{len(result['candidate_scenarios'])} candidate rows; {result['table_scan_stop']}")


if __name__ == '__main__':
    main()
