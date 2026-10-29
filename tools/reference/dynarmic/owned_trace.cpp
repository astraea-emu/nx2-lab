// Independent, source-owned AArch64 backend comparison; not Switch 2 execution.
// Dynarmic is consumed from a frozen external checkout, never vendored here.
#include <dynarmic/interface/A64/a64.h>
#include <nx2/cpu.hpp>
#include <nx2/memory.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>

namespace {
constexpr std::uint32_t svc(std::uint16_t imm) {
    return 0xD4000001U | (static_cast<std::uint32_t>(imm) << 5U);
}
void require(bool ok, const char* what) {
    if (!ok) throw std::runtime_error(what);
}

class OwnedCallbacks final : public Dynarmic::A64::UserCallbacks {
public:
    OwnedCallbacks(std::span<const std::uint32_t> words, bool writable)
        : code(words), regions{{nx2::GuestMemoryRegion{0x2000U, bytes, true, writable}}},
          guest_memory(regions) {}

    std::span<const std::uint32_t> code;
    std::array<std::byte, 32> bytes{};
    std::array<nx2::GuestMemoryRegion, 1> regions;
    nx2::GuestMemoryView guest_memory;
    bool unqualified_effect = false;
    unsigned memory_reads = 0;
    unsigned memory_writes = 0;

    std::optional<std::uint32_t> MemoryReadCode(Dynarmic::A64::VAddr pc) override {
        if ((pc & 3U) != 0 || pc / 4 >= code.size()) return std::nullopt;
        return code[static_cast<std::size_t>(pc / 4)];
    }
    std::uint8_t MemoryRead8(std::uint64_t) override { unqualified_effect = true; return 0; }
    std::uint16_t MemoryRead16(std::uint64_t) override { unqualified_effect = true; return 0; }
    std::uint32_t MemoryRead32(std::uint64_t) override { unqualified_effect = true; return 0; }
    std::uint64_t MemoryRead64(std::uint64_t addr) override {
        const auto value = guest_memory.load64(addr);
        if (!value) { unqualified_effect = true; return 0; }
        ++memory_reads;
        return *value;
    }
    Dynarmic::A64::Vector MemoryRead128(std::uint64_t) override {
        unqualified_effect = true; return {};
    }
    void MemoryWrite8(std::uint64_t, std::uint8_t) override { unqualified_effect = true; }
    void MemoryWrite16(std::uint64_t, std::uint16_t) override { unqualified_effect = true; }
    void MemoryWrite32(std::uint64_t, std::uint32_t) override { unqualified_effect = true; }
    void MemoryWrite64(std::uint64_t addr, std::uint64_t value) override {
        if (!guest_memory.store64(addr, value)) { unqualified_effect = true; return; }
        ++memory_writes;
    }
    void MemoryWrite128(std::uint64_t, Dynarmic::A64::Vector) override {
        unqualified_effect = true;
    }
    void InterpreterFallback(std::uint64_t, std::size_t) override { unqualified_effect = true; }
    void CallSVC(std::uint32_t) override { unqualified_effect = true; }
    void ExceptionRaised(std::uint64_t, Dynarmic::A64::Exception) override {
        unqualified_effect = true;
    }
    void AddTicks(std::uint64_t) override {}
    std::uint64_t GetTicksRemaining() override { return 1; }
    std::uint64_t GetCNTPCT() override { return 0; }
};

template <std::size_t N>
void compare_owned_trace(const std::array<std::uint32_t, N>& code,
                         std::size_t retired_before_svc, bool writable = true) {
    require(retired_before_svc < code.size() &&
            code[retired_before_svc] == svc(0x1234U), "unreviewed program/stop");
    OwnedCallbacks candidate(code, writable);
    Dynarmic::A64::UserConfig config{};
    config.callbacks = &candidate;
    config.fastmem_pointer = std::nullopt;
    config.page_table = nullptr;
    config.silently_mirror_fastmem = false;
    config.silently_mirror_page_table = false;
    config.unsafe_optimizations = false;
    config.check_halt_on_memory_access = true;
    Dynarmic::A64::Jit cpu(config);
    cpu.SetPC(0);
    for (std::size_t step = 1; step <= retired_before_svc; ++step) {
        // Explicit Step(): no unbounded batch and no unexpected service dispatch.
        cpu.Step();
        require(!candidate.unqualified_effect, "unqualified backend host/guest effect");
        std::array<std::byte, 32> reference_bytes{};
        std::array<nx2::GuestMemoryRegion, 1> regions{{
            nx2::GuestMemoryRegion{0x2000U, reference_bytes, true, writable}}};
        nx2::GuestMemoryView reference_mem(regions);
        const auto reference = nx2::run_owned_program(code, step, {}, &reference_mem);
        require(reference.stop == nx2::StopReason::instruction_budget &&
                reference.retired == step, "owned oracle failed to retire prefix");
        require(cpu.GetPC() == reference.state.pc &&
                cpu.GetRegisters() == reference.state.x, "backend CPU state mismatch");
        require(candidate.bytes == reference_bytes, "backend memory readback mismatch");
    }
    // Do not call Step() on SVC. Backend callback alone does not prove the
    // exact pre-retirement or permission semantics required by our contract.
    std::array<std::byte, 32> final_bytes{};
    std::array<nx2::GuestMemoryRegion, 1> final_regions{{
        nx2::GuestMemoryRegion{0x2000U, final_bytes, true, writable}}};
    nx2::GuestMemoryView final_memory(final_regions);
    const auto final = nx2::run_owned_program(
        code, retired_before_svc + 1, {}, &final_memory);
    require(final.stop == nx2::StopReason::service_request &&
            final.service_immediate == 0x1234U &&
            cpu.GetPC() == final.state.pc &&
            cpu.GetRegisters() == final.state.x,
            "typed pre-retirement service stop diverged");
    require(candidate.memory_reads <= retired_before_svc &&
            candidate.memory_writes <= retired_before_svc,
            "unexpected number of data effects");
}

void denied_write_negative() {
    constexpr std::array<std::uint32_t, 4> code{
        0xD2840001U, 0xD2800540U, 0xF9000020U, svc(0x1234U)};
    OwnedCallbacks candidate(code, false);
    Dynarmic::A64::UserConfig config{};
    config.callbacks = &candidate;
    config.fastmem_pointer = std::nullopt;
    config.page_table = nullptr;
    config.check_halt_on_memory_access = true;
    Dynarmic::A64::Jit cpu(config);
    cpu.SetPC(0);
    cpu.Step();
    cpu.Step();
    require(!candidate.unqualified_effect, "pre-denial program failed");
    cpu.Step();
    require(candidate.unqualified_effect && candidate.memory_writes == 0,
            "read-only store not rejected by host-side guest memory facade");
    require(candidate.bytes == std::array<std::byte, 32>{},
            "read-only store modified controller-owned canary");
    // The engine may have advanced PC/state following the denied callback.
    // No mutated private state may be published. This is a HOLD, not a proven
    // precise guest memory fault or a production sandbox.
}
} // namespace

