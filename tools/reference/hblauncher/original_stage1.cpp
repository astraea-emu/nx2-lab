// Research-only AArch64 execution of a pinned, unchanged external HBX SDK app.
// HBX is HBLauncher's custom ABI; this does not emulate Nintendo Horizon.
// No host syscall, native guest jump, device, firmware or game input permitted.
#include <dynarmic/interface/A64/a64.h>

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using U8 = std::uint8_t;
using U64 = std::uint64_t;
constexpr U64 kContextBase = 0x30000000ULL;
constexpr U64 kStackBase = 0x50000000ULL;
constexpr U64 kCallerStackBase = 0x51000000ULL;
constexpr U64 kReturnSentinel = 0x60000000ULL;
constexpr std::size_t kContextBytes = 4096;
constexpr std::size_t kStackBytes = 64 * 1024;
constexpr std::size_t kMaxFile = 2 * 1024 * 1024;
constexpr U64 kHbxMagic = 0x33425848U;
constexpr U64 kHbxVersion = 3;
constexpr U64 kHbxContextSize = 696;

void require(bool value, const char* why) {
    if (!value) throw std::runtime_error(why);
}
std::vector<U8> load_file(const char* path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    require(in.good(), "file_open");
    const auto length = in.tellg();
    require(length >= 0 && length <= static_cast<std::streamoff>(kMaxFile),
            "file_size");
    std::vector<U8> result(static_cast<std::size_t>(length));
    in.seekg(0);
    if (!result.empty()) {
        require(static_cast<bool>(in.read(
            reinterpret_cast<char*>(result.data()), length)), "file_read");
    }
    return result;
}
U64 parse_number(const char* input) {
    const auto s = std::string(input);
    require(!s.empty() && s[0] != '-', "invalid_integer");
    std::size_t end = 0;
    const auto v = std::stoull(s, &end, 0);
    require(end == s.size(), "invalid_integer_tail");
    return v;
}
void put_le(std::vector<U8>& bytes, std::size_t off, U64 value, unsigned size) {
    require(off <= bytes.size() && size <= bytes.size() - off,
            "guest_context_bounds");
    for (unsigned i = 0; i < size; ++i)
        bytes[off + i] = static_cast<U8>(value >> (i * 8U));
}

struct Mapping {
    U64 guest_base;
    std::vector<U8> bytes;
    bool readable;
    bool writable;
    bool executable;
};

// Exact, bounded guest *write callbacks*, not a claim that every JIT
// microarchitectural effect is known. Used to compare repeated source runs.
struct WriteEffect {
    U64 guest_address = 0;
    std::array<U8, 16> bytes{};
    unsigned width = 0;
    bool operator==(const WriteEffect&) const = default;
};

class OwnedMemoryCallbacks final : public Dynarmic::A64::UserCallbacks {
public:
    std::vector<Mapping> regions;
    bool denied = false;
    unsigned svc_count = 0;
    unsigned other_exceptions = 0;
    unsigned successful_writes = 0;
    std::vector<WriteEffect> effects;
    static constexpr std::size_t kMaxEffects = 4096;

    void record_write(U64 address, const U8* bytes, unsigned size) {
        if (effects.size() >= kMaxEffects || size == 0 || size > 16) {
            denied = true;
            return;
        }
        WriteEffect effect;
        effect.guest_address = address;
        effect.width = size;
        std::copy_n(bytes, size, effect.bytes.begin());
        effects.push_back(effect);
        ++successful_writes;
    }

    OwnedMemoryCallbacks(std::vector<U8> code, std::vector<U8> data,
                         U64 code_base, U64 data_base, std::size_t data_extent,
                         const std::string& scenario)
        : regions{} {
        require(!code.empty() && code.size() <= kMaxFile &&
                code.size() % 4 == 0, "code_image_size");
        require(data_extent >= data.size() && data_extent <= kMaxFile,
                "data_image_size");
        require(code_base != data_base && code_base % 4096 == 0 &&
                data_base % 4096 == 0, "code_data_addresses");
        // The source compiler's original code and data bytes are immutable.
        regions.push_back({code_base, std::move(code), true, false, true});
        regions.push_back({data_base, std::vector<U8>(data_extent, 0), true,
                           true, false});
        std::copy(data.begin(), data.end(), regions.back().bytes.begin());
        std::vector<U8> ctx(kContextBytes, 0);
        put_le(ctx, 0, scenario == "bad_magic" ? 0x12345678U : kHbxMagic, 4);
        put_le(ctx, 4, scenario == "bad_version" ? 4U : kHbxVersion, 4);
        put_le(ctx, 8, scenario == "bad_size" ? 512U : kHbxContextSize, 4);
        put_le(ctx, 0x70, kStackBase, 8);
        put_le(ctx, 0x78, kStackBytes, 8);
        put_le(ctx, 0x208 + 8, 1U, 8); // HBX hello-cpu stage 1, source-authored.
        regions.push_back({kContextBase, std::move(ctx), true, false, false});
        regions.push_back({kStackBase, std::vector<U8>(kStackBytes, 0), true,
                           scenario != "no_stack_write", false});
        // HBX _start saves its own caller frame before switching to the
        // context-supplied app stack. Those two stacks MUST NOT alias.
        regions.push_back({kCallerStackBase,
                           std::vector<U8>(kStackBytes, 0), true, true, false});
    }

