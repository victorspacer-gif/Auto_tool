#include "dbvm_adapter.h"

#include <intrin.h>
#include <windows.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>

extern "C" std::uint64_t smem_vmcall_intel(void* vmcallinfo, std::uint64_t password1, std::uint64_t password3, std::uint64_t* out_rdx);
extern "C" std::uint64_t smem_vmcall_amd(void* vmcallinfo, std::uint64_t password1, std::uint64_t password3, std::uint64_t* out_rdx);

namespace {

constexpr std::uint64_t kPassword1 = 0x0000000076543210ULL;
constexpr std::uint32_t kPassword2 = 0xFEDCBA98UL;
constexpr std::uint64_t kPassword3 = 0x0000000090909090ULL;

constexpr std::uint32_t kVmcallGetVersion = 0;
constexpr std::uint32_t kVmcallReadPhysicalMemory = 3;
constexpr std::uint32_t kVmcallWritePhysicalMemory = 4;

constexpr std::uint64_t kPageSize = 0x1000;
constexpr std::uint64_t kPresent = 1ULL << 0;
constexpr std::uint64_t kLargePage = 1ULL << 7;
constexpr std::uint64_t kPhysicalMask4k = 0x000FFFFFFFFFF000ULL;
constexpr std::uint64_t kPhysicalMask2m = 0x000FFFFFFFE00000ULL;
constexpr std::uint64_t kPhysicalMask1g = 0x000FFFFFC0000000ULL;

enum class CpuVendor {
    Intel,
    Amd,
    Unsupported,
};

#pragma pack(push, 1)
struct DbvmBasicCall {
    std::uint32_t structsize;
    std::uint32_t level2pass;
    std::uint32_t command;
};

struct DbvmReadPhysicalCall {
    std::uint32_t structsize;
    std::uint32_t level2pass;
    std::uint32_t command;
    std::uint64_t source_pa;
    std::uint32_t size;
    std::uint64_t destination_va;
    std::uint32_t nopagefault;
};

struct DbvmWritePhysicalCall {
    std::uint32_t structsize;
    std::uint32_t level2pass;
    std::uint32_t command;
    std::uint64_t destination_pa;
    std::uint32_t size;
    std::uint64_t source_va;
    std::uint32_t nopagefault;
};
#pragma pack(pop)

static_assert(sizeof(DbvmBasicCall) == 12);
static_assert(sizeof(DbvmReadPhysicalCall) == 36);
static_assert(sizeof(DbvmWritePhysicalCall) == 36);

CpuVendor cpu_vendor() {
    int regs[4]{};
    __cpuid(regs, 0);

    char vendor[13]{};
    std::memcpy(vendor + 0, &regs[1], 4);
    std::memcpy(vendor + 4, &regs[3], 4);
    std::memcpy(vendor + 8, &regs[2], 4);

    if (std::strcmp(vendor, "GenuineIntel") == 0) {
        return CpuVendor::Intel;
    }
    if (std::strcmp(vendor, "AuthenticAMD") == 0) {
        return CpuVendor::Amd;
    }
    return CpuVendor::Unsupported;
}

std::uint64_t safe_vmcall(void* call) {
    const CpuVendor vendor = cpu_vendor();
    if (vendor == CpuVendor::Unsupported) {
        return 0;
    }

    __try {
        std::uint64_t ignored = 0;
        if (vendor == CpuVendor::Amd) {
            return smem_vmcall_amd(call, kPassword1, kPassword3, &ignored);
        }
        return smem_vmcall_intel(call, kPassword1, kPassword3, &ignored);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

bool dbvm_present(std::uint32_t* out_version) {
    DbvmBasicCall call{
        static_cast<std::uint32_t>(sizeof(DbvmBasicCall)),
        kPassword2,
        kVmcallGetVersion,
    };

    const std::uint64_t result = safe_vmcall(&call);
    if ((result >> 24) != 0xCE) {
        if (out_version != nullptr) {
            *out_version = 0;
        }
        return false;
    }

    if (out_version != nullptr) {
        *out_version = static_cast<std::uint32_t>(result);
    }
    return true;
}

std::size_t page_limited_size(std::uint64_t address, std::size_t remaining, std::uint64_t page_size = kPageSize) {
    const std::uint64_t page_remaining = page_size - (address & (page_size - 1));
    return static_cast<std::size_t>((std::min<std::uint64_t>)(page_remaining, remaining));
}

SmemStatus read_u64_physical(std::uint64_t physical_address, std::uint64_t* value) {
    std::size_t bytes_read = 0;
    const SmemStatus status = dbvm_adapter::read_physical(physical_address, value, sizeof(*value), &bytes_read);
    if (status != SMEM_OK) {
        return status;
    }
    return bytes_read == sizeof(*value) ? SMEM_OK : SMEM_ERR_PARTIAL_COPY;
}

SmemStatus translate_virtual(std::uint64_t cr3, std::uint64_t virtual_address, std::uint64_t* physical_address, std::uint64_t* page_size) {
    if (cr3 == 0 || physical_address == nullptr || page_size == nullptr) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }

    const std::uint64_t pml4_index = (virtual_address >> 39) & 0x1FF;
    const std::uint64_t pdpt_index = (virtual_address >> 30) & 0x1FF;
    const std::uint64_t pd_index = (virtual_address >> 21) & 0x1FF;
    const std::uint64_t pt_index = (virtual_address >> 12) & 0x1FF;
    const std::uint64_t offset4k = virtual_address & 0xFFF;

    std::uint64_t pml4e = 0;
    SmemStatus status = read_u64_physical((cr3 & kPhysicalMask4k) + pml4_index * 8, &pml4e);
    if (status != SMEM_OK) {
        return status;
    }
    if ((pml4e & kPresent) == 0) {
        return SMEM_ERR_INVALID_ADDRESS;
    }

    std::uint64_t pdpte = 0;
    status = read_u64_physical((pml4e & kPhysicalMask4k) + pdpt_index * 8, &pdpte);
    if (status != SMEM_OK) {
        return status;
    }
    if ((pdpte & kPresent) == 0) {
        return SMEM_ERR_INVALID_ADDRESS;
    }
    if ((pdpte & kLargePage) != 0) {
        *page_size = 0x40000000ULL;
        *physical_address = (pdpte & kPhysicalMask1g) + (virtual_address & 0x3FFFFFFFULL);
        return SMEM_OK;
    }

    std::uint64_t pde = 0;
    status = read_u64_physical((pdpte & kPhysicalMask4k) + pd_index * 8, &pde);
    if (status != SMEM_OK) {
        return status;
    }
    if ((pde & kPresent) == 0) {
        return SMEM_ERR_INVALID_ADDRESS;
    }
    if ((pde & kLargePage) != 0) {
        *page_size = 0x200000ULL;
        *physical_address = (pde & kPhysicalMask2m) + (virtual_address & 0x1FFFFFULL);
        return SMEM_OK;
    }

    std::uint64_t pte = 0;
    status = read_u64_physical((pde & kPhysicalMask4k) + pt_index * 8, &pte);
    if (status != SMEM_OK) {
        return status;
    }
    if ((pte & kPresent) == 0) {
        return SMEM_ERR_INVALID_ADDRESS;
    }

    *page_size = kPageSize;
    *physical_address = (pte & kPhysicalMask4k) + offset4k;
    return SMEM_OK;
}

}  // namespace

namespace dbvm_adapter {

SmemStatus initialize() {
    return dbvm_present(nullptr) ? SMEM_OK : SMEM_ERR_DRIVER_UNAVAILABLE;
}

SmemStatus version(std::uint32_t* out_version) {
    if (out_version == nullptr) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }
    return dbvm_present(out_version) ? SMEM_OK : SMEM_ERR_DRIVER_UNAVAILABLE;
}

SmemStatus read_physical(
    std::uint64_t physical_address,
    void* out_buffer,
    std::size_t size,
    std::size_t* out_bytes_read) {
    if (out_bytes_read != nullptr) {
        *out_bytes_read = 0;
    }
    if (physical_address == 0 || out_buffer == nullptr || size == 0 || out_bytes_read == nullptr) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }
    if (!dbvm_present(nullptr)) {
        return SMEM_ERR_DRIVER_UNAVAILABLE;
    }

