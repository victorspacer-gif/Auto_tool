#include "driver_adapter.h"

#include "dbk_contract.h"

#include <windows.h>

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdlib>
#include <cstring>

namespace {

HANDLE g_device = INVALID_HANDLE_VALUE;

const wchar_t* device_name() {
    static wchar_t configured[MAX_PATH]{};
    static bool loaded = false;

    if (!loaded) {
        loaded = true;
        const DWORD chars = GetEnvironmentVariableW(L"STUDIOMEM_DBK_DEVICE", configured, MAX_PATH);
        if (chars == 0 || chars >= MAX_PATH) {
            configured[0] = L'\0';
        }
    }

    return configured[0] != L'\0' ? configured : kDefaultDbkDeviceName;
}

SmemStatus status_from_last_error() {
    switch (GetLastError()) {
    case ERROR_ACCESS_DENIED:
    case ERROR_PRIVILEGE_NOT_HELD:
        return SMEM_ERR_ACCESS_DENIED;
    case ERROR_FILE_NOT_FOUND:
    case ERROR_PATH_NOT_FOUND:
    case ERROR_SERVICE_DOES_NOT_EXIST:
        return SMEM_ERR_DRIVER_UNAVAILABLE;
    case ERROR_PARTIAL_COPY:
        return SMEM_ERR_PARTIAL_COPY;
    case ERROR_INVALID_ADDRESS:
        return SMEM_ERR_INVALID_ADDRESS;
    case ERROR_INVALID_PARAMETER:
        return SMEM_ERR_INVALID_ARGUMENT;
    default:
        return SMEM_ERR_INTERNAL;
    }
}

bool has_device() {
    return g_device != INVALID_HANDLE_VALUE && g_device != nullptr;
}

}  // namespace

namespace driver_adapter {

SmemStatus initialize() {
    if (has_device()) {
        return SMEM_OK;
    }

    g_device = CreateFileW(
        device_name(),
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        nullptr);

    if (!has_device()) {
        g_device = INVALID_HANDLE_VALUE;
        return status_from_last_error();
    }

    DWORD version = 0;
    DWORD returned = 0;
    DeviceIoControl(
        g_device,
        kDbkGetVersion,
        nullptr,
        0,
        &version,
        sizeof(version),
        &returned,
        nullptr);

    return SMEM_OK;
}

void shutdown() {
    if (has_device()) {
        CloseHandle(g_device);
    }
    g_device = INVALID_HANDLE_VALUE;
}

SmemStatus open_process(std::uint32_t pid) {
    if (pid == 0) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }
    if (!has_device()) {
        return SMEM_ERR_NOT_INITIALIZED;
    }

    DWORD input = pid;
    DbkOpenProcessOutput output{};
    DWORD returned = 0;
    const BOOL ok = DeviceIoControl(
        g_device,
        kDbkOpenProcess,
        &input,
        sizeof(input),
        &output,
        sizeof(output),
        &returned,
        nullptr);

    return ok ? SMEM_OK : status_from_last_error();
}

void close_process() {
}

SmemStatus resolve_process_eprocess(std::uint32_t pid, std::uint64_t* out_eprocess) {
    if (out_eprocess != nullptr) {
        *out_eprocess = 0;
    }
    if (pid == 0 || out_eprocess == nullptr) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }
    if (!has_device()) {
        return SMEM_ERR_NOT_INITIALIZED;
    }

    DWORD input = pid;
    std::uint64_t output = 0;
    DWORD returned = 0;
    const BOOL ok = DeviceIoControl(
        g_device,
        kDbkGetPeProcess,
        &input,
        sizeof(input),
        &output,
        sizeof(output),
        &returned,
        nullptr);

    if (!ok) {
        return status_from_last_error();
    }
    if (output == 0) {
        return SMEM_ERR_PROCESS_NOT_FOUND;
    }

    *out_eprocess = output;
    return SMEM_OK;
}

