"""Inspect a verified subset of ONE script instructions without executing them.

Stops at an unknown instruction, a resource transfer, or the first text block.
This is not a general script extractor or runtime.
"""
import argparse
import json
from pathlib import Path


def inspect(data):
    rows, pos = [], 0
    while pos < len(data):
        opcode = data[pos]
        row = {'offset': hex(pos), 'opcode': hex(opcode)}
        if opcode in (0x60, 0x61, 0x62, 0x80):
            if pos + 3 > len(data):
                raise ValueError('Truncated three-byte instruction')
            a, b = data[pos + 1:pos + 3]
            if opcode == 0x80:
                row.update(operation='unresolved_80', operands=[a, b], handler='0x8001af04')
            else:
                row.update(operation={0x60: 'set_byte', 0x61: 'add_byte', 0x62: 'subtract_byte'}[opcode],
                           variable_index=a, value=b, address=hex(0x800FA840 + a))
            pos += 3
        elif opcode == 0x5F:
            if pos + 2 > len(data):
                raise ValueError('Truncated resource transfer')
            row.update(operation='scenario_transfer_conditional_path', resource_index=data[pos + 1],
                       handler='0x8001ab1c')
            rows.append(row)
            return {'instructions': rows, 'stop': 'Resource transfer; alternate handler path not modeled'}
        elif opcode == 0x10:
            # Only the initial plain text block; do not guess other text controls.
            end = data.find(b'\x81\x66', pos + 1)
            if end < 0 or data[end + 2:end + 3] != b'\0':
                rows.append(row)
                return {'instructions': rows, 'stop': 'Unsupported text terminator/control'}
            text = data[pos + 1:end].decode('cp932')
            row.update(operation='text', text=text, handler='0x8001876c', next_offset=hex(end + 3))
            rows.append(row)
            return {'instructions': rows, 'stop': 'First text block; no further command boundaries inferred'}
        else:
            rows.append(row)
            return {'instructions': rows, 'stop': 'Unknown instruction'}
        rows.append(row)
    return {'instructions': rows, 'stop': 'End of input'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = inspect(args.script.read_bytes())
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(f"{len(result['instructions'])} instructions: {result['stop']}")


if __name__ == '__main__':
    main()
