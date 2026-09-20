"""Extract surveyed resources and conservatively map reachable known instructions.

Unknown commands stop that path. Never resynchronize by searching for opcode
bytes inside unparsed data. Save offsets refer to the internal 128-byte record.
"""
import argparse
import collections
import csv
import hashlib
import json
import struct
from pathlib import Path
from disc import Disc
from lzss import decompress


def decode(data, pos):
    def require(end):
        if end > len(data):
            raise ValueError('Truncated instruction')
    require(pos + 1)
    op = data[pos]
    refs = []
    if op == 0x30:
        require(pos + 5)
        return pos + 5, [pos + 5], refs
    if op in (0x28, 0x31, 0x85):
        require(pos + 4)
        return pos + 4, [pos + 4], refs
    if op in (0x60, 0x61, 0x62, 0x68, 0x80):
        require(pos + 3)
        index, value = data[pos + 1:pos + 3]
        if op != 0x80:
            refs.append(dict(kind='flag' if op == 0x68 else 'numeric', index=index,
                             access={0x60: 'assign', 0x61: 'add', 0x62: 'subtract', 0x68: 'assign'}[op],
                             value=int(value == 1) if op == 0x68 else value))
        return pos + 3, [pos + 3], refs
    if op in (0x09, 0x16, 0x17, 0x87, 0x90, 0x91):
        return pos + 1, [pos + 1], refs
    if op in (0x05, 0x81, 0x39):
        require(pos + 2)
        return pos + 2, [pos + 2], refs
    if op == 0x50:
        require(pos + 3)
        return pos + 3, [struct.unpack_from('<H', data, pos + 1)[0]], refs
    if op == 0x5F:
        require(pos + 2)
        return pos + 2, [], [dict(kind='scenario', index=data[pos + 1], access='transfer_candidate')]
    if op == 0x10:
        p = pos + 1
        while p < len(data):
            if data[p:p + 2] == b'\x81\x66':
                require(p + 3)
                if data[p + 2] != 0:
                    raise ValueError('Unsupported text control after marker')
                return p + 3, [p + 3], refs
            byte = data[p]
            if byte < 0x20 or byte == 0x7F:
                raise ValueError('Unsupported control within text')
            size = 2 if 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC else 1
            require(p + size)
            data[p:p + size].decode('cp932')
            p += size
        raise ValueError('Missing text terminator')
    if op == 0x52:
        p = pos + 1
        for _ in range(256):
            require(p + 6)
            operand = struct.unpack_from('<H', data, p + 1)[0]
            if not 1 <= data[p + 3] <= 5:
                raise ValueError('Unsupported comparison selector')
            refs.append(dict(kind='numeric' if operand & 0x8000 else 'flag', index=operand & 255,
                             access='read_condition', comparison_selector=data[p + 3],
                             rhs=data[p + 4], term_prefix=data[p]))
            separator = data[p + 5]
            if separator == 0:
                require(p + 8)
                target = struct.unpack_from('<H', data, p + 6)[0]
                return p + 8, [p + 8, target], refs
            require(p + 7)
            p += 7
        raise ValueError('Condition group limit')
    raise ValueError(f'Unknown opcode 0x{op:02x}')


def analyze(data):
    pending, seen, instructions, stops, refs = [0], set(), [], [], []
    while pending:
        pos = pending.pop()
        if pos in seen:
            continue
        seen.add(pos)
        if pos == len(data):
            continue
        try:
            if not 0 <= pos < len(data):
                raise ValueError('Target outside resource')
            end, successors, current = decode(data, pos)
        except (ValueError, UnicodeError) as error:
            stops.append(dict(offset=pos, reason=str(error)))
            continue
        instructions.append(dict(offset=pos, end=end, opcode=data[pos], successors=successors))
        refs.extend(dict(offset=pos, **r) for r in current)
        pending.extend(successors)
    # Overlapping instruction ranges indicate an inconsistent control-flow map.
    ordered = sorted(instructions, key=lambda x: x['offset'])
    overlap = any(a['end'] > b['offset'] for a, b in zip(ordered, ordered[1:]))
    if overlap:
        refs = []
        stops.append(dict(offset=0, reason='Overlapping instructions: all references withheld'))
    return dict(instructions=ordered, references=refs, stops=stops, overlap=overlap,
                decoded_bytes=sum(i['end'] - i['offset'] for i in ordered), total_bytes=len(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('survey', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    survey = json.loads(args.survey.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True, exist_ok=False)
    disc = Disc(args.image)
    analyses, flat = [], []
    try:
        for row in survey['candidate_scenarios']:
            data = decompress(disc.read(row['lba'], row['read_sectors'] * 2048))
            digest = hashlib.sha256(data).hexdigest()
            if digest != row['expanded_sha256']:
                raise ValueError('Resource differs from survey')
            # Numeric names avoid trusting file paths in input JSON.
            (args.output / f"{row['index']:03d}.bin").write_bytes(data)
            result = analyze(data)
            result.update(index=row['index'], label=row['label'], sha256=digest)
            analyses.append(result)
            for ref in result['references']:
                kind, index = ref['kind'], ref['index']
                mapped = kind == 'flag' and index < 144 or kind == 'numeric' and index < 20
                offset = (0x28 + index // 8 if kind == 'flag' else index) if mapped else None
                flat.append(dict(scenario=row['label'], scenario_index=row['index'],
                                 script_offset=hex(ref['offset']), kind=kind, index=index,
                                 access=ref['access'], value=ref.get('value', ''),
                                 comparison_selector=ref.get('comparison_selector', ''), rhs=ref.get('rhs', ''),
                                 internal_record_offset=hex(offset) if mapped else '',
                                 mask=hex(1 << (index & 7)) if mapped and kind == 'flag' else '',
                                 save_mapping='static_copy_confirmed' if mapped else 'unconfirmed'))
    finally:
        disc.file.close()
    (args.output / 'analysis.json').write_text(json.dumps(analyses, indent=2), encoding='utf-8')
    with (args.output / 'references.csv').open('w', newline='', encoding='utf-8-sig') as output:
        if flat:
            writer = csv.DictWriter(output, fieldnames=list(flat[0]))
            writer.writeheader()
            writer.writerows(flat)
    index_rows = []
    for kind, limit in [('flag', 144), ('numeric', 20)]:
        for index in range(256):
            matching = [r for r in flat if r['kind'] == kind and r['index'] == index]
            index_rows.append(dict(kind=kind, index=index,
                                   internal_record_offset=hex(0x28 + index // 8 if kind == 'flag' else index) if index < limit else None,
                                   mask=hex(1 << (index & 7)) if kind == 'flag' and index < limit else None,
                                   reads=[r for r in matching if r['access'] == 'read_condition'],
                                   writes=[r for r in matching if r['access'] != 'read_condition'],
                                   meaning='unknown',
                                   status='observed_in_static_paths' if matching else 'not_seen_in_parsed_paths'))
    (args.output / 'state-index.json').write_text(json.dumps(index_rows, indent=2), encoding='utf-8')
    summary = dict(resources=len(analyses), unique_resources=len({a['sha256'] for a in analyses}),
                   instructions=sum(len(a['instructions']) for a in analyses), references=len(flat),
                   decoded_bytes=sum(a['decoded_bytes'] for a in analyses),
                   total_bytes=sum(a['total_bytes'] for a in analyses),
                   stopped_resources=sum(bool(a['stops']) for a in analyses),
                   stop_reasons=dict(collections.Counter(s['reason'] for a in analyses for s in a['stops'])),
                   scope='Only surveyed resources and paths reachable through supported instructions; not complete flag semantics or card format')
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
