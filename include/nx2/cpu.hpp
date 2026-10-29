#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

#include <nx2/memory.hpp>

namespace nx2 {

enum class StopReason {
    breakpoint,
    service_request,
    unsupported_instruction,
    instruction_budget,
    instruction_fetch_fault,
    data_access_fault,
    invalid_program,
};

struct CpuState {
    std::array<std::uint64_t, 31> x{};
    std::uint64_t pc = 0;
};

struct RunResult {
    StopReason stop = StopReason::invalid_program;
    CpuState state{};
    std::size_t retired = 0;
    std::uint32_t stopped_word = 0;
    // Only populated for a stopped, unretired generic AArch64 SVC.
    std::uint16_t service_immediate = 0;
};

// Host-only generic AArch64 instruction semantics, NOT a Switch 2 process.
// Only source-authored 32-bit words in a bounded read-only span are admitted.
// Stops are typed; an unsupported instruction is never considered retired.
[[nodiscard]] RunResult run_owned_program(
    std::span<const std::uint32_t> words, std::size_t instruction_budget,
    CpuState initial = {}, GuestMemoryView* memory = nullptr) noexcept;

[[nodiscard]] const char* stop_reason_name(StopReason reason) noexcept;

} // namespace nx2
