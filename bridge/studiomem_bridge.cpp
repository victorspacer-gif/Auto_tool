#include "studiomem_bridge.h"

#include "dbvm_adapter.h"
#include "driver_adapter.h"

#include <windows.h>
#include <tlhelp32.h>

#include <algorithm>
#include <cstddef>
#include <cwchar>
#include <cwctype>
#include <mutex>
#include <string>

namespace {

constexpr std::uint64_t kPageSize = 0x1000;

std::mutex g_mutex;
bool g_initialized = false;
std::uint32_t g_attached_pid = 0;
std::wstring g_last_error = L"OK";

void set_last_error_message(const std::wstring& message) {
    g_last_error = message;
}

SmemStatus fail(SmemStatus status, const std::wstring& message) {
    set_last_error_message(message);
    return status;
}

bool contains_case_insensitive(const wchar_t* haystack, const wchar_t* needle) {
    if (haystack == nullptr || needle == nullptr || needle[0] == L'\0') {
        return false;
    }

    std::wstring h(haystack);
    std::wstring n(needle);
    std::transform(h.begin(), h.end(), h.begin(), towlower);
    std::transform(n.begin(), n.end(), n.begin(), towlower);
    return h.find(n) != std::wstring::npos;
}

SmemStatus find_pid_by_name(const wchar_t* process_name, std::uint32_t* out_pid) {
    if (process_name == nullptr || process_name[0] == L'\0' || out_pid == nullptr) {
        return fail(SMEM_ERR_INVALID_ARGUMENT, L"Process name and out_pid are required.");
    }

    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) {
        return fail(SMEM_ERR_INTERNAL, L"CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS) failed.");
    }

    PROCESSENTRY32W entry{};
    entry.dwSize = sizeof(entry);

    if (!Process32FirstW(snapshot, &entry)) {
        CloseHandle(snapshot);
        return fail(SMEM_ERR_INTERNAL, L"Process32FirstW failed.");
    }

    do {
        if (contains_case_insensitive(entry.szExeFile, process_name)) {
            *out_pid = entry.th32ProcessID;
            CloseHandle(snapshot);
            return SMEM_OK;
        }
    } while (Process32NextW(snapshot, &entry));

    CloseHandle(snapshot);
    return fail(SMEM_ERR_PROCESS_NOT_FOUND, L"Process was not found.");
}

std::size_t page_limited_size(std::uint64_t address, std::uint64_t remaining) {
    const std::uint64_t page_remaining = kPageSize - (address & (kPageSize - 1));
    const std::uint64_t chunk = std::min(page_remaining, remaining);
    return static_cast<std::size_t>(std::min<std::uint64_t>(chunk, 1024 * 1024));
}

}  // namespace

