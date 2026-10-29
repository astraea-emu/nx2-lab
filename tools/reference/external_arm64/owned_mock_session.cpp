// Only for source-pinned AArch64 Linux research: mock service effects.
// No guest host-syscall execution; no Nintendo/Horizon ABI or service.
#include <nx2/cpu.hpp>
#include <nx2/memory.hpp>
#include <nx2/owned_image.hpp>
#include <nx2/owned_service.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr std::size_t kMessageSize = 14U;
void require(bool yes, const char* reason) {
    if (!yes) throw std::runtime_error(reason);
}

std::vector<std::byte> read_bounded(const char* path, std::size_t maximum) {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    require(f.good(), "file_open");
    const auto length = f.tellg();
    require(length >= 0 && static_cast<std::uint64_t>(length) <= maximum,
            "file_length");
    std::vector<std::byte> out(static_cast<std::size_t>(length));
    f.seekg(0);
    require(static_cast<bool>(f.read(reinterpret_cast<char*>(out.data()), length)),
            "file_read");
    return out;
}

using Message = std::array<std::byte, kMessageSize>;
Message checked_message(std::span<const std::byte> bytes) {
    require(bytes.size() == kMessageSize, "guest_message_length");
    Message result{};
    for (std::size_t i = 0; i < result.size(); ++i) result[i] = bytes[i];
    return result;
}

struct Checkpoint {
    std::uint64_t first_pc = 0;
    std::uint64_t second_pc = 0;
    std::size_t next_retired = 0;
    bool operator==(const Checkpoint&) const = default;
};

Checkpoint execute_mock_only(
    const nx2::OwnedImage& image, const Message& data,
    std::uint64_t base, bool readable = true) {
    require(image.word_count == 10U && image.entry_offset == 0U,
            "unreviewed_executable_layout");
    const auto code = image.program();
    require(code[4] == 0xD4000001U && code[7] == 0xD4000001U,
            "changed_external_svc_word");
    const std::uint64_t literal = code[8] |
        (static_cast<std::uint64_t>(code[9]) << 32U);
    require(literal == base, "source_linked_pointer_mismatch");
    require(base <= std::numeric_limits<std::uint64_t>::max() - kMessageSize,
            "guest_address_overflow");
    const auto stop = nx2::run_owned_program(code, 16U);
    require(stop.stop == nx2::StopReason::service_request &&
            stop.retired == 4U && stop.state.pc == 16U &&
            stop.service_immediate == 0U &&
            stop.stopped_word == 0xD4000001U &&
            stop.state.x[0] == 1U && stop.state.x[1] == base &&
            stop.state.x[2] == kMessageSize && stop.state.x[8] == 64U,
            "first_linux_source_service_demand_changed");

    // Map only the exact checked original 14 source-message bytes.
    // Two legitimate overlapping 64-bit reads cover this fixed-size
    // message without exporting a host pointer or invoking host writes.
    auto private_data = data;
    std::array<nx2::GuestMemoryRegion, 1> regions{{
        nx2::GuestMemoryRegion{base, private_data, readable, false}}};
    nx2::GuestMemoryView memory(regions);
    const auto low = memory.load64(base);
    const auto high = memory.load64(base + (kMessageSize - 8U));
    require(low.has_value() && high.has_value(), "guest_message_access_denied");
    Message readback{};
    for (std::size_t i = 0; i < 8; ++i) {
        readback[i] = static_cast<std::byte>((*low >> (8U * i)) & 0xFFU);
        readback[i + 6U] = static_cast<std::byte>((*high >> (8U * i)) & 0xFFU);
    }
    constexpr std::array<char, kMessageSize> expected{
        'H','e','l','l','o',',',' ','W','o','r','l','d','!','\n'};
    for (std::size_t i = 0; i < expected.size(); ++i) {
        require(readback[i] == static_cast<std::byte>(expected[i]),
                "source_message_content_mismatch");
    }
    const auto continuation = nx2::apply_owned_fixture_service_reply(
        code, stop, nx2::OwnedFixtureServiceReply{
            .expected_immediate = 0U, .x0_return_value = kMessageSize});
    require(continuation.has_value() && continuation->pc == 20U &&
            continuation->x[0] == 14U && continuation->x[1] == base &&
            continuation->x[2] == 14U && continuation->x[8] == 64U,
            "explicit_mock_write_reply_refused");
    const auto after = nx2::run_owned_program(code, 8U, *continuation);
    require(after.stop == nx2::StopReason::service_request &&
            after.service_immediate == 0U &&
            after.stopped_word == 0xD4000001U &&
            after.retired == 2U && after.state.pc == 28U &&
            after.state.x[0] == 0U && after.state.x[8] == 93U,
            "second_external_exit_demand_mismatch");
    require(data == private_data, "guest_memory_mutated_by_mock");
    // The second source SVC is deliberately never retired or replied to.
    return {stop.state.pc, after.state.pc, after.retired};
}

