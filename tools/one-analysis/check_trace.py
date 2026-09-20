"""Validate ONE JSONL trace ordering/checksums and optionally both opening choices."""
import argparse
import collections
import json
from pathlib import Path


def check(rows, opening=False):
    previous = 0
    for row in rows:
        if row['sequence'] != previous + 1:
            raise ValueError('Missing or reordered trace events')
        previous = row['sequence']
        if row['event'] == 'trace_error':
            raise ValueError(row['message'])
        if row['event'] == 'snapshot_ready':
            record = bytes.fromhex(row['record_hex'])
            if len(record) != 128 or sum(record[:109]) != int.from_bytes(record[124:126], 'little'):
                raise ValueError('Snapshot checksum mismatch')
    verified = []
    if opening:
        for value, destination in [(1, 0x401), (2, 0x465)]:
            found = False
            for i, row in enumerate(rows):
                if (row['event'] != 'choice_result' or row.get('scene') != 'NV30'
                        or row.get('offset') != 0x3F5 or row.get('variable') != 16 or row.get('value') != value):
                    continue
                following = [r for r in rows[i+1:] if r['epoch'] == row['epoch']]
                branch = next((r for r in following if r['event'] == 'branch'), None)
                if branch is None or branch['next_offset'] != destination or branch['passed'] != (value == 1):
                    continue
                command = next((r for r in following if r['event'] == 'command' and r['sequence'] > branch['sequence']), None)
                snapshot = next((r for r in following if r['event'] == 'snapshot_ready'), None)
                if command and command['offset'] == destination and snapshot and bytes.fromhex(snapshot['record_hex'])[16] == value:
                    found = True
                    verified.append(dict(value=value, next_offset=hex(destination), epoch=row['epoch']))
                    break
            if not found:
                raise ValueError(f'Opening choice {value} was not verified through branch and snapshot')
    return dict(events=len(rows), event_counts=dict(collections.Counter(r['event'] for r in rows)),
                verified_opening_choices=verified)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--verify-opening', action='store_true')
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.trace.read_text(encoding='utf-8').splitlines()]
    print(json.dumps(check(rows, args.verify_opening), indent=2))


if __name__ == '__main__':
    main()
