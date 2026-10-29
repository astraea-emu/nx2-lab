#pragma once

#include <cstdint>
#include <optional>
#include <span>

#include <nx2/cpu.hpp>

namespace nx2 {

// A deliberately independent, test-owned service fixture reply. It is NOT
// a Nintendo, Horizon, or generic AArch64 kernel-service implementation.
struct OwnedFixtureServiceReply {
    std::uint16_t expected_immediate = 0;
    std::uint64_t x0_return_value = 0;
};

// Only continue a source-owned, previously halted SVC instruction after an
// explicitly supplied fixture response. Re-check the stopped word and
// requested immediate against the original immutable instruction span.
// Refuse without mutation when state/input is inconsistent. On success only
// X0 and PC advance; no host syscall or guest-memory write is performed.
[[nodiscard]] std::optional<CpuState> apply_owned_fixture_service_reply(
    std::span<const std::uint32_t> original_program,
    const RunResult& stop,
    const OwnedFixtureServiceReply& reply) noexcept;

} // namespace nx2
