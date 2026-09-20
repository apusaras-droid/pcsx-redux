"""Host-side checks for diagnostic filtering; no emulator or MIPS compiler needed."""

import os
from pathlib import Path
import subprocess
import tempfile


MIPS_ROOT = Path(__file__).resolve().parents[2]
CC = os.environ.get("CC", "gcc")
SOURCE = r'''
#include <stdarg.h>
#include <stdio.h>
#include "openbios/diagnostics/log.h"

void BoardConsolePrintf(const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
}

int main(void) {
    int evaluated = 0;
    OB_LOG_ERROR("TEST", "error %d", ++evaluated);
    OB_LOG_WARN("TEST", "warning %d", ++evaluated);
    OB_LOG_INFO("TEST", "info %d", ++evaluated);
    OB_LOG_DEBUG("TEST", "debug %d", ++evaluated);
    if (evaluated != OPENBIOS_LOG_LEVEL) return 1;
    OB_LOG_INFO("TEST", "no arguments");
    if (0) OB_LOG_ERROR("TEST", "unexpected"); else evaluated = 0;
    return evaluated;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="openbios-log-") as directory:
        root = Path(directory)
        source = root / "logging.c"
        source.write_text(SOURCE)
        messages = [("ERROR", "error"), ("WARN", "warning"), ("INFO", "info"), ("DEBUG", "debug")]
        # Check both unoptimized and release builds: disabled expressions must
        # never run, even when the compiler does not optimize the program.
        for optimization in ("-O0", "-Os"):
            for level in range(5):
                binary = root / ("logging.exe" if os.name == "nt" else "logging")
                subprocess.run([CC, "-std=gnu11", optimization, "-Wall", "-Wextra", "-Werror",
                                f"-DOPENBIOS_LOG_LEVEL={level}", "-I", str(MIPS_ROOT),
                                str(source), "-o", str(binary)], check=True)
                output = subprocess.check_output([str(binary)], text=True)
                expected = "".join(f"[OpenBIOS][{tag}][TEST] {message} {i + 1}\n"
                                   for i, (tag, message) in enumerate(messages[:level]))
                if level >= 3:
                    expected += "[OpenBIOS][INFO][TEST] no arguments\n"
                assert output == expected, (level, output, expected)
        for level in (-1, 5):
            result = subprocess.run([CC, "-fsyntax-only", f"-DOPENBIOS_LOG_LEVEL={level}",
                                     "-I", str(MIPS_ROOT), str(source)], capture_output=True)
            assert result.returncode != 0, f"Invalid level {level} accepted"
        print("PASS: 10 level/optimization combinations, side effects, formatting, invalid levels")


if __name__ == "__main__":
    main()
