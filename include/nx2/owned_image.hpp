#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

namespace nx2 {

// NX2OWNED v1 is an Astraea-independent, project-owned *test* container.
// It is NOT NRO, NSO, NCA, XCI, a Switch 2 executable or firmware format.
// Header bytes: "NX2O", u16 version(1), u16 flags(0),
// u32 entry_byte_offset, u32 number_of_32_bit_words, then LE words.
inline constexpr std::size_t kMaxOwnedWords = 4096;
inline constexpr std::size_t kOwnedHeaderSize = 16;

struct OwnedImage {
    std::array<std::uint32_t, kMaxOwnedWords> words{};
    std::size_t word_count = 0;
    std::uint32_t entry_offset = 0;

    [[nodiscard]] std::span<const std::uint32_t> program() const noexcept {
        return {words.data(), word_count};
    }
};

[[nodiscard]] std::optional<OwnedImage> parse_owned_image(
    std::span<const std::byte> file) noexcept;

}  // namespace nx2
