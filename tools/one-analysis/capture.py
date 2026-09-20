"""Capture a consistent PCSX-Redux RAM/VRAM/screen snapshot over its local API."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


def request(base, path, method='GET'):
    req = urllib.request.Request(base + path, method=method, data=b'' if method == 'POST' else None)
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--base', default='http://127.0.0.1:18080')
    parser.add_argument('--button', choices=['START', 'CIRCLE', 'CROSS', 'UP', 'DOWN'])
    args = parser.parse_args()
    if args.button:
        path = '/api/v1/lua/one-pad?button=' + args.button
        try:
            request(args.base, path + '&pressed=1', 'POST')
            time.sleep(0.15)
        finally:
            request(args.base, path + '&pressed=0', 'POST')
        time.sleep(1)
    # Never overwrite a previous checkpoint.
    args.output.mkdir(parents=True, exist_ok=False)
    state = json.loads(request(args.base, '/api/v1/execution-flow'))
    manifest = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'flow_before': state, 'files': {}}
    try:
        request(args.base, '/api/v1/execution-flow?function=pause', 'POST')
        for name, path, size in [
            ('ram.bin', '/api/v1/cpu/ram/raw', 8388608 if state['8mb'] else 2097152),
            ('vram.bin', '/api/v1/gpu/vram/raw', 1048576),
            ('screen.png', '/api/v1/screen/still', None),
        ]:
            data = request(args.base, path)
            if size is not None and len(data) != size:
                raise ValueError(f'{name}: expected {size} bytes, got {len(data)}')
            if name.endswith('.png') and not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Invalid screenshot response')
            (args.output / name).write_bytes(data)
            manifest['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        try:
            manifest['observer'] = json.loads(request(args.base, '/api/v1/lua/one-status'))
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            manifest['observer'] = None
        (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    finally:
        if state['running']:
            request(args.base, '/api/v1/execution-flow?function=resume', 'POST')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
