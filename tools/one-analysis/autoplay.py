"""Bounded analysis experiment: checkpoint a choice, try each item to next choice.

Uses named emulator states; never writes game RAM or memory cards. Reaches only
one additional choice per branch; unknown waits and time limits are preserved.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import uuid
from capture import request

BASE = 'http://127.0.0.1:18080'
REPO = Path(__file__).resolve().parents[2]


def api(path, post=False):
    return request(BASE, '/api/v1/' + path, 'POST' if post else 'GET')


def status():
    return json.loads(api('lua/one-trace-status'))


def flow():
    return json.loads(api('execution-flow'))


def pause():
    api('execution-flow?function=pause', True)


def button(name):
    prefix = 'lua/one-pad?button=' + name
    try:
        api(prefix + '&pressed=1', True)
        time.sleep(.16)
    finally:
        api(prefix + '&pressed=0', True)


def log_rows(epoch):
    return [r for line in (REPO / '.tools/redux/scenario-trace.jsonl').read_text(encoding='utf-8').splitlines()
            if (r := json.loads(line))['epoch'] == epoch]


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checkpoint(folder, identifier, parent, history, reason):
    pause()
    for name in ('CIRCLE', 'DOWN', 'UP'):
        api('lua/one-pad?button=' + name + '&pressed=0', True)
    s = status()
    folder.mkdir(parents=True, exist_ok=False)
    response = api('state/save?name=' + urllib.parse.quote(identifier)).decode()
    source = REPO / '.tools/redux/SLPS01972' / (identifier + '.sstate')
    if not source.is_file():
        raise RuntimeError('State save did not create expected SLPS01972 file: ' + response)
    files = {}
    for name, data in [('state.sstate', source.read_bytes()),
                       ('ram.bin', api('cpu/ram/raw')), ('screen.png', api('screen/still'))]:
        if name == 'ram.bin' and len(data) != 2097152:
            raise ValueError('Unexpected RAM size')
        (folder / name).write_bytes(data)
        files[name] = dict(bytes=len(data), sha256=digest(data))
    ram = (folder / 'ram.bin').read_bytes()
    rows = log_rows(s['epoch'])
    text_events = [r for r in rows if r['event'] == 'choice_text']
    (folder / 'trace.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    manifest = dict(id=identifier, parent=parent, history=history, reason=reason,
                    utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), observer=s, files=files,
                    flags_hex=ram[0xFA808:0xFA828].hex(), numeric=list(ram[0xFA840:0xFA854]),
                    display_rows=[ram[0xFD088+i*47:0xFD088+(i+1)*47].split(b'\0')[0].decode('cp932', errors='replace') for i in range(9)],
                    display_rows_note='Raw buffers may contain stale trailing text; not authoritative option labels',
                    choice_text_event=text_events[-1] if text_events else None,
                    emulator_state_name=identifier, trace_events=len(rows))
    write_json(folder / 'checkpoint.json', manifest)
    print(json.dumps(dict(checkpoint=identifier, reason=reason, scene=s['scene'], offset=s['offset']), ensure_ascii=False), flush=True)
    return manifest


def load(name):
    pause()
    api('lua/one-trace?action=stop', True)
    api('state/load?name=' + urllib.parse.quote(name))
    api('lua/one-trace?action=start&pause_choice=1', True)
    api('execution-flow?function=resume', True)


def seek_choice(seconds, initial=False):
    deadline = time.monotonic() + seconds
    last_command, changed = None, time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(.15)
        s, f = status(), flow()
        if not s['enabled']:
            return 'trace_disabled'
        if not f['running']:
            return 'choice' if s['at_choice'] else 'unexpected_pause'
        key = (s['scene'], s['offset'], s['opcode'])
        if key != last_command:
            last_command, changed = key, time.monotonic()
        # Advance only known text wait commands. Choice commands never get an
        # automatic confirm, and Lua pauses before the choice handler executes.
        if s['opcode'] in (0x16, 0x17) and time.monotonic() - changed > .5:
            button('CIRCLE')
            time.sleep(.3)
        elif time.monotonic() - changed > (15 if initial else 40):
            return 'stalled_at_command'
    return 'time_limit'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seed', default='one-trace-choice')
    parser.add_argument('--seed-checkpoint', type=Path, help='Reuse a checkpoint.json and its full choice history')
    parser.add_argument('--seconds', type=float, default=180)
    args = parser.parse_args()
    inherited_history = []
    if args.seed_checkpoint:
        seed = json.loads(args.seed_checkpoint.read_text(encoding='utf-8'))
        args.seed = seed['emulator_state_name']
        inherited_history = seed['history']
        saved = REPO / '.tools/redux/SLPS01972' / (args.seed + '.sstate')
        if digest(saved.read_bytes()) != seed['files']['state.sstate']['sha256']:
            raise ValueError('Reusable emulator state is missing or differs from manifest')
    if not 1 <= args.seconds <= 600:
        raise ValueError('seconds must be 1..600 per branch')
    f = flow()
    if f['isDynarec'] or f['8mb'] or not f['debugger']:
        raise ValueError('Requires 2 MiB Interpreter with debugger')
    args.output.mkdir(parents=True, exist_ok=False)
    run = 'one-' + uuid.uuid4().hex[:12]
    metadata = dict(run=run, seed=args.seed, seconds_per_branch=args.seconds,
                    objective='Compare each item of one choice through the next choice; no recursive exhaustive play',
                    provenance={})
    for relative in ['.tools/redux/pcsx-redux.exe', '.tools/redux/pcsx-redux.main', '.tools/redux/pcsx.json', '.tools/redux/scph5500.bin',
                     'tools/one-analysis/trace.lua', 'tools/one-analysis/autoplay.py']:
        metadata['provenance'][relative] = digest((REPO / relative).read_bytes())
    for relative in ['.tools/redux-manifest.json', '.tools/redux-analysis/disc-copy-hashes.json']:
        path = REPO / relative
        if path.exists():
            metadata['provenance'][relative] = json.loads(path.read_text(encoding='utf-8-sig'))
    write_json(args.output / 'run.json', metadata)
    try:
        # Preserve the user's current paused/running point before loading seed.
        checkpoint(args.output / 'before', run + '-before', None, [], 'before_experiment')
        load(args.seed)
        reason = seek_choice(20, initial=True)
        root = checkpoint(args.output / 'root', run + '-root', args.seed, inherited_history, reason)
        if reason != 'choice':
            raise RuntimeError('Seed did not reach a choice: ' + reason)
        count = root['observer']['choice_count']
        if not 1 <= count <= 9:
            raise ValueError('Unsupported choice count')
        outcomes = []
        for item in range(1, count + 1):
            load(root['id'])
            if seek_choice(20, initial=True) != 'choice':
                raise RuntimeError('Checkpoint did not restore to choice')
            api('execution-flow?function=resume', True)
            time.sleep(.5)
            for _ in range(item - 1):
                button('DOWN'); time.sleep(.3)
            button('CIRCLE')
            reason = seek_choice(args.seconds)
            child = checkpoint(args.output / f'item-{item}', run + f'-item-{item}', root['id'],
                               inherited_history + [dict(checkpoint=root['id'], item=item)], reason)
            choices = [r for r in log_rows(child['observer']['epoch']) if r['event'] == 'choice_result']
            if not choices or choices[0]['value'] != item:
                raise RuntimeError('Chosen item did not match observed result')
            outcomes.append(child)
            write_json(args.output / 'outcomes.json', outcomes)
        # Leave a reusable root point paused, rather than continuing unchecked.
        load(root['id'])
        seek_choice(20, initial=True)
    except Exception as error:
        metadata['error'] = str(error)
        raise
    finally:
        pause()
        for name in ('CIRCLE', 'DOWN', 'UP'):
            api('lua/one-pad?button=' + name + '&pressed=0', True)
        metadata['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json(args.output / 'run.json', metadata)


if __name__ == '__main__':
    main()
