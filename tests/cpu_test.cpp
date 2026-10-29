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
    // A64 LDR (literal) Xt: signed imm19 * 4 from the current PC.
    constexpr std::array<std::uint32_t, 4> forward_literal{
        0x58000040U, 0xD4200000U, 0x11223344U, 0x55667788U};
    const auto forward = nx2::run_owned_program(forward_literal, 6);
    require(forward.stop == StopReason::breakpoint && forward.retired == 1 &&
            forward.state.pc == 4 &&
            forward.state.x[0] == 0x5566778811223344ULL,
            "LDR literal positive offset decoded incorrectly");
    constexpr std::array<std::uint32_t, 4> backward_literal{
        0x11223344U, 0x55667788U, 0x58ffffc1U, 0xD4200000U};
    nx2::CpuState start_backward;
    start_backward.pc = 8;
    const auto backward = nx2::run_owned_program(
        backward_literal, 4, start_backward);
    require(backward.stop == StopReason::breakpoint &&
            backward.retired == 1 && backward.state.pc == 12 &&
            backward.state.x[1] == 0x5566778811223344ULL,
            "LDR literal negative offset decoded incorrectly");
    constexpr std::array<std::uint32_t, 4> discard_literal{
        0x5800005fU, 0xD4200000U, 0x11223344U, 0x55667788U};
    const auto discarded = nx2::run_owned_program(discard_literal, 2);
    require(discarded.stop == StopReason::breakpoint &&
            discarded.retired == 1 && discarded.state.pc == 4 &&
            discarded.state.x == nx2::CpuState{}.x,
            "LDR literal XZR must discard register write");
    const auto too_far = nx2::run_owned_program(
        std::array<std::uint32_t, 2>{0x58000040U, 0xD4200000U}, 2);
    require(too_far.stop == StopReason::data_access_fault &&
            too_far.retired == 0 && too_far.state.pc == 0,
            "LDR literal unmapped positive access retired");
    const auto too_low = nx2::run_owned_program(
        std::array<std::uint32_t, 2>{0x58ffffc0U, 0xD4200000U}, 2);
    require(too_low.stop == StopReason::data_access_fault &&
            too_low.retired == 0 && too_low.state.pc == 0,
            "LDR literal negative guest address wrap accepted");
    const auto partial_literal = nx2::run_owned_program(
        std::array<std::uint32_t, 3>{0x58000040U, 0xD4200000U,
                                     0x11223344U}, 2);
    require(partial_literal.stop == StopReason::data_access_fault &&
            partial_literal.retired == 0 && partial_literal.state.pc == 0,
            "LDR literal partial 64-bit read accepted");
    const auto zero_budget_literal = nx2::run_owned_program(forward_literal, 0);
    require(zero_budget_literal.stop == StopReason::instruction_budget &&
            zero_budget_literal.retired == 0, "LDR literal exceeded zero budget");
    const auto wrong_width_literal = nx2::run_owned_program(
        std::array<std::uint32_t, 2>{0x18000040U, 0xD4200000U}, 2);
    require(wrong_width_literal.stop == StopReason::unsupported_instruction &&
            wrong_width_literal.retired == 0,
            "unsupported 32-bit literal load silently admitted");
    std::cout << "SOURCE_OWNED_AARCH64_CONTRACT_PASS:11_cases\n";
}
