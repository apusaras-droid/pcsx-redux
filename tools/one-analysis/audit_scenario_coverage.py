"""Audit Disc 1 DATA.BIN for sector-aligned compressed scenario candidates.

Heuristic matches are never promoted to confirmed scenarios. Does not scan
audio/video payloads, unaligned streams, or other compression formats.
"""
import argparse
import collections
import hashlib
import json
import struct
from pathlib import Path
from lzss import decompress


def text_candidates(data):
    hits, pos = [], 0
    while True:
        start = data.find(b'\x10', pos)
        if start < 0:
            break
        pos = start + 1
        end = data.find(b'\x81\x66', pos, pos + 2048)
        if end < pos + 6 or data[end + 2:end + 3] not in (b'\0', b'\1'):
            continue
        try:
            text = data[pos:end].decode('cp932')
        except UnicodeError:
            continue
        if any(ord(c) < 32 for c in text):
            continue
        if sum('\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff' for c in text) >= 3:
            hits.append(start)
    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', type=Path)
    parser.add_argument('survey', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = args.data.read_bytes()
    survey = json.loads(args.survey.read_text(encoding='utf-8'))
    known = collections.defaultdict(list)
    for row in survey['candidate_scenarios']:
        known[int(row['container_offset'], 16)].append(row)
    known_extents = [(start, start + struct.unpack_from('<I', data, start)[0], aliases)
                     for start, aliases in known.items()]
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'confirmed').mkdir()
    (args.output / 'candidates').mkdir()
    results, rejected, checked = [], collections.Counter(), 0
    for offset in range(0, len(data) - 3, 2048):
        size = struct.unpack_from('<I', data, offset)[0]
        if not 4 <= size <= min(262144, len(data) - offset):
            rejected['header_outside_scan_bounds'] += 1
            continue
        checked += 1
        try:
            expanded = decompress(data[offset:offset + size], 262144)
        except ValueError as error:
            rejected[str(error)] += 1
            continue
        digest = hashlib.sha256(expanded).hexdigest()
        aliases = known.get(offset, [])
        if aliases and any(r['expanded_sha256'] != digest for r in aliases):
            raise ValueError(f'Known resource hash mismatch at {offset:#x}')
        hits = text_candidates(expanded)
        containing = [dict(offset=hex(start), labels=[r['label'] for r in labels])
                      for start, end, labels in known_extents if start < offset < end]
        row = dict(file_offset=hex(offset), compressed_bytes=size, expanded_bytes=len(expanded),
                   sha256=digest, aliases=[dict(index=r['index'], label=r['label']) for r in aliases],
                   text_pattern_count=len(hits), text_pattern_offsets=hits,
                   containing_known_streams=containing,
                   classification='confirmed_table_resource' if aliases else 'unclassified_compressed_data')
        if aliases or len(hits) >= 3:
            category = 'confirmed' if aliases else 'candidates'
            filename = f'{category}/{offset:08x}.bin'
            (args.output / filename).write_bytes(expanded)
            row['file'] = filename
            if not aliases:
                row['classification'] = ('interior_of_known_stream_not_independent' if containing
                                         else 'unconfirmed_text_bearing_candidate')
        results.append(row)
    found = {int(r['file_offset'], 16) for r in results if r['aliases']}
    missing = sorted(set(known) - found)
    report = dict(data_sha256=hashlib.sha256(data).hexdigest(), sector_alignment=2048,
                  compressed_and_output_limit=262144, checked_headers=checked,
                  rejected=dict(rejected), confirmed_aliases=sum(len(r['aliases']) for r in results),
                  confirmed_unique_offsets=len(found), missing_known_offsets=missing,
                  extra_candidates=sum(r['classification']=='unconfirmed_text_bearing_candidate' for r in results),
                  resources=results,
                  limitations='Only DATA.BIN, 2048-aligned headers, known LZSS, bounded sizes. Text signatures do not prove script boundaries or reachability.')
    (args.output / 'coverage.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'resources'}, indent=2), flush=True)
    if missing:
        raise SystemExit('Some known resources were not recovered')


if __name__ == '__main__':
    main()
