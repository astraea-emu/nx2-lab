#include <nx2/cpu.hpp>

#include <limits>

namespace nx2 {
namespace {
constexpr std::size_t kMaxWords = 4096;
constexpr std::size_t kMaxBudget = 4096;
constexpr std::uint32_t kNop = 0xD503201FU;
constexpr std::uint32_t kMovz64Pattern = 0xD2800000U;
constexpr std::uint32_t kAdd64Pattern = 0x91000000U;
constexpr std::uint32_t kBrkPattern = 0xD4200000U;
constexpr std::uint32_t kSvcPattern = 0xD4000001U;
constexpr std::uint32_t kStr64Pattern = 0xF9000000U;
constexpr std::uint32_t kLdr64Pattern = 0xF9400000U;
} // namespace

RunResult run_owned_program(
    std::span<const std::uint32_t> words, std::size_t instruction_budget,
    CpuState initial, GuestMemoryView* memory) noexcept {
    RunResult out{.stop = StopReason::invalid_program, .state = initial,
                  .retired = 0, .stopped_word = 0};
    if (words.empty() || words.size() > kMaxWords ||
        instruction_budget > kMaxBudget || out.state.pc % 4U != 0U) {
        return out;
    }
    for (;;) {
        if (out.retired == instruction_budget) {
            out.stop = StopReason::instruction_budget;
            return out;
        }
        if (out.state.pc >= words.size() * 4U) {
            out.stop = StopReason::instruction_fetch_fault;
            return out;
        }
        const auto word = words[static_cast<std::size_t>(out.state.pc / 4U)];
        out.stopped_word = word;
        if ((word & 0xFFE0001FU) == kBrkPattern) {
            out.stop = StopReason::breakpoint;
            return out;
        }
        if ((word & 0xFFE0001FU) == kSvcPattern) {
            // A generic AArch64 SVC instruction is a *boundary*, not a
            // host call or an inferred Nintendo/Horizon service. Do not
            // retire it, change any caller register, or resume implicitly.
            out.stop = StopReason::service_request;
            out.service_immediate = static_cast<std::uint16_t>(
                (word >> 5U) & 0xFFFFU);
            return out;
        }
        if (word == kNop) {
            // NOP has no register or flag effects.
        } else if ((word & 0xFF800000U) == kMovz64Pattern) {
            const unsigned rd = word & 0x1FU;
            const unsigned hw = (word >> 21U) & 0x3U;
            const auto imm = (word >> 5U) & 0xFFFFU;
            if (rd < 31U) {
                out.state.x[rd] = static_cast<std::uint64_t>(imm) << (hw * 16U);
            } // XZR discards writes.
        } else if ((word & 0xFF000000U) == kAdd64Pattern) {
            const unsigned rd = word & 0x1FU;
            const unsigned rn = (word >> 5U) & 0x1FU;
            const unsigned shift = (word >> 22U) & 0x3U;
            // In ADD (immediate), register 31 aliases SP, not zero. We do
            // not model SP yet, so refuse instead of making a false claim.
            if (rd == 31U || rn == 31U || shift > 1U) {
                out.stop = StopReason::unsupported_instruction;
                return out;
            }
            const std::uint64_t operand =
                static_cast<std::uint64_t>((word >> 10U) & 0xFFFU)
                << (shift == 1U ? 12U : 0U);
            out.state.x[rd] = out.state.x[rn] + operand;
        } else if ((word & 0xFFC00000U) == kStr64Pattern ||
                   (word & 0xFFC00000U) == kLdr64Pattern) {
            // Generic AArch64 64-bit unsigned-offset LDR/STR. Offset is
            // imm12 scaled by 8. Rn==31 encodes SP, currently unsupported;
            // Rt==31 encodes XZR for this instruction class.
            const bool load = (word & 0xFFC00000U) == kLdr64Pattern;
            const auto rt = word & 0x1FU;
            const auto rn = (word >> 5U) & 0x1FU;
            const auto byte_offset = static_cast<std::uint64_t>(
                (word >> 10U) & 0xFFFU) * 8U;
            if (rn == 31U) {
                out.stop = StopReason::unsupported_instruction;
                return out;
            }
            if (memory == nullptr ||
                out.state.x[rn] >
                    std::numeric_limits<std::uint64_t>::max() - byte_offset) {
                out.stop = StopReason::data_access_fault;
                return out;
            }
            const auto address = out.state.x[rn] + byte_offset;
            if (load) {
                const auto value = memory->load64(address);
                if (!value.has_value()) {
                    out.stop = StopReason::data_access_fault;
                    return out;
                }
                if (rt < 31U) {
                    out.state.x[rt] = *value;
                }
            } else if (!memory->store64(address, rt == 31U ? 0U : out.state.x[rt])) {
                out.stop = StopReason::data_access_fault;
                return out;
            }
        } else {
            out.stop = StopReason::unsupported_instruction;
            return out;
        }
        out.state.pc += 4U;
        ++out.retired;
    }
}

const char* stop_reason_name(StopReason reason) noexcept {
    switch (reason) {
    case StopReason::breakpoint: return "breakpoint_before_retirement";
    case StopReason::service_request: return "service_request_before_retirement";
    case StopReason::unsupported_instruction: return "unsupported_instruction";
    case StopReason::instruction_budget: return "instruction_budget";
    case StopReason::instruction_fetch_fault: return "instruction_fetch_fault";
    case StopReason::data_access_fault: return "data_access_fault";
    case StopReason::invalid_program: return "invalid_program";
    }
    return "unknown";
}
} // namespace nx2
