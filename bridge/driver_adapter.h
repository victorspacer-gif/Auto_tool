#pragma once

#include "studiomem_bridge.h"

#include <cstddef>
#include <cstdint>

namespace driver_adapter {

SmemStatus initialize();
void shutdown();

SmemStatus open_process(std::uint32_t pid);
void close_process();

SmemStatus resolve_process_eprocess(std::uint32_t pid, std::uint64_t* out_eprocess);
SmemStatus resolve_process_cr3(std::uint32_t pid, std::uint64_t* out_cr3);

SmemStatus read_virtual_chunk(
    std::uint32_t pid,
    std::uint64_t address,
    void* out_buffer,
    std::size_t size,
    std::size_t* out_bytes_read);

SmemStatus write_virtual_chunk(
    std::uint32_t pid,
    std::uint64_t address,
    const void* buffer,
    std::size_t size,
    std::size_t* out_bytes_written);

}  // namespace driver_adapter