    // Refuse partial, overlapping, out-of-range, or denied accesses.
    U8* checked(U64 address, std::size_t bytes, bool write, bool exec) {
        if (bytes == 0 || address > std::numeric_limits<U64>::max() - bytes) {
            denied = true;
            return nullptr;
        }
        Mapping* found = nullptr;
        for (auto& r : regions) {
            if (r.guest_base > std::numeric_limits<U64>::max() -
                                   static_cast<U64>(r.bytes.size())) {
                denied = true; return nullptr;
            }
            const U64 end = r.guest_base + r.bytes.size();
            const U64 access_end = address + bytes;
            if (address >= end || access_end <= r.guest_base)
                continue;
            if (found || address < r.guest_base || access_end > end) {
                denied = true; return nullptr;
            }
            found = &r;
        }
        if (!found || (exec ? !found->executable :
                        write ? !found->writable : !found->readable)) {
            denied = true;
            return nullptr;
        }
        return found->bytes.data() + (address - found->guest_base);
    }
    std::optional<std::uint32_t> MemoryReadCode(U64 addr) override {
        if (addr % 4 != 0) { denied = true; return std::nullopt; }
        const auto* ptr = checked(addr, 4, false, true);
        if (!ptr) return std::nullopt;
        std::uint32_t value = 0;
        for (unsigned i = 0; i < 4; ++i) value |=
            std::uint32_t(ptr[i]) << (i * 8U);
        return value;
    }
    U64 read(U64 addr, unsigned size) {
        const auto* ptr = checked(addr, size, false, false);
        if (!ptr) return 0;
        U64 value = 0;
        for (unsigned i = 0; i < size; ++i)
            value |= U64(ptr[i]) << (i * 8U);
        return value;
    }
    void write(U64 addr, U64 value, unsigned size) {
        auto* ptr = checked(addr, size, true, false);
        if (!ptr) return;
        for (unsigned i = 0; i < size; ++i)
            ptr[i] = static_cast<U8>(value >> (i * 8U));
        record_write(addr, ptr, size);
    }
    std::uint8_t MemoryRead8(U64 a) override { return static_cast<U8>(read(a, 1)); }
    std::uint16_t MemoryRead16(U64 a) override { return static_cast<std::uint16_t>(read(a, 2)); }
    std::uint32_t MemoryRead32(U64 a) override { return static_cast<std::uint32_t>(read(a, 4)); }
    std::uint64_t MemoryRead64(U64 a) override { return read(a, 8); }
    Dynarmic::A64::Vector MemoryRead128(U64 a) override {
        const auto* p = checked(a, 16, false, false);
        if (!p) return {};
        U64 lo = 0, hi = 0;
        for (unsigned i = 0; i < 8; ++i) {
            lo |= U64(p[i]) << (i * 8);
            hi |= U64(p[i + 8]) << (i * 8);
        }
        return {lo, hi};
    }
    void MemoryWrite8(U64 a, std::uint8_t v) override { write(a, v, 1); }
    void MemoryWrite16(U64 a, std::uint16_t v) override { write(a, v, 2); }
    void MemoryWrite32(U64 a, std::uint32_t v) override { write(a, v, 4); }
    void MemoryWrite64(U64 a, std::uint64_t v) override { write(a, v, 8); }
    void MemoryWrite128(U64 a, Dynarmic::A64::Vector v) override {
        auto* p = checked(a, 16, true, false);
        if (!p) return;
        for (unsigned i = 0; i < 8; ++i) {
            p[i] = static_cast<U8>(v[0] >> (i * 8));
            p[i + 8] = static_cast<U8>(v[1] >> (i * 8));
        }
        record_write(a, p, 16);
    }
    void InterpreterFallback(U64, std::size_t) override { denied = true; }
    void CallSVC(std::uint32_t) override { ++svc_count; denied = true; }
    void ExceptionRaised(U64, Dynarmic::A64::Exception) override {
        ++other_exceptions; denied = true;
    }
    void AddTicks(U64) override {}
    U64 GetTicksRemaining() override { return 1; }
    U64 GetCNTPCT() override { return 0; }
};

