// SPDX-License-Identifier: MIT
// NX2-authored independent probe; compiled only with frozen external NeXo source.
#include <cstdint>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#include "test_framework.hpp"
#include "system.hpp"

#ifndef NEXO2_TEST_DATA_DIR
#error "Frozen candidate test directory must be defined"
#endif

namespace {
std::vector<std::uint8_t> FrozenNro() {
    std::ifstream f(std::string(NEXO2_TEST_DATA_DIR) + "/hello.nro", std::ios::binary);
    return {std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>()};
}
}

TEST(Nx2_OriginalNroExecutesToExit) {
    const auto source = FrozenNro();
    CHECK_EQ(source.size(), 24636U);
    if (source.size() != 24636U) return;
    NeXo2::Core::System sys;
    const bool loaded = sys.LoadNro(source, "hello.nro");
    CHECK(loaded);
    if (!loaded) return;
    CHECK(sys.GetNroInfo() != nullptr);
    CHECK_EQ(sys.GetCpu().GetState().pc, NeXo2::HLE::Layout::CODE_BASE);
    const auto retired = sys.Run(10'000'000);
    CHECK(retired > 0);
    CHECK(sys.GetKernel().HasExited());
    const auto& output = sys.GetKernel().GetDebugOutput();
    CHECK(output.find("Contador (.data): 42") != std::string::npos);
    CHECK(output.find("Suma en el heap: 499500") != std::string::npos);
    CHECK(output.find("fibonacci(50) = 12586269025") != std::string::npos);
    CHECK_EQ(sys.GetKernel().GetHeapSize(), 0x200000U);
}

TEST(Nx2_NroRejectsDamagedImage) {
    const auto original = FrozenNro();
    CHECK_EQ(original.size(), 24636U);
    if (original.size() != 24636U) return;
    NeXo2::Core::System too_short;
    CHECK(!too_short.LoadNro(std::vector<std::uint8_t>(16, 0), "short.nro"));
    CHECK(!too_short.GetLastError().empty());
    auto invalid_magic = original;
    invalid_magic.at(0x10) = 'X';
    NeXo2::Core::System bad_magic;
    CHECK(!bad_magic.LoadNro(invalid_magic, "bad-magic.nro"));
    CHECK(bad_magic.GetLastError().find("NRO0") != std::string::npos);
    std::vector<std::uint8_t> truncated(original.begin(), original.begin() + 0x200);
    NeXo2::Core::System incomplete;
    CHECK(!incomplete.LoadNro(truncated, "incomplete.nro"));
    CHECK(!incomplete.GetLastError().empty());
}

TEST(Nx2_UnsupportedSvcDoesNotPretendToSucceed) {
    NeXo2::Core::System sys;
    // Synthetic unsupported probe, NOT part of the original NRO program.
    constexpr std::uint32_t program[] = {0xD40005C1U}; // SVC #0x2e
    sys.LoadRawProgram(program, 1, NeXo2::HLE::Layout::CODE_BASE);
    CHECK(sys.Run(10) <= 10);
    CHECK(sys.GetCpu().IsHalted());
    CHECK(sys.GetCpu().GetHaltReason().find("GetDebugFutureThreadInfo") != std::string::npos);
}
