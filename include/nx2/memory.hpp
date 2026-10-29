#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

namespace nx2 {

// Source-owned generic guest-memory experiment only. No Switch 2 MMU or ABI.
// The caller owns the storage and its lifetime. An access must lie within
// one explicitly admitted region; host pointers never become guest addresses.
struct GuestMemoryRegion {
    std::uint64_t guest_base = 0;
    std::span<std::byte> bytes{};
    bool can_read = false;
    bool can_write = false;
};

class GuestMemoryView {
public:
    explicit GuestMemoryView(std::span<GuestMemoryRegion> regions) noexcept
        : regions_(regions) {}

    // All-or-nothing 64-bit little-endian access. Refuse mapped-but-denied,
    // unmapped, overlapping-authority, overflow and boundary-crossing cases.
    [[nodiscard]] std::optional<std::uint64_t> load64(
        std::uint64_t address) const noexcept;
    [[nodiscard]] bool store64(
        std::uint64_t address, std::uint64_t value) const noexcept;

private:
    [[nodiscard]] GuestMemoryRegion* find_unique_region(
        std::uint64_t address, bool writing) const noexcept;
    std::span<GuestMemoryRegion> regions_;
};

}  // namespace nx2
