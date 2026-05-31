#pragma once

#include <cstdint>

enum SmemStatus : int {
    SMEM_OK = 0,
    SMEM_ERR_NOT_INITIALIZED = 1,
    SMEM_ERR_DRIVER_UNAVAILABLE = 2,
    SMEM_ERR_PROCESS_NOT_FOUND = 3,
    SMEM_ERR_INVALID_ARGUMENT = 4,
    SMEM_ERR_INVALID_ADDRESS = 5,
    SMEM_ERR_PARTIAL_COPY = 6,
    SMEM_ERR_ACCESS_DENIED = 7,
    SMEM_ERR_INTERNAL = 100,
};

extern "C" {

__declspec(dllexport) int __stdcall smem_initialize();
__declspec(dllexport) int __stdcall smem_shutdown();

__declspec(dllexport) int __stdcall smem_attach_process(
    const wchar_t* process_name,
    std::uint32_t* out_pid);

__declspec(dllexport) int __stdcall smem_open_process(std::uint32_t pid);
__declspec(dllexport) int __stdcall smem_close_process();

__declspec(dllexport) int __stdcall smem_get_module_base(
    std::uint32_t pid,
    const wchar_t* module_name,
    std::uint64_t* out_base,
    std::uint64_t* out_size);

__declspec(dllexport) int __stdcall smem_read_virtual(
    std::uint32_t pid,
    std::uint64_t address,
    void* out_buffer,
    std::uint64_t size,
    std::uint64_t* out_bytes_read);

__declspec(dllexport) int __stdcall smem_write_virtual(
    std::uint32_t pid,
    std::uint64_t address,
    const void* buffer,
    std::uint64_t size,
    std::uint64_t* out_bytes_written);

__declspec(dllexport) int __stdcall smem_last_error(
    wchar_t* buffer,
    std::uint32_t buffer_chars);

__declspec(dllexport) int __stdcall smem_dbvm_initialize();

__declspec(dllexport) int __stdcall smem_dbvm_get_version(
    std::uint32_t* out_version);

__declspec(dllexport) int __stdcall smem_dbvm_read_virtual(
    std::uint64_t cr3,
    std::uint64_t address,
    void* out_buffer,
    std::uint64_t size,
    std::uint64_t* out_bytes_read);

__declspec(dllexport) int __stdcall smem_dbvm_write_virtual(
    std::uint64_t cr3,
    std::uint64_t address,
    const void* buffer,
    std::uint64_t size,
    std::uint64_t* out_bytes_written);

}
