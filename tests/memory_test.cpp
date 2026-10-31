#include <nx2/cpu.hpp>
#include <nx2/memory.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
void require(bool value, const char* reason) {
    if (!value) throw std::runtime_error(reason);
}
}  // namespace

int main() {
    using nx2::GuestMemoryRegion;
    using nx2::GuestMemoryView;
    using nx2::StopReason;
    constexpr std::uint64_t kBase = 0x2000;
    std::array<std::byte, 32> data{};
    std::array<GuestMemoryRegion, 1> regions{{
        GuestMemoryRegion{kBase, data, true, true},
    }};
    GuestMemoryView memory(regions);
    require(memory.store64(kBase, 0x0123456789ABCDEFULL), "store failed");
    require(memory.load64(kBase).value() == 0x0123456789ABCDEFULL,
            "little-endian readback wrong");
    require(data[0] == std::byte{0xEF} && data[7] == std::byte{0x01},
            "little-endian byte order wrong");
    require(!memory.load64(kBase + 25).has_value(), "cross-boundary read");
    require(!memory.store64(kBase + 25, 0x55), "cross-boundary write");
    require(!memory.load64(kBase - 1).has_value(), "unmapped-before read");
    require(!memory.store64(kBase + 32, 1), "unmapped-after write");
    require(!memory.load64(std::numeric_limits<std::uint64_t>::max()).has_value(),
            "address-overflow read");
    require(!memory.store64(std::numeric_limits<std::uint64_t>::max(), 1),
            "address-overflow write");
    regions[0].can_write = false;
    require(!memory.store64(kBase, 0), "read-only region writable");
    require(memory.load64(kBase).value() == 0x0123456789ABCDEFULL,
            "read-only denial changed bytes");
    regions[0].can_write = true;
    regions[0].can_read = false;
    require(!memory.load64(kBase).has_value(), "write-only region readable");
    regions[0].can_read = true;

    std::array<std::byte, 32> shadow{};
    std::array<GuestMemoryRegion, 2> aliases{{
        GuestMemoryRegion{kBase, data, true, true},
        GuestMemoryRegion{kBase, shadow, true, true},
    }};
    GuestMemoryView ambiguous(aliases);
    require(!ambiguous.store64(kBase, 123) && !ambiguous.load64(kBase).has_value(),
            "ambiguous overlap admitted");
    require(memory.load64(kBase).value() == 0x0123456789ABCDEFULL,
            "ambiguous write changed primary bytes");
    require(shadow[0] == std::byte{0}, "ambiguous write changed alias");

    std::array<GuestMemoryRegion, 2> partial_alias{{
        GuestMemoryRegion{kBase, data, true, true},
        GuestMemoryRegion{kBase + 4, std::span<std::byte>{shadow.data(), 4},
                          true, true},
    }};
    GuestMemoryView partial_ambiguous(partial_alias);
    require(!partial_ambiguous.store64(kBase, 4) &&
            !partial_ambiguous.load64(kBase).has_value(),
            "partially overlapping region admitted");
    require(memory.load64(kBase).value() == 0x0123456789ABCDEFULL,
            "partial overlap corrupted primary bytes");

    // A genuine source-authored program, not a Switch 2 binary:
    // STR X0,[X1]; LDR X2,[X1]; BRK. All operands are generic AArch64.
    constexpr std::array<std::uint32_t, 3> program = {
        0xF9000020U, 0xF9400022U, 0xD4200000U};
    nx2::CpuState initial;
    initial.x[0] = 0xCAFEBABE11223344ULL;
    initial.x[1] = kBase + 8;
    const auto done = nx2::run_owned_program(program, 6, initial, &memory);
    require(done.stop == StopReason::breakpoint && done.retired == 2 &&
            done.state.pc == 8 && done.state.x[2] == initial.x[0],
            "source-authored STR/LDR/BRK progression wrong");
    require(memory.load64(kBase + 8).value() == initial.x[0],
            "source-authored store did not commit");

    regions[0].can_write = false;
    const auto denied = nx2::run_owned_program(program, 6, initial, &memory);
    require(denied.stop == StopReason::data_access_fault && denied.retired == 0 &&
            denied.state.pc == 0 && denied.state.x[2] == 0 &&
            memory.load64(kBase + 8).value() == initial.x[0],
            "write fault retired or changed guest state");
    regions[0].can_write = true;
    regions[0].can_read = false;
    const auto read_denied = nx2::run_owned_program(
        std::array<std::uint32_t, 2>{0xF9400022U, 0xD4200000U},
        4, initial, &memory);
    require(read_denied.stop == StopReason::data_access_fault &&
            read_denied.retired == 0 && read_denied.state.x[2] == 0,
            "read fault retired or changed state");
    regions[0].can_read = true;
    const auto no_memory = nx2::run_owned_program(program, 4, initial);
    require(no_memory.stop == StopReason::data_access_fault &&
            no_memory.retired == 0, "unmapped memory accepted");
    nx2::CpuState overflow = initial;
    overflow.x[1] = std::numeric_limits<std::uint64_t>::max() - 7;
    const auto bad_offset = nx2::run_owned_program(
        std::array<std::uint32_t, 1>{0xF9000420U}, 1, overflow, &memory);
    require(bad_offset.stop == StopReason::data_access_fault &&
            bad_offset.retired == 0, "overflowed scaled offset accepted");

    // SP base (Rn=31) has not been implemented and is explicitly unsupported.
    const auto unmodelled_sp = nx2::run_owned_program(
        std::array<std::uint32_t, 1>{0xF90003E0U}, 1, initial, &memory);
    require(unmodelled_sp.stop == StopReason::unsupported_instruction &&
            unmodelled_sp.retired == 0, "unmodelled SP access accepted");

    // Unsigned scaled offset 8 bytes: STR X0,[X1,#8].
    constexpr std::array<std::uint32_t, 2> scaled = {
        0xF9000420U, 0xD4200000U};
    nx2::CpuState base_start = initial;
    base_start.x[1] = kBase;
    const auto shifted = nx2::run_owned_program(scaled, 4, base_start, &memory);
    require(shifted.retired == 1 && shifted.stop == StopReason::breakpoint &&
            memory.load64(kBase + 8).value() == initial.x[0],
            "scaled offset store incorrect");
    std::cout << "OWNED_GUEST_MEMORY_CONTRACT_PASS\n";
}
