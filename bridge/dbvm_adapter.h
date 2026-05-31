#pragma once

#include "studiomem_bridge.h"

#include <cstddef>
#include <cstdint>

namespace dbvm_adapter {

SmemStatus initialize();
SmemStatus version(std::uint32_t* out_version);

SmemStatus read_virtual(
    std::uint64_t cr3,
    std::uint64_t address,
    void* out_buffer,
    std::size_t size,
    std::size_t* out_bytes_read);

SmemStatus write_virtual(
    std::uint64_t cr3,
    std::uint64_t address,
    const void* buffer,
    std::size_t size,
    std::size_t* out_bytes_written);

}  // namespace dbvm_adapter
