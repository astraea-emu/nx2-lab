#include <nx2/cpu.hpp>
#include <nx2/memory.hpp>
#include <nx2/owned_service.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <stdexcept>

namespace {
void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
constexpr std::uint32_t svc(std::uint16_t imm) {
    // A64 SVC #imm16: 11010100 000 imm16 00001
    return 0xD4000001U | (static_cast<std::uint32_t>(imm) << 5U);
}
}

int main() {
    using nx2::StopReason;
    constexpr std::array<std::uint32_t, 5> program{
        0xD28000E0U, // MOVZ X0, #7
        0xD2800121U, // MOVZ X1, #9
        svc(0x1234U),
        0x91000400U, // ADD X0, X0, #1 — reached only after explicit reply
        0xD4200000U, // BRK, not fetched before service authorization
    };
    nx2::CpuState initial;
    initial.x[2] = 0xCAFEBABE00000001ULL;
    initial.x[7] = 0xAABBCCDDULL;
    std::array<std::byte, 16> bytes{};
    std::array<nx2::GuestMemoryRegion, 1> regions{{
        nx2::GuestMemoryRegion{0x2000U, bytes, true, true}
    }};
    nx2::GuestMemoryView memory(regions);
    const auto result = nx2::run_owned_program(program, 10, initial, &memory);
    require(result.stop == StopReason::service_request &&
            result.service_immediate == 0x1234U && result.stopped_word == svc(0x1234U),
            "incorrect typed service boundary or immediate");
    require(result.retired == 2 && result.state.pc == 8 &&
            result.state.x[0] == 7 && result.state.x[1] == 9 &&
            result.state.x[2] == initial.x[2] && result.state.x[7] == initial.x[7],
            "SVC retired or caller state changed");
    require(memory.load64(0x2000U) == std::optional<std::uint64_t>{0},
            "SVC performed an unauthorized memory effect");

    const auto zero = nx2::run_owned_program(
        std::array<std::uint32_t, 1>{svc(0)}, 3, initial);
    require(zero.stop == StopReason::service_request &&
            zero.service_immediate == 0 && zero.retired == 0 &&
            zero.state.pc == 0 && zero.state.x == initial.x,
            "SVC #0 corrupted caller state");
    const auto max = nx2::run_owned_program(
        std::array<std::uint32_t, 1>{svc(0xFFFFU)}, 3, initial);
    require(max.stop == StopReason::service_request &&
            max.service_immediate == 0xFFFFU && max.retired == 0,
            "SVC immediate width truncated");
    const auto budget = nx2::run_owned_program(program, 2, initial);
    require(budget.stop == StopReason::instruction_budget &&
            budget.retired == 2 && budget.state.pc == 8,
            "budget incorrectly executed next service boundary");
    const auto first_instruction = nx2::run_owned_program(program, 0, initial);
    require(first_instruction.stop == StopReason::instruction_budget &&
            first_instruction.retired == 0 && first_instruction.state.pc == 0,
            "zero budget admitted a service path");
    const auto hvc = nx2::run_owned_program(
        std::array<std::uint32_t, 1>{0xD4000002U}, 2, initial);
    require(hvc.stop == StopReason::unsupported_instruction && hvc.retired == 0 &&
            hvc.state.x == initial.x,
            "unsupported hypervisor call was treated as SVC");
    const auto smc = nx2::run_owned_program(
        std::array<std::uint32_t, 1>{0xD4000003U}, 2, initial);
    require(smc.stop == StopReason::unsupported_instruction && smc.retired == 0,
            "unsupported secure monitor call was treated as SVC");
    const auto reply = nx2::OwnedFixtureServiceReply{
        .expected_immediate = 0x1234U, .x0_return_value = 99U};
    auto resumed = nx2::apply_owned_fixture_service_reply(program, result, reply);
    require(resumed.has_value() && resumed->pc == 12 &&
            resumed->x[0] == 99 && resumed->x[1] == 9 &&
            resumed->x[2] == initial.x[2],
            "explicit source-owned service reply failed");
    const auto afterward = nx2::run_owned_program(program, 8, *resumed, &memory);
    require(afterward.stop == StopReason::breakpoint && afterward.retired == 1 &&
            afterward.state.pc == 16 && afterward.state.x[0] == 100 &&
            afterward.state.x[1] == 9 &&
            memory.load64(0x2000U) == std::optional<std::uint64_t>{0},
            "source-owned mock service continuation failed");

    const auto wrong_imm = nx2::OwnedFixtureServiceReply{
        .expected_immediate = 0x1235U, .x0_return_value = 99U};
    require(!nx2::apply_owned_fixture_service_reply(program, result, wrong_imm),
            "mismatched service ID admitted");
    auto altered = program;
    altered[2] ^= 0x20U;
    require(!nx2::apply_owned_fixture_service_reply(altered, result, reply),
            "changed source instruction admitted");
    auto forged = result;
    forged.service_immediate = 0;
    require(!nx2::apply_owned_fixture_service_reply(program, forged, reply),
            "forged immediate accepted");
    forged = result;
    forged.state.pc = 4;
    require(!nx2::apply_owned_fixture_service_reply(program, forged, reply),
            "wrong stop PC accepted");
    forged = result;
    forged.stop = StopReason::breakpoint;
    require(!nx2::apply_owned_fixture_service_reply(program, forged, reply),
            "non-service stop was resumed");
    require(!nx2::apply_owned_fixture_service_reply(
                std::span<const std::uint32_t>{program.data(), 3}, result, reply),
            "service without a continuation instruction was accepted");
    std::cout << "OWNED_AARCH64_SERVICE_BOUNDARY_PASS:14_cases\n";
}
