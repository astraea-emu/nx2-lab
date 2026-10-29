#include <nx2/memory.hpp>

#include <cstddef>
#include <cstdint>
#include <limits>

namespace nx2 {
namespace {
constexpr std::uint64_t kWordBytes = 8;

[[nodiscard]] bool valid_region_extent(const GuestMemoryRegion& region) noexcept {
    return !region.bytes.empty() &&
           region.guest_base <= std::numeric_limits<std::uint64_t>::max() -
                                    static_cast<std::uint64_t>(region.bytes.size());
}
}  // namespace

GuestMemoryRegion* GuestMemoryView::find_unique_region(
    std::uint64_t address, bool writing) const noexcept {
    if (address > std::numeric_limits<std::uint64_t>::max() - kWordBytes) {
        return nullptr;
    }
    const auto access_end = address + kWordBytes;
    GuestMemoryRegion* unique = nullptr;
    for (auto& region : regions_) {
        if (!valid_region_extent(region)) {
            // A malformed region must not authorize access, even if its
            // virtual extent wraps back into the address space.
            return nullptr;
        }
        const auto region_end = region.guest_base + region.bytes.size();
        if (address >= region_end || access_end <= region.guest_base) {
            continue;
        }
        // A partial overlap is ambiguous too, not just two full mappings.
        // One access must fit wholly in exactly one authorized region.
        if (unique != nullptr || address < region.guest_base ||
            access_end > region_end) {
            return nullptr;
        }
        unique = &region;
    }
    if (unique == nullptr || (writing ? !unique->can_write : !unique->can_read)) {
        return nullptr;
    }
    return unique;
}

std::optional<std::uint64_t> GuestMemoryView::load64(
    std::uint64_t address) const noexcept {
    const auto* region = find_unique_region(address, false);
    if (region == nullptr) {
        return std::nullopt;
    }
    const auto offset = static_cast<std::size_t>(address - region->guest_base);
    std::uint64_t value = 0;
    for (std::size_t i = 0; i < kWordBytes; ++i) {
        value |= static_cast<std::uint64_t>(
                     std::to_integer<unsigned int>(region->bytes[offset + i]))
                 << (i * 8U);
    }
    return value;
}

bool GuestMemoryView::store64(
    std::uint64_t address, std::uint64_t value) const noexcept {
    auto* region = find_unique_region(address, true);
    if (region == nullptr) {
        return false;
    }
    const auto offset = static_cast<std::size_t>(address - region->guest_base);
    for (std::size_t i = 0; i < kWordBytes; ++i) {
        region->bytes[offset + i] =
            static_cast<std::byte>((value >> (i * 8U)) & 0xFFU);
    }
    return true;
}
}  // namespace nx2