struct SessionResult {
    U64 result = 0;
    U64 retired = 0;
    U64 end_pc = 0;
    std::vector<WriteEffect> guest_write_effects{};
    std::size_t app_stack_writes = 0;
    std::size_t caller_stack_writes = 0;
    bool operator==(const SessionResult&) const = default;
};

SessionResult execute(const std::vector<U8>& code,
                      const std::vector<U8>& data, U64 code_base,
                      U64 data_base, U64 entry, std::size_t data_extent,
                      std::string scenario, U64 budget) {
    if (scenario == "bad_entry") entry = code_base + code.size();
    OwnedMemoryCallbacks mem(code, data, code_base, data_base, data_extent,
                             scenario);
    // Keep controller-owned preimages across guest execution. The original
    // code and source-defined context must remain byte-identical, even if
    // an accidental callback would try writing outside its permissions.
    const auto original_code = mem.regions[0].bytes;
    const auto original_data = mem.regions[1].bytes;
    const auto original_context = mem.regions[2].bytes;
    const auto original_app_stack = mem.regions[3].bytes;
    const auto original_caller_stack = mem.regions[4].bytes;
    Dynarmic::A64::UserConfig conf{};
    conf.callbacks = &mem;
    conf.fastmem_pointer = std::nullopt;
    conf.page_table = nullptr;
    conf.silently_mirror_fastmem = false;
    conf.silently_mirror_page_table = false;
    conf.unsafe_optimizations = false;
    conf.check_halt_on_memory_access = true;
    conf.code_cache_size = 8 * 1024 * 1024; // bounded research-only allocation
    Dynarmic::A64::Jit cpu(conf);
    cpu.SetPC(entry);
    // In the original CRT0 route the incoming host-caller stack is
    // independent of ctx->stack_base. Direct app-function calls retain
    // the existing test stack to preserve earlier regression semantics.
    const U64 caller_sp = (entry == code_base)
        ? kCallerStackBase + kStackBytes : kStackBase + kStackBytes;
    cpu.SetSP(caller_sp);
    cpu.SetRegister(0, scenario == "bad_pointer" ?
        0x70000000ULL : kContextBase);
    cpu.SetRegister(30, kReturnSentinel);
    require(budget <= 4096, "budget_excess");
    for (U64 step = 0; step < budget; ++step) {
        if (cpu.GetPC() == kReturnSentinel) {
            require(!mem.denied && mem.svc_count == 0 &&
                    mem.other_exceptions == 0 &&
                    cpu.GetSP() == caller_sp &&
                    cpu.GetRegister(29) == 0U &&
                    cpu.GetRegister(30) == kReturnSentinel,
                    "unverified_stack_frame_or_return_state");
            require(mem.regions[0].bytes == original_code &&
                    mem.regions[1].bytes == original_data &&
                    mem.regions[2].bytes == original_context,
                    "immutable_original_image_or_context_changed");
            require(mem.successful_writes == mem.effects.size() &&
                    !mem.effects.empty(),
                    "unaccounted_guest_write_effects");
            SessionResult result{};
            result.result = cpu.GetRegister(0);
            result.retired = step;
            result.end_pc = cpu.GetPC();
            result.guest_write_effects = mem.effects;
            for (const auto& effect : mem.effects) {
                const U64 low = effect.guest_address;
                const U64 high = low + effect.width;
                if (low >= kStackBase &&
                    high <= kStackBase + kStackBytes) {
                    ++result.app_stack_writes;
                } else if (low >= kCallerStackBase &&
                           high <= kCallerStackBase + kStackBytes) {
                    ++result.caller_stack_writes;
                } else {
                    throw std::runtime_error("write_outside_trusted_stacks");
                }
            }
            require(result.app_stack_writes != 0,
                    "missing_actual_app_stack_effect");
            if (entry == code_base) {
                // Original upstream crt0.S stp x29,x30,[sp,#-16]! and
                // later ldp ...; its preserved caller frame remains in
                // guest memory even though SP/X29/X30 are restored.
                auto expected_caller = original_caller_stack;
                put_le(expected_caller, kStackBytes - 16, 0, 8);
                put_le(expected_caller, kStackBytes - 8, kReturnSentinel, 8);
                require(result.caller_stack_writes == 1 &&
                        mem.regions[4].bytes == expected_caller &&
                        mem.regions[3].bytes != original_app_stack,
                        "original_crt0_caller_frame_or_app_stack_mismatch");
            } else {
                require(result.caller_stack_writes == 0 &&
                        mem.regions[4].bytes == original_caller_stack,
                        "direct_function_modified_other_caller_stack");
            }
            return result;
        }
        // Deny running from any unexpected code/host address.
        require(cpu.GetPC() >= code_base &&
                cpu.GetPC() - code_base <= code.size() - 4,
                "guest_pc_outside_checked_rx");
        const auto reasons = cpu.Step();
        (void)reasons;
        require(!mem.denied && mem.svc_count == 0 &&
                mem.other_exceptions == 0,
                "unqualified_guest_memory_or_service_effect");
    }
    throw std::runtime_error("instruction_budget_exhausted");
}

