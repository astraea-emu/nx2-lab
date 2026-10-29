#include <nx2/owned_image.hpp>

#include <cstddef>
#include <cstdint>

namespace nx2 {
namespace {
[[nodiscard]] std::uint32_t read_le32(
    std::span<const std::byte> file, std::size_t at) noexcept {
    std::uint32_t out = 0;
    for (std::size_t i = 0; i < 4; ++i) {
        out |= static_cast<std::uint32_t>(
                   std::to_integer<unsigned int>(file[at + i])) << (8U * i);
    }
    return out;
}
[[nodiscard]] std::uint16_t read_le16(
    std::span<const std::byte> file, std::size_t at) noexcept {
    return static_cast<std::uint16_t>(
        std::to_integer<unsigned int>(file[at]) |
        (std::to_integer<unsigned int>(file[at + 1]) << 8U));
}
}  // namespace

std::optional<OwnedImage> parse_owned_image(
    std::span<const std::byte> file) noexcept {
    if (file.size() < kOwnedHeaderSize ||
        file.size() > kOwnedHeaderSize + 4U * kMaxOwnedWords ||
        file[0] != std::byte{'N'} || file[1] != std::byte{'X'} ||
        file[2] != std::byte{'2'} || file[3] != std::byte{'O'} ||
        read_le16(file, 4) != 1U || read_le16(file, 6) != 0U) {
        return std::nullopt;
    }
    const auto entry = read_le32(file, 8);
    const auto count = read_le32(file, 12);
    if (count == 0 || count > kMaxOwnedWords ||
        file.size() != kOwnedHeaderSize + 4U * count ||
        entry % 4U != 0U || entry / 4U >= count) {
        return std::nullopt;
    }
    OwnedImage out;
    out.entry_offset = entry;
    out.word_count = count;
    for (std::size_t i = 0; i < count; ++i) {
        out.words[i] = read_le32(file, kOwnedHeaderSize + 4U * i);
    }
    return out;
}
}  // namespace nx2
