/* SPDX-License-Identifier: MIT */
#pragma once

#include "openbios/uC-sdk-glue/BoardConsole.h"

// Opt in: the BoardConsole backend writes to the PCSX-Redux debug port.
#ifndef OPENBIOS_LOG_LEVEL
#define OPENBIOS_LOG_LEVEL 0
#endif

#if OPENBIOS_LOG_LEVEL < 0 || OPENBIOS_LOG_LEVEL > 4
#error "OPENBIOS_LOG_LEVEL must be between 0 (off) and 4 (debug)"
#endif

// Disabled messages do not evaluate their arguments or retain format strings.
// Use literal format strings, without a trailing newline.
#define OPENBIOS_LOG(level, tag, category, fmt, ...)                         \
    do {                                                                  \
        if (OPENBIOS_LOG_LEVEL >= (level))                                  \
            BoardConsolePrintf("[OpenBIOS][" tag "][" category "] " fmt "\n", ##__VA_ARGS__); \
    } while (0)

#define OB_LOG_ERROR(category, fmt, ...) OPENBIOS_LOG(1, "ERROR", category, fmt, ##__VA_ARGS__)
#define OB_LOG_WARN(category, fmt, ...) OPENBIOS_LOG(2, "WARN", category, fmt, ##__VA_ARGS__)
#define OB_LOG_INFO(category, fmt, ...) OPENBIOS_LOG(3, "INFO", category, fmt, ##__VA_ARGS__)
#define OB_LOG_DEBUG(category, fmt, ...) OPENBIOS_LOG(4, "DEBUG", category, fmt, ##__VA_ARGS__)
