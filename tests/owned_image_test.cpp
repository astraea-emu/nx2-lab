#include <nx2/owned_image.hpp>
#include <nx2/cpu.hpp>
#include <array>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <stdexcept>

namespace {
void require(bool ok, const char* why) {
    if (!ok) throw std::runtime_error(why);
}
}  // namespace

int main() {
    using nx2::parse_owned_image;
    // Explicit source-owned NX2OWNED header, MOVZ X0,#42; ADD X0,X0,#1; BRK.
    constexpr std::array<std::byte, 28> source = {
        std::byte{'N'}, std::byte{'X'}, std::byte{'2'}, std::byte{'O'},
        std::byte{1}, std::byte{0}, std::byte{0}, std::byte{0},
        std::byte{0}, std::byte{0}, std::byte{0}, std::byte{0},
        std::byte{3}, std::byte{0}, std::byte{0}, std::byte{0},
        std::byte{0x40}, std::byte{0x05}, std::byte{0x80}, std::byte{0xD2},
        std::byte{0x00}, std::byte{0x04}, std::byte{0x00}, std::byte{0x91},
        std::byte{0x00}, std::byte{0x00}, std::byte{0x20}, std::byte{0xD4},
    };
    auto original = parse_owned_image(source);
    require(original.has_value() && original->word_count == 3 &&
            original->entry_offset == 0, "valid source-owned image rejected");
    nx2::CpuState state;
    state.pc = original->entry_offset;
    const auto result = nx2::run_owned_program(original->program(), 8, state);
    require(result.stop == nx2::StopReason::breakpoint &&
            result.retired == 2 && result.state.x[0] == 43 &&
            result.state.pc == 8, "image execution divergence");

    auto mutate = source;
    mutate[0] = std::byte{0};
    require(!parse_owned_image(mutate), "forged magic admitted");
    mutate = source;
    mutate[4] = std::byte{2};
    require(!parse_owned_image(mutate), "unsupported version admitted");
    mutate = source;
    mutate[6] = std::byte{1};
    require(!parse_owned_image(mutate), "reserved flag admitted");
    mutate = source;
    mutate[12] = std::byte{4};
    require(!parse_owned_image(mutate), "wrong count admitted");
    mutate = source;
    mutate[8] = std::byte{1};
    require(!parse_owned_image(mutate), "misaligned entry admitted");
    mutate = source;
    mutate[8] = std::byte{12};
    require(!parse_owned_image(mutate), "out-of-program entry admitted");
    require(!parse_owned_image(std::span<const std::byte>{source.data(), 15}),
            "truncated header admitted");
    require(!parse_owned_image(std::span<const std::byte>{source.data(), 27}),
            "truncated body admitted");
    mutate = source;
    mutate[12] = std::byte{0};
    require(!parse_owned_image(mutate), "zero program count admitted");
    constexpr std::array<std::byte, 0> empty{};
    require(!parse_owned_image(empty), "empty source admitted");
    std::cout << "OWNED_EXECUTABLE_IMAGE_CONTRACT_PASS:12_checks\n";
}
