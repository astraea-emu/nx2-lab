#include <nx2/owned_service.hpp>

#include <limits>

namespace nx2 {
std::optional<CpuState> apply_owned_fixture_service_reply(
    std::span<const std::uint32_t> original_program,
    const RunResult& stop,
    const OwnedFixtureServiceReply& reply) noexcept {
    constexpr std::uint32_t kSvcPattern = 0xD4000001U;
    if (stop.stop != StopReason::service_request ||
        stop.state.pc % 4U != 0U ||
        stop.state.pc > std::numeric_limits<std::uint64_t>::max() - 4U ||
        stop.state.pc / 4U >= original_program.size()) {
        return std::nullopt;
    }
    const auto index = static_cast<std::size_t>(stop.state.pc / 4U);
    const auto word = original_program[index];
    if ((word & 0xFFE0001FU) != kSvcPattern ||
        word != stop.stopped_word ||
        static_cast<std::uint16_t>((word >> 5U) & 0xFFFFU) !=
            stop.service_immediate ||
        stop.service_immediate != reply.expected_immediate ||
        index + 1U >= original_program.size()) {
        return std::nullopt;
    }
    auto continued = stop.state;
    continued.x[0] = reply.x0_return_value;
    continued.pc += 4U;
    return continued;
}
} // namespace nx2
