#include <nx2/cpu.hpp>
#include <nx2/owned_image.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <fstream>
#include <iterator>
#include <vector>
#include <string_view>

int main(int argc, char** argv) {
    if ((argc != 2 && argc != 3) || argc < 2) {
        std::cerr << "Usage: nx2lab demo|memory-demo|run-owned PATH (no Switch 2 execution)\n";
        return 2;
    }
    const std::string_view mode(argv[1]);
    if (mode == "run-owned" && argc == 3) {
        // NX2OWNED is an original, bounded test container, not a Nintendo
        // executable format. No file-supplied host operations are performed.
        std::ifstream stream(argv[2], std::ios::binary | std::ios::ate);
        if (!stream) {
            std::cerr << "OWNED_IMAGE_REFUSED:file_open\n";
            return 1;
        }
        const auto size = stream.tellg();
        if (size < 0 || size > static_cast<std::streamoff>(
                nx2::kOwnedHeaderSize + 4U * nx2::kMaxOwnedWords)) {
            std::cerr << "OWNED_IMAGE_REFUSED:file_size\n";
            return 1;
        }
        std::vector<std::byte> raw(static_cast<std::size_t>(size));
        stream.seekg(0);
        if (!stream.read(reinterpret_cast<char*>(raw.data()), size)) {
            std::cerr << "OWNED_IMAGE_REFUSED:read_failure\n";
            return 1;
        }
        const auto image = nx2::parse_owned_image(raw);
        if (!image.has_value()) {
            std::cerr << "OWNED_IMAGE_REFUSED:invalid_format\n";
            return 1;
        }
        nx2::CpuState state;
        state.pc = image->entry_offset;
        const auto result = nx2::run_owned_program(image->program(), 4096, state);
        std::cout << "research_only=1\nswitch2_guest_execution=0\n"
                  << "image_format=NX2OWNED_v1\n"
                  << "stop=" << nx2::stop_reason_name(result.stop) << "\n"
                  << "retired=" << result.retired << "\n"
                  << "pc=" << result.state.pc << "\n"
                  << "x0=" << result.state.x[0] << "\n";
        if (result.stop == nx2::StopReason::service_request) {
            std::cout << "service_immediate=" << result.service_immediate << "\n"
                      << "caller_x1=" << result.state.x[1] << "\n"
                      << "service_dispatched=0\n";
        }
        return result.stop == nx2::StopReason::breakpoint ||
                       result.stop == nx2::StopReason::service_request ? 0 : 1;
    }
    if (mode == "demo" && argc == 2) {
        // MOVZ X0,#42 ; ADD X0,X0,#1 ; BRK #0
        constexpr std::array<std::uint32_t, 3> words = {
            0xD2800540U, 0x91000400U, 0xD4200000U};
        const auto result = nx2::run_owned_program(words, 8);
        std::cout << "research_only=1\n"
                  << "switch2_guest_execution=0\n"
                  << "retired=" << result.retired << "\n"
                  << "stop=" << nx2::stop_reason_name(result.stop) << "\n"
                  << "x0=" << result.state.x[0] << "\n"
                  << "pc=" << result.state.pc << "\n";
        return result.stop == nx2::StopReason::breakpoint &&
                       result.retired == 2 && result.state.x[0] == 43 &&
                       result.state.pc == 8 ? 0 : 1;
    }
    if (mode == "memory-demo" && argc == 2) {
        // STR X0,[X1] ; LDR X2,[X1] ; BRK #0.
        // Native compiler-generated AArch64 encoding independently checked.
        constexpr std::array<std::uint32_t, 3> words = {
            0xF9000020U, 0xF9400022U, 0xD4200000U};
        std::array<std::byte, 16> bytes{};
        std::array<nx2::GuestMemoryRegion, 1> regions{{
            nx2::GuestMemoryRegion{0x2000U, bytes, true, true},
        }};
        nx2::GuestMemoryView memory(regions);
        nx2::CpuState initial;
        initial.x[0] = 0x11223344U;
        initial.x[1] = 0x2000U;
        const auto result = nx2::run_owned_program(words, 8, initial, &memory);
        const auto saved = memory.load64(0x2000U);
        std::cout << "research_only=1\n"
                  << "switch2_guest_execution=0\n"
                  << "retired=" << result.retired << "\n"
                  << "stop=" << nx2::stop_reason_name(result.stop) << "\n"
                  << "x2=" << result.state.x[2] << "\n"
                  << "stored=" << saved.value_or(0U) << "\n"
                  << "pc=" << result.state.pc << "\n";
        return result.stop == nx2::StopReason::breakpoint &&
                       result.retired == 2 && result.state.x[2] == 0x11223344U &&
                       saved == std::optional<std::uint64_t>{0x11223344U} &&
                       result.state.pc == 8 ? 0 : 1;
    }
    std::cerr << "Usage: nx2lab demo|memory-demo|run-owned PATH (no Switch 2 execution)\n";
    return 2;
}