void check_case(const std::vector<U8>& code, const std::vector<U8>& data,
                U64 code_base, U64 data_base, U64 entry,
                std::size_t data_extent, const char* name,
                U64 expected_return) {
    const auto first = execute(code, data, code_base, data_base, entry,
                               data_extent, name, 4096);
    const auto second = execute(code, data, code_base, data_base, entry,
                                data_extent, name, 4096);
    require(first == second, "nondeterministic_original_guest_execution");
    require(first.result == expected_return &&
            first.retired > 0 && first.end_pc == kReturnSentinel,
            "original_guest_return_mismatch");
    std::cout << "hbx_original_" << name << "_ret=" << first.result << '\n';
    if (std::string(name) == "valid") {
        std::cout << "hbx_original_instructions_retired=" <<
            first.retired << '\n';
        std::cout << "hbx_guest_write_effects=" <<
            first.guest_write_effects.size() << '\n';
        std::cout << "hbx_app_stack_writes=" <<
            first.app_stack_writes << '\n';
        std::cout << "hbx_caller_stack_writes=" <<
            first.caller_stack_writes << '\n';
        std::cout << "hbx_full_write_ledger=two_runs_equal" << '\n';
    }
}
void refuse_case(const std::vector<U8>& code, const std::vector<U8>& data,
                 U64 code_base, U64 data_base, U64 entry,
                 std::size_t data_extent, const char* name, U64 budget) {
    bool refused = false;
    try {
        (void)execute(code, data, code_base, data_base, entry,
                      data_extent, name, budget);
    } catch (const std::runtime_error&) {
        refused = true;
    }
    require(refused, "invalid_guest_case_accepted");
    std::cout << "hbx_rejected_" << name << "=1\n";
}
} // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 7, "arguments: code.bin data.bin code-base data-base app-main data-extent");
        const auto code = load_file(argv[1]);
        const auto data = load_file(argv[2]);
        const U64 cb = parse_number(argv[3]);
        const U64 db = parse_number(argv[4]);
        const U64 entry = parse_number(argv[5]);
        const auto extent = parse_number(argv[6]);
        require(extent <= kMaxFile && code.size() >= 4 &&
                entry >= cb && entry - cb <= code.size() - 4,
                "original_entry_preflight");
        check_case(code, data, cb, db, entry, extent, "valid", 0);
        check_case(code, data, cb, db, entry, extent, "bad_magic", 2);
        check_case(code, data, cb, db, entry, extent, "bad_version", 2);
        check_case(code, data, cb, db, entry, extent, "bad_size", 2);
        refuse_case(code, data, cb, db, entry, extent, "bad_pointer", 4096);
        refuse_case(code, data, cb, db, entry, extent, "no_stack_write", 4096);
        refuse_case(code, data, cb, db, entry, extent, "bad_entry", 4096);
        refuse_case(code, data, cb, db, entry, extent, "valid", 1);
        std::cout << "NX2_HBX_STAGE1_ORIGINAL_GUEST_PASS\n"
                  << "guest_hbx_abi=custom_launcher_v3\n"
                  << "original_aarch64_code=executed_inside_dynarmic\n"
                  << "host_services_dispatched=0\n"
                  << "nintendo_horizon_calls=0\n"
                  << "switch2_hardware_observations=0\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "NX2_HBX_STAGE1_REFUSED:" << e.what() << '\n';
        return 1;
    }
}