    auto* cursor = static_cast<unsigned char*>(out_buffer);
    std::uint64_t current = physical_address;
    std::size_t remaining = size;

    while (remaining > 0) {
        const std::size_t chunk = (std::min<std::size_t>)(remaining, 0x1000);
        DbvmReadPhysicalCall call{};
        call.structsize = sizeof(call);
        call.level2pass = kPassword2;
        call.command = kVmcallReadPhysicalMemory;
        call.source_pa = current;
        call.size = static_cast<std::uint32_t>(chunk);
        call.destination_va = reinterpret_cast<std::uint64_t>(cursor);
        call.nopagefault = 0;

        const std::uint64_t bytes_left = safe_vmcall(&call);
        const std::size_t copied = chunk >= bytes_left ? chunk - static_cast<std::size_t>(bytes_left) : 0;
        *out_bytes_read += copied;
        if (copied != chunk) {
            return *out_bytes_read == 0 ? SMEM_ERR_INVALID_ADDRESS : SMEM_ERR_PARTIAL_COPY;
        }

        cursor += chunk;
        current += chunk;
        remaining -= chunk;
    }

    return SMEM_OK;
}

SmemStatus write_physical(
    std::uint64_t physical_address,
    const void* buffer,
    std::size_t size,
    std::size_t* out_bytes_written) {
    if (out_bytes_written != nullptr) {
        *out_bytes_written = 0;
    }
    if (physical_address == 0 || buffer == nullptr || size == 0 || out_bytes_written == nullptr) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }
    if (!dbvm_present(nullptr)) {
        return SMEM_ERR_DRIVER_UNAVAILABLE;
    }

    const auto* cursor = static_cast<const unsigned char*>(buffer);
    std::uint64_t current = physical_address;
    std::size_t remaining = size;

    while (remaining > 0) {
        const std::size_t chunk = (std::min<std::size_t>)(remaining, 0x1000);
        DbvmWritePhysicalCall call{};
        call.structsize = sizeof(call);
        call.level2pass = kPassword2;
        call.command = kVmcallWritePhysicalMemory;
        call.destination_pa = current;
        call.size = static_cast<std::uint32_t>(chunk);
        call.source_va = reinterpret_cast<std::uint64_t>(cursor);
        call.nopagefault = 0;

        const std::uint64_t bytes_left = safe_vmcall(&call);
        const std::size_t copied = chunk >= bytes_left ? chunk - static_cast<std::size_t>(bytes_left) : 0;
        *out_bytes_written += copied;
        if (copied != chunk) {
            return *out_bytes_written == 0 ? SMEM_ERR_INVALID_ADDRESS : SMEM_ERR_PARTIAL_COPY;
        }

        cursor += chunk;
        current += chunk;
        remaining -= chunk;
    }

    return SMEM_OK;
}