int main() {
    try {
        constexpr std::array<std::uint32_t, 5> arithmetic{
            0xD2800540U, 0x91000400U, 0xD503201FU,
            svc(0x1234U), 0xD4200000U};
        constexpr std::array<std::uint32_t, 6> memory{
            0xD2840001U, 0xD2800540U, 0xF9000020U,
            0xF9400022U, svc(0x1234U), 0xD4200000U};
        compare_owned_trace(arithmetic, 3);
        compare_owned_trace(memory, 4);
        denied_write_negative();
        auto mutated = arithmetic;
        mutated[3] ^= 0x20U;
        bool refused = false;
        try { compare_owned_trace(mutated, 3); }
        catch (const std::runtime_error&) { refused = true; }
        require(refused, "changed source-owned SVC identity admitted");
        std::cout << "NX2_DYNARMIC_OWNED_TRACE_PASS\n"
                  << "original_instruction_prefixes=3_and_4\n"
                  << "source_owned_guest_memory_readback=checked\n"
                  << "svc_execution=not_admitted\n"
                  << "read_only_denial=private_effects_rejected_not_precise_fault\n"
                  << "switch2_instructions_executed=0\n"
                  << "external_backend=research_only\n";
    } catch (const std::exception& e) {
        std::cerr << "NX2_DYNARMIC_OWNED_TRACE_REFUSED: " << e.what() << '\n';
        return 1;
    }
}