void rejected_mutations(const nx2::OwnedImage& original,
                        const Message& bytes, std::uint64_t base) {
    unsigned rejected = 0;
    const auto refuse = [&](const nx2::OwnedImage& image,
                            const Message& data,
                            std::uint64_t address,
                            bool readable,
                            const char* label) {
        try { (void)execute_mock_only(image, data, address, readable); }
        catch (const std::runtime_error&) { ++rejected; return; }
        throw std::runtime_error(std::string("mutated_fixture_admitted:") + label);
    };
    auto changed = original;
    changed.words[4] ^= 0x20U;
    refuse(changed, bytes, base, true, "first_svc");
    changed = original; changed.words[7] ^= 0x20U;
    refuse(changed, bytes, base, true, "second_svc");
    changed = original; changed.words[3] ^= 0x20U;
    refuse(changed, bytes, base, true, "first_service_id");
    changed = original; changed.words[6] ^= 0x20U;
    refuse(changed, bytes, base, true, "second_service_id");
    changed = original; changed.words[8] ^= 1U;
    refuse(changed, bytes, base, true, "literal_pointer");
    auto changed_message = bytes;
    changed_message[0] ^= std::byte{1};
    refuse(original, changed_message, base, true, "message_content");
    refuse(original, bytes, base, false, "unreadable_message");
    refuse(original, bytes, base + 1U, true, "wrong_guest_base");
    changed = original; changed.entry_offset = 4U;
    refuse(changed, bytes, base, true, "entry");
    changed = original; changed.word_count = 9U;
    refuse(changed, bytes, base, true, "truncated_code");
    require(rejected == 10U, "missing_negative_case");
    std::cout << "mock_route_rejected_mutations=10\n";
}
} // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 4, "expected_image_message_pointer_args");
        const auto raw = read_bounded(argv[1],
            nx2::kOwnedHeaderSize + 4U * nx2::kMaxOwnedWords);
        const auto image = nx2::parse_owned_image(raw);
        require(image.has_value(), "owned_image_parse_refused");
        const auto message = checked_message(read_bounded(argv[2], kMessageSize));
        const std::string address_string(argv[3]);
        std::size_t length = 0;
        const auto base = std::stoull(address_string, &length, 0);
        require(length == address_string.size() && base != 0U,
                "guest_address_argument_refused");
        const auto first = execute_mock_only(*image, message, base);
        const auto second = execute_mock_only(*image, message, base);
        require(first == second, "two_fresh_mock_routes_diverged");
        rejected_mutations(*image, message, base);
        std::cout << "NX2_EXTERNAL_MOCK_TWO_SERVICE_PASS\n"
                  << "external_original_instructions_retired=6\n"
                  << "first_boundary=mock_only_linux_write_no_host_io\n"
                  << "second_boundary=unretired_linux_exit_no_host_io\n"
                  << "guest_message_length=14_bytes_verified_from_mapped_source\n"
                  << "mock_service_return=14_bytes_in_x0\n"
                  << "fresh_mock_runs=2_identical\n"
                  << "nintendo_horizon_services=none\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "NX2_EXTERNAL_MOCK_REFUSED:" << e.what() << '\n';
        return 1;
    }
}
