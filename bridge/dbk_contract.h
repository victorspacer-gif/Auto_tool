#pragma once

#include <windows.h>
#include <winioctl.h>

#include <cstdint>

// Extracted from upstream Cheat Engine:
// - Cheat Engine/dbk32/DBK32functions.pas
// - DBKKernel/IOPLDispatcher.c
//
// The current upstream repository does not contain DBK32/dbk32.h; the user-mode
// contract lives primarily in DBK32functions.pas and the kernel-side buffered
// structures are mirrored inside IOPLDispatcher.c.

// The local Studiomemuer 7.5.1 portable binary still embeds Cheat Engine's
// DBK service/device defaults:
//   servicename       CEDRIVER73
//   processeventname  DBKProcList60
//   threadeventname   DBKThreadList60
//   config filename   driver64.dat
constexpr wchar_t kDefaultDbkDeviceName[] = L"\\\\.\\CEDRIVER73";

constexpr DWORD kDbkReadMemory = CTL_CODE(FILE_DEVICE_UNKNOWN, 0x0800, METHOD_BUFFERED, FILE_READ_ACCESS | FILE_WRITE_ACCESS);
constexpr DWORD kDbkWriteMemory = CTL_CODE(FILE_DEVICE_UNKNOWN, 0x0801, METHOD_BUFFERED, FILE_READ_ACCESS | FILE_WRITE_ACCESS);
constexpr DWORD kDbkOpenProcess = CTL_CODE(FILE_DEVICE_UNKNOWN, 0x0802, METHOD_BUFFERED, FILE_READ_ACCESS | FILE_WRITE_ACCESS);
constexpr DWORD kDbkGetVersion = CTL_CODE(FILE_DEVICE_UNKNOWN, 0x0816, METHOD_BUFFERED, FILE_READ_ACCESS | FILE_WRITE_ACCESS);

#pragma pack(push, 1)
struct DbkReadMemoryInput {
    std::uint64_t processid;
    std::uint64_t startaddress;
    std::uint16_t bytestoread;
};

struct DbkWriteMemoryInput {
    std::uint64_t processid;
    std::uint64_t startaddress;
    std::uint16_t bytestowrite;
};

struct DbkOpenProcessOutput {
    std::uint64_t process_handle;
    std::uint8_t special;
};
#pragma pack(pop)

static_assert(sizeof(DbkReadMemoryInput) == 18);
static_assert(sizeof(DbkWriteMemoryInput) == 18);