SmemStatus resolve_process_cr3(std::uint32_t pid, std::uint64_t* out_cr3) {
    if (out_cr3 != nullptr) {
        *out_cr3 = 0;
    }
    if (pid == 0 || out_cr3 == nullptr) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }
    if (!has_device()) {
        return SMEM_ERR_NOT_INITIALIZED;
    }

    DWORD input = pid;
    std::uint64_t output = 0;
    DWORD returned = 0;
    const BOOL ok = DeviceIoControl(
        g_device,
        kDbkGetCr3,
        &input,
        sizeof(input),
        &output,
        sizeof(output),
        &returned,
        nullptr);

    if (!ok) {
        return status_from_last_error();
    }
    if ((output & 0xFFFFFFFFFFFFF000ULL) == 0) {
        return SMEM_ERR_INVALID_ADDRESS;
    }

    *out_cr3 = output;
    return SMEM_OK;
}

SmemStatus read_virtual_chunk(
    std::uint32_t pid,
    std::uint64_t address,
    void* out_buffer,
    std::size_t size,
    std::size_t* out_bytes_read) {
    if (out_bytes_read != nullptr) {
        *out_bytes_read = 0;
    }
    if (pid == 0 || address == 0 || out_buffer == nullptr || size == 0 || out_bytes_read == nullptr) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }
    if (!has_device()) {
        return SMEM_ERR_NOT_INITIALIZED;
    }
    if (size > 0x1000 || size > UINT16_MAX) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }

    DbkReadMemoryInput input{
        static_cast<std::uint64_t>(pid),
        address,
        static_cast<std::uint16_t>(size),
    };
    DWORD returned = 0;

    const BOOL ok = DeviceIoControl(
        g_device,
        kDbkReadMemory,
        &input,
        sizeof(input),
        out_buffer,
        static_cast<DWORD>(size),
        &returned,
        nullptr);

    if (!ok) {
        return status_from_last_error();
    }

    *out_bytes_read = returned != 0 ? returned : size;
    return *out_bytes_read == size ? SMEM_OK : SMEM_ERR_PARTIAL_COPY;
}

SmemStatus write_virtual_chunk(
    std::uint32_t pid,
    std::uint64_t address,
    const void* buffer,
    std::size_t size,
    std::size_t* out_bytes_written) {
    if (out_bytes_written != nullptr) {
        *out_bytes_written = 0;
    }
    if (pid == 0 || address == 0 || buffer == nullptr || size == 0 || out_bytes_written == nullptr) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }
    if (!has_device()) {
        return SMEM_ERR_NOT_INITIALIZED;
    }

    constexpr std::size_t packet_size = 512;
    constexpr std::size_t header_size = sizeof(DbkWriteMemoryInput);
    constexpr std::size_t max_payload = packet_size - header_size;

    std::array<unsigned char, packet_size> packet{};
    auto* input = reinterpret_cast<DbkWriteMemoryInput*>(packet.data());
    std::size_t total_written = 0;

    while (total_written < size) {
        const std::size_t remaining = size - total_written;
        const std::size_t payload_size = (std::min)(remaining, max_payload);

        packet.fill(0);
        input->processid = pid;
        input->startaddress = address + total_written;
        input->bytestowrite = static_cast<std::uint16_t>(payload_size);
        std::memcpy(packet.data() + header_size, static_cast<const unsigned char*>(buffer) + total_written, payload_size);

        DWORD returned = 0;
        const BOOL ok = DeviceIoControl(
            g_device,
            kDbkWriteMemory,
            packet.data(),
            static_cast<DWORD>(packet.size()),
            packet.data(),
            static_cast<DWORD>(packet.size()),
            &returned,
            nullptr);

        if (!ok) {
            *out_bytes_written = total_written;
            return status_from_last_error();
        }

        total_written += payload_size;
    }

    *out_bytes_written = total_written;
    return total_written == size ? SMEM_OK : SMEM_ERR_PARTIAL_COPY;
}

}  // namespace driver_adapter
