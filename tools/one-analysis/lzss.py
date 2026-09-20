"""Bounded decoder derived from SLPS-01972 function 0x80020340."""
import struct


def decompress(data, max_output=2 * 1024 * 1024):
    if len(data) < 4:
        raise ValueError('Missing length header')
    end = struct.unpack_from('<I', data)[0]
    if not 4 <= end <= len(data):
        raise ValueError('Compressed length outside input')
    ring = bytearray(4096)
    # The original clears only 0..4077; reject dependence on stale scratch RAM.
    initialized = bytearray(b'\1' * 4078 + b'\0' * 18)
    write, pos = 4078, 4
    output = bytearray()

    def emit(value):
        nonlocal write
        if len(output) >= max_output:
            raise ValueError('Output limit exceeded')
        output.append(value)
        ring[write] = value
        initialized[write] = 1
        write = (write + 1) & 4095

    while pos < end:
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if flags & (1 << bit):
                if pos >= end:
                    return bytes(output)
                emit(data[pos])
                pos += 1
            else:
                if pos + 2 > end:
                    return bytes(output)
                low, high = data[pos:pos + 2]
                pos += 2
                source = low | ((high & 240) << 4)
                for index in range((high & 15) + 3):
                    address = (source + index) & 4095
                    if not initialized[address]:
                        raise ValueError('Back-reference depends on uninitialized scratch RAM')
                    emit(ring[address])
    return bytes(output)
