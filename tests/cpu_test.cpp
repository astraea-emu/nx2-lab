#include <nx2/cpu.hpp>
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

void require(bool ok, const char* what) {
    if (!ok) throw std::runtime_error(what);
}
int main() {
    using nx2::StopReason;
    constexpr std::array<std::uint32_t, 3> words = {
        0xD2800540U, 0x91000400U, 0xD4200000U};
    const auto good = nx2::run_owned_program(words, 12);
    require(good.stop == StopReason::breakpoint, "BRK not typed");
    require(good.state.x[0] == 43 && good.state.pc == 8, "CPU state mismatch");
    require(good.retired == 2, "BRK illegally retired");
    const auto short_budget = nx2::run_owned_program(words, 1);
    require(short_budget.stop == StopReason::instruction_budget &&
            short_budget.retired == 1 && short_budget.state.x[0] == 42 &&
            short_budget.state.pc == 4, "budget changed state");
    const auto no_budget = nx2::run_owned_program(words, 0);
    require(no_budget.stop == StopReason::instruction_budget &&
            no_budget.retired == 0 && no_budget.state.pc == 0, "zero budget admitted");
    const auto invalid = nx2::run_owned_program(
        std::array<std::uint32_t, 1>{0xFFFFFFFFU}, 1);
    require(invalid.stop == StopReason::unsupported_instruction &&
            invalid.retired == 0 && invalid.state.pc == 0, "unknown word retired");
    const auto sp_add = nx2::run_owned_program(
        std::array<std::uint32_t, 1>{0x910007E0U}, 1);
    require(sp_add.stop == StopReason::unsupported_instruction &&
            sp_add.retired == 0, "unmodeled SP admitted");
    const auto over_budget = nx2::run_owned_program(words, 4097);
    require(over_budget.stop == StopReason::invalid_program, "huge budget admitted");
    const auto empty = nx2::run_owned_program(std::span<const std::uint32_t>{}, 1);
    require(empty.stop == StopReason::invalid_program, "empty program admitted");
    const auto too_large = nx2::run_owned_program(
        std::vector<std::uint32_t>(4097, 0xD503201FU), 1);
    require(too_large.stop == StopReason::invalid_program, "oversized program admitted");
    nx2::CpuState misaligned; misaligned.pc = 1;
    const auto alignment = nx2::run_owned_program(words, 1, misaligned);
    require(alignment.stop == StopReason::invalid_program, "misaligned PC admitted");
    const auto at_end = nx2::run_owned_program(
        std::array<std::uint32_t, 1>{0xD503201FU}, 2);
    require(at_end.stop == StopReason::instruction_fetch_fault &&
            at_end.retired == 1 && at_end.state.pc == 4, "OOB fetch admitted");
    constexpr std::array<std::uint32_t, 2> mov_shift = {
        0xD2A00020U, 0xD4200000U}; // MOVZ X0,#1,LSL #16
    const auto shift = nx2::run_owned_program(mov_shift, 4);
    require(shift.stop == StopReason::breakpoint &&
            shift.state.x[0] == 0x10000, "MOVZ shift mismatch");
    std::cout << "SOURCE_OWNED_AARCH64_CONTRACT_PASS:11_cases\n";
}