SmemStatus read_virtual(
    std::uint64_t cr3,
    std::uint64_t address,
    void* out_buffer,
    std::size_t size,
    std::size_t* out_bytes_read) {
    if (out_bytes_read != nullptr) {
        *out_bytes_read = 0;
    }
    if (cr3 == 0 || address == 0 || out_buffer == nullptr || size == 0 || out_bytes_read == nullptr) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }

    auto* cursor = static_cast<unsigned char*>(out_buffer);
    std::uint64_t current = address;
    std::size_t remaining = size;

    while (remaining > 0) {
        std::uint64_t physical = 0;
        std::uint64_t translated_page_size = 0;
        SmemStatus status = translate_virtual(cr3, current, &physical, &translated_page_size);
        if (status != SMEM_OK) {
            return status;
        }

        const std::size_t chunk = page_limited_size(physical, remaining, translated_page_size);
        std::size_t chunk_read = 0;
        status = read_physical(physical, cursor, chunk, &chunk_read);
        *out_bytes_read += chunk_read;
        if (status != SMEM_OK) {
            return status;
        }
        if (chunk_read != chunk) {
            return SMEM_ERR_PARTIAL_COPY;
        }

        cursor += chunk;
        current += chunk;
        remaining -= chunk;
    }

    return SMEM_OK;
}

SmemStatus write_virtual(
    std::uint64_t cr3,
    std::uint64_t address,
    const void* buffer,
    std::size_t size,
    std::size_t* out_bytes_written) {
    if (out_bytes_written != nullptr) {
        *out_bytes_written = 0;
    }
    if (cr3 == 0 || address == 0 || buffer == nullptr || size == 0 || out_bytes_written == nullptr) {
        return SMEM_ERR_INVALID_ARGUMENT;
    }

    const auto* cursor = static_cast<const unsigned char*>(buffer);
    std::uint64_t current = address;
    std::size_t remaining = size;

    while (remaining > 0) {
        std::uint64_t physical = 0;
        std::uint64_t translated_page_size = 0;
        SmemStatus status = translate_virtual(cr3, current, &physical, &translated_page_size);
        if (status != SMEM_OK) {
            return status;
        }

        const std::size_t chunk = page_limited_size(physical, remaining, translated_page_size);
        std::size_t chunk_written = 0;
        status = write_physical(physical, cursor, chunk, &chunk_written);
        *out_bytes_written += chunk_written;
        if (status != SMEM_OK) {
            return status;
        }
        if (chunk_written != chunk) {
            return SMEM_ERR_PARTIAL_COPY;
        }

        cursor += chunk;
        current += chunk;
        remaining -= chunk;
    }

    return SMEM_OK;
}

}  // namespace dbvm_adapter