extern "C" {

__declspec(dllexport) int __stdcall smem_initialize() {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (g_initialized) {
        return SMEM_OK;
    }

    const SmemStatus status = driver_adapter::initialize();
    if (status != SMEM_OK) {
        return fail(
            status,
            L"Studiomemuer DBK driver could not be opened. Default device is \\\\.\\CEDRIVER73; "
            L"set STUDIOMEM_DBK_DEVICE if your fork uses a different device name.");
    }

    g_initialized = true;
    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_shutdown() {
    std::lock_guard<std::mutex> lock(g_mutex);
    driver_adapter::close_process();
    driver_adapter::shutdown();
    g_attached_pid = 0;
    g_initialized = false;
    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_attach_process(
    const wchar_t* process_name,
    std::uint32_t* out_pid) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (!g_initialized) {
        return fail(SMEM_ERR_NOT_INITIALIZED, L"smem_initialize must be called first.");
    }

    std::uint32_t pid = 0;
    SmemStatus status = find_pid_by_name(process_name, &pid);
    if (status != SMEM_OK) {
        return status;
    }

    status = driver_adapter::open_process(pid);
    if (status != SMEM_OK) {
        return fail(status, L"Driver adapter failed to open target process context.");
    }

    g_attached_pid = pid;
    *out_pid = pid;
    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_open_process(std::uint32_t pid) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (!g_initialized) {
        return fail(SMEM_ERR_NOT_INITIALIZED, L"smem_initialize must be called first.");
    }
    if (pid == 0) {
        return fail(SMEM_ERR_INVALID_ARGUMENT, L"PID must be nonzero.");
    }

    const SmemStatus status = driver_adapter::open_process(pid);
    if (status != SMEM_OK) {
        return fail(status, L"Driver adapter failed to open target process context.");
    }

    g_attached_pid = pid;
    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_close_process() {
    std::lock_guard<std::mutex> lock(g_mutex);
    driver_adapter::close_process();
    g_attached_pid = 0;
    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_get_module_base(
    std::uint32_t pid,
    const wchar_t* module_name,
    std::uint64_t* out_base,
    std::uint64_t* out_size) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (pid == 0 || module_name == nullptr || out_base == nullptr || out_size == nullptr) {
        return fail(SMEM_ERR_INVALID_ARGUMENT, L"PID, module_name, out_base, and out_size are required.");
    }

    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
    if (snapshot == INVALID_HANDLE_VALUE) {
        return fail(SMEM_ERR_ACCESS_DENIED, L"CreateToolhelp32Snapshot(TH32CS_SNAPMODULE) failed.");
    }

    MODULEENTRY32W entry{};
    entry.dwSize = sizeof(entry);

    if (!Module32FirstW(snapshot, &entry)) {
        CloseHandle(snapshot);
        return fail(SMEM_ERR_PROCESS_NOT_FOUND, L"No modules were found for the process.");
    }

    do {
        if (contains_case_insensitive(entry.szModule, module_name) ||
            contains_case_insensitive(entry.szExePath, module_name)) {
            *out_base = reinterpret_cast<std::uint64_t>(entry.modBaseAddr);
            *out_size = entry.modBaseSize;
            CloseHandle(snapshot);
            set_last_error_message(L"OK");
            return SMEM_OK;
        }
    } while (Module32NextW(snapshot, &entry));

    CloseHandle(snapshot);
    return fail(SMEM_ERR_PROCESS_NOT_FOUND, L"Requested module was not found.");
}

__declspec(dllexport) int __stdcall smem_read_virtual(
    std::uint32_t pid,
    std::uint64_t address,
    void* out_buffer,
    std::uint64_t size,
    std::uint64_t* out_bytes_read) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (out_bytes_read != nullptr) {
        *out_bytes_read = 0;
    }
    if (!g_initialized) {
        return fail(SMEM_ERR_NOT_INITIALIZED, L"smem_initialize must be called first.");
    }
    if (pid == 0 || address == 0 || out_buffer == nullptr || size == 0 || out_bytes_read == nullptr) {
        return fail(SMEM_ERR_INVALID_ARGUMENT, L"PID, address, output buffer, size, and byte count are required.");
    }

    auto* cursor = static_cast<unsigned char*>(out_buffer);
    std::uint64_t current = address;
    std::uint64_t remaining = size;

    while (remaining > 0) {
        const std::size_t chunk_size = page_limited_size(current, remaining);
        std::size_t chunk_read = 0;
        const SmemStatus status = driver_adapter::read_virtual_chunk(
            pid,
            current,
            cursor,
            chunk_size,
            &chunk_read);

        *out_bytes_read += chunk_read;
        if (status != SMEM_OK) {
            return status;
        }
        if (chunk_read != chunk_size) {
            return fail(SMEM_ERR_PARTIAL_COPY, L"Driver adapter returned a partial page chunk read.");
        }

        cursor += chunk_size;
        current += chunk_size;
        remaining -= chunk_size;
    }

    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_write_virtual(
    std::uint32_t pid,
    std::uint64_t address,
    const void* buffer,
    std::uint64_t size,
    std::uint64_t* out_bytes_written) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (out_bytes_written != nullptr) {
        *out_bytes_written = 0;
    }
    if (!g_initialized) {
        return fail(SMEM_ERR_NOT_INITIALIZED, L"smem_initialize must be called first.");
    }
    if (pid == 0 || address == 0 || buffer == nullptr || size == 0 || out_bytes_written == nullptr) {
        return fail(SMEM_ERR_INVALID_ARGUMENT, L"PID, address, input buffer, size, and byte count are required.");
    }

    const auto* cursor = static_cast<const unsigned char*>(buffer);
    std::uint64_t current = address;
    std::uint64_t remaining = size;

    while (remaining > 0) {
        const std::size_t chunk_size = page_limited_size(current, remaining);
        std::size_t chunk_written = 0;
        const SmemStatus status = driver_adapter::write_virtual_chunk(
            pid,
            current,
            cursor,
            chunk_size,
            &chunk_written);

        *out_bytes_written += chunk_written;
        if (status != SMEM_OK) {
            return status;
        }
        if (chunk_written != chunk_size) {
            return fail(SMEM_ERR_PARTIAL_COPY, L"Driver adapter returned a partial page chunk write.");
        }

        cursor += chunk_size;
        current += chunk_size;
        remaining -= chunk_size;
    }

    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_last_error(
    wchar_t* buffer,
    std::uint32_t buffer_chars) {
    if (buffer == nullptr || buffer_chars == 0) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }

    std::lock_guard<std::mutex> lock(g_mutex);
    wcsncpy_s(buffer, buffer_chars, g_last_error.c_str(), _TRUNCATE);
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_dbvm_initialize() {
    std::lock_guard<std::mutex> lock(g_mutex);

    const SmemStatus status = dbvm_adapter::initialize();
    if (status != SMEM_OK) {
        return fail(
            status,
            L"DBVM is not currently reachable through VMCall/VMMCall. Start DBVM in Studiomemuer first, "
            L"then provide the target process CR3 via STUDIOMEM_DBVM_CR3.");
    }

    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_dbvm_get_version(
    std::uint32_t* out_version) {
    std::lock_guard<std::mutex> lock(g_mutex);

    const SmemStatus status = dbvm_adapter::version(out_version);
    if (status != SMEM_OK) {
        return fail(status, L"DBVM version query failed.");
    }

    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_dbvm_read_physical(
    std::uint64_t physical_address,
    void* out_buffer,
    std::uint64_t size,
    std::uint64_t* out_bytes_read) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (out_bytes_read != nullptr) {
        *out_bytes_read = 0;
    }
    if (out_buffer == nullptr || out_bytes_read == nullptr || physical_address == 0 || size == 0) {
        return fail(SMEM_ERR_INVALID_ARGUMENT, L"Physical address, output buffer, size, and byte count are required.");
    }

    std::size_t bytes_read = 0;
    const SmemStatus status = dbvm_adapter::read_physical(
        physical_address,
        out_buffer,
        static_cast<std::size_t>(size),
        &bytes_read);
    *out_bytes_read = bytes_read;

    if (status != SMEM_OK) {
        return fail(status, L"DBVM physical read failed.");
    }
    if (bytes_read != size) {
        return fail(SMEM_ERR_PARTIAL_COPY, L"DBVM physical read returned fewer bytes than requested.");
    }

    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_dbvm_write_physical(
    std::uint64_t physical_address,
    const void* buffer,
    std::uint64_t size,
    std::uint64_t* out_bytes_written) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (out_bytes_written != nullptr) {
        *out_bytes_written = 0;
    }
    if (buffer == nullptr || out_bytes_written == nullptr || physical_address == 0 || size == 0) {
        return fail(SMEM_ERR_INVALID_ARGUMENT, L"Physical address, input buffer, size, and byte count are required.");
    }

    std::size_t bytes_written = 0;
    const SmemStatus status = dbvm_adapter::write_physical(
        physical_address,
        buffer,
        static_cast<std::size_t>(size),
        &bytes_written);
    *out_bytes_written = bytes_written;

    if (status != SMEM_OK) {
        return fail(status, L"DBVM physical write failed.");
    }
    if (bytes_written != size) {
        return fail(SMEM_ERR_PARTIAL_COPY, L"DBVM physical write returned fewer bytes than requested.");
    }

    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_dbvm_read_virtual(
    std::uint64_t cr3,
    std::uint64_t address,
    void* out_buffer,
    std::uint64_t size,
    std::uint64_t* out_bytes_read) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (out_bytes_read != nullptr) {
        *out_bytes_read = 0;
    }
    if (cr3 == 0 || address == 0 || out_buffer == nullptr || size == 0 || out_bytes_read == nullptr) {
        return fail(SMEM_ERR_INVALID_ARGUMENT, L"CR3, virtual address, output buffer, size, and byte count are required.");
    }

    std::size_t bytes_read = 0;
    const SmemStatus status = dbvm_adapter::read_virtual(
        cr3,
        address,
        out_buffer,
        static_cast<std::size_t>(size),
        &bytes_read);
    *out_bytes_read = bytes_read;

    if (status != SMEM_OK) {
        return fail(status, L"DBVM virtual read failed. Check that STUDIOMEM_DBVM_CR3 belongs to the target process.");
    }
    if (bytes_read != size) {
        return fail(SMEM_ERR_PARTIAL_COPY, L"DBVM virtual read returned fewer bytes than requested.");
    }

    set_last_error_message(L"OK");
    return SMEM_OK;
}

__declspec(dllexport) int __stdcall smem_dbvm_write_virtual(
    std::uint64_t cr3,
    std::uint64_t address,
    const void* buffer,
    std::uint64_t size,
    std::uint64_t* out_bytes_written) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (out_bytes_written != nullptr) {
        *out_bytes_written = 0;
    }
    if (cr3 == 0 || address == 0 || buffer == nullptr || size == 0 || out_bytes_written == nullptr) {
        return fail(SMEM_ERR_INVALID_ARGUMENT, L"CR3, virtual address, input buffer, size, and byte count are required.");
    }

    std::size_t bytes_written = 0;
    const SmemStatus status = dbvm_adapter::write_virtual(
        cr3,
        address,
        buffer,
        static_cast<std::size_t>(size),
        &bytes_written);
    *out_bytes_written = bytes_written;

    if (status != SMEM_OK) {
        return fail(status, L"DBVM virtual write failed. Check that STUDIOMEM_DBVM_CR3 belongs to the target process.");
    }
    if (bytes_written != size) {
        return fail(SMEM_ERR_PARTIAL_COPY, L"DBVM virtual write returned fewer bytes than requested.");
    }

    set_last_error_message(L"OK");
    return SMEM_OK;
}

}
