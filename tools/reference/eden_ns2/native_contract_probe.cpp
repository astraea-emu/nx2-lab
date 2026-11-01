// SPDX-License-Identifier: GPL-3.0-only
// NX2-authored source-qualification test. Linked ONLY to frozen upstream
// Eden-NS2 header implementations in ephemeral CI; no vendor code is copied.
#include <array>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <optional>
#include <span>
#include <vector>

#include "core/hle/service/am/service/graphics_supervisor_protocol.h"
#include "core/hle/service/am/service/graphics_syncpoint_cache.h"
#include "core/hle/service/am/service/native_image_layout.h"
#include "core/hle/service/am/service/native_video_layout.h"
#include "core/hle/service/nvdrv/devices/gpu_address_space_layout.h"
#include "video_core/native_semaphore.h"

namespace {
int assertions = 0;
int failed = 0;
void check(bool condition, const char* expression, int line) {
    ++assertions;
    if (!condition) {
        ++failed;
        std::cerr << "NX2_EDEN_CHECK_FAIL line=" << line
                  << " condition=" << expression << '\n';
    }
}
#define VERIFY(x) check(static_cast<bool>(x), #x, __LINE__)

void graphics_bootstrap() {
    using namespace Service::AM::GraphicsSupervisorProtocol;
    constexpr std::array<u32, 16> packet{
        0x14, 0x8000000c, 2, 0xffff8001,
        0x51, 0, 5, 0x80000000,
        0, 0, 0, 0, 0, 0, 0, 0};
    const auto original = DecodeBootstrap(packet);
    VERIFY(original);
    if (!original) return;
    VERIFY(original->process_handle == 0xffff8001);
    VERIFY(original->applet_resource_user_id == 0x51);
    VERIFY(original->flags == 0x8000000000000005ULL);
    VERIFY(IsLocalBootstrap(*original));
    VERIFY(NativeGpuProfileForBootstrap(original->flags) == 0x807);
    VERIFY(NativeGpuProfileForBootstrap(0x8000000000000006ULL) == 0x808);
    VERIFY(NativeGpuProfileForBootstrap(0x8000000000000007ULL) == 0x808);
    VERIFY(NativeGpuProfileForBootstrap(0x8000000000000008ULL) == 0);
    VERIFY(IsSupportedDisplaySession(0x300030000ULL));
    VERIFY(!IsSupportedDisplaySession(0x300030001ULL));

    for (std::size_t size = 0; size < packet.size(); ++size) {
        VERIFY(!DecodeBootstrap(std::span{packet}.first(size)));
    }
    for (std::size_t index : {0U, 1U, 2U}) {
        auto bad = packet;
        bad[index] ^= 1U;
        VERIFY(!DecodeBootstrap(bad));
    }
    auto remote = packet;
    remote[8] = 0x1000;
    const auto accepted_remote = DecodeBootstrap(remote);
    VERIFY(accepted_remote);
    if (accepted_remote) VERIFY(!IsLocalBootstrap(*accepted_remote));
    auto unsupported = packet;
    unsupported[6] = 9;
    const auto decoded = DecodeBootstrap(unsupported);
    VERIFY(decoded);
    if (decoded) VERIFY(!IsLocalBootstrap(*decoded));
    const RequestGroupDuplicateRequest group{0x21, 0};
    VERIFY(group.group == 0);
    VERIFY(ClassifyRequestGroupEventDuplicate(RequestGroupCount, true, true, true) ==
           RequestGroupDuplicateStatus::OutOfRange);
    VERIFY(ClassifyRequestGroupEventDuplicate(0, true, false, true) ==
           RequestGroupDuplicateStatus::MissingEvent);
    VERIFY(ClassifyRequestGroupEventDuplicate(0, true, true, true) ==
           RequestGroupDuplicateStatus::Ready);
}

void native_graphics_memory() {
    using namespace Service::Nvidia::Devices;
    constexpr auto normal = GetGpuAddressSpaceLayout(false);
    constexpr auto native = GetGpuAddressSpaceLayout(true);
    VERIFY(normal.end == (1ULL << 37));
    VERIFY(native.end == (1ULL << 40));
    VERIFY(native.split > normal.split);
    VERIFY(native.split - native.start >= 0x7ff8000000ULL + (1ULL << 32));
    VERIFY(GetGpuAddressSpaceBigPageSize(true, 0x1000) == 0x10000);
    VERIFY(GetGpuAddressSpaceBigPageSize(false, 0x1000) == 0x1000);
    VERIFY(GpuPageAddress(0x400000, 17) == 0x8000000000ULL);
    const GpuAddressSpaceLayout view{native.start, 0, 0xa000000000ULL};
    VERIFY(IsSupportedNativeAddressSpaceView(5, 0x1000, 0, view, native));
    VERIFY(!IsSupportedNativeAddressSpaceView(5, 0x10000, 0, view, native));
    VERIFY(!IsSupportedNativeAddressSpaceView(5, 0x1000, 1, view, native));
    VERIFY(!IsSupportedNativeAddressSpaceView(1, 0x1000, 0, view, native));
    auto bad = view;
    bad.start += 1;
    VERIFY(!IsSupportedNativeAddressSpaceView(5, 0x1000, 0, bad, native));
}

void native_image_sizing() {
    using Service::AM::CalculateNativeImageRequirements;
    std::array<u32, 16> preferences{0, 2, 0x0437077f, 0, 7, 120, 1, 1};
    const auto one = CalculateNativeImageRequirements(preferences, 1);
    VERIFY(one);
    if (!one) return;
    VERIFY(one->size == 8847360ULL);
    VERIFY(one->alignment == 4096);
    const auto two = CalculateNativeImageRequirements(preferences, 2);
    VERIFY(two);
    if (two) VERIFY(two->size == 17694720ULL);
    VERIFY(!CalculateNativeImageRequirements(preferences, 0));
    VERIFY(!CalculateNativeImageRequirements(preferences, 0xffffffffU));
    VERIFY(!CalculateNativeImageRequirements(std::span{preferences}.first(15), 1));
    auto bad_pitch = preferences;
    bad_pitch[5] = 119;
    VERIFY(!CalculateNativeImageRequirements(bad_pitch, 1));
    auto bad_block = preferences;
    bad_block[4] = 9;
    VERIFY(!CalculateNativeImageRequirements(bad_block, 1));
    auto bad_reserved = preferences;
    bad_reserved[10] = 1;
    VERIFY(!CalculateNativeImageRequirements(bad_reserved, 1));

    // Independent math oracle for a second NX2-authored width/height fixture:
    // 65 pixels * 4 bytes -> 5 GOBs per row; 33 rows aligned to 64 at block 32.
    std::array<u32, 16> small{0, 2, (32U << 16) | 64U, 0, 5, 5, 1, 1};
    const auto calculated = CalculateNativeImageRequirements(small, 2);
    VERIFY(calculated);
    if (calculated) VERIFY(calculated->size == 40960ULL);
    small[5] = 4; // cannot hold 65 x 4 bytes
    VERIFY(!CalculateNativeImageRequirements(small, 2));
}

void native_video_layout() {
    using Service::AM::CalculateNativeVideoImageLayout;
    std::array<u32, 16> video{0, 5, 0x059f09ff};
    auto layout = CalculateNativeVideoImageLayout(video, 4);
    VERIFY(layout);
    if (!layout) return;
    VERIFY(layout->size == 0x3c00000ULL);
    VERIFY(layout->alignment == 4096);
    VERIFY(layout->row_bytes == 10240);
    VERIFY(layout->image_stride == 0xf00000);
    VERIFY(!CalculateNativeVideoImageLayout(video, 0));
    VERIFY(!CalculateNativeVideoImageLayout(std::span{video}.first(15), 1));
    video[3] = 1;
    VERIFY(!CalculateNativeVideoImageLayout(video, 1));
    video[3] = 0;
    video[1] = 6;
    VERIFY(!CalculateNativeVideoImageLayout(video, 1));
}

void graphics_syncpoints() {
    using namespace Service::AM::GraphicsSyncpointCache;
    VERIFY(ExtendCounter(Unallocated, 7) == 7);
    VERIFY(ExtendCounter(0xffffffffULL, 0) == 0x100000000ULL);
    VERIFY(ExtendCounter(0x1ffffffffULL, 3) == 0x200000003ULL);
    CounterValue value;
    VERIFY(value.Observe(std::nullopt) == Unallocated);
    VERIFY(value.Observe(0xfffffffeU) == 0xfffffffeULL);
    VERIFY(value.Observe(1U) == 0x100000001ULL);
    VERIFY(value.Observe(std::nullopt) == Unallocated);
    VERIFY(value.Observe(3U) == 0x100000003ULL);
}

void gpu_wait_scheduling() {
    const Tegra::NativeSemaphoreWait equal{0x1000, 7, 1};
    const Tegra::NativeSemaphoreWait gequal{0x2000, 7, 4};
    const Tegra::NativeSemaphoreWait bits{0x3000, 4, 8};
    VERIFY(!equal.Matches(6));
    VERIFY(equal.Matches(7));
    VERIFY(!equal.Matches(8));
    VERIFY(!gequal.Matches(6));
    VERIFY(gequal.Matches(8));
    VERIFY(!bits.Matches(0));
    VERIFY(bits.Matches(4));
    VERIFY(!Tegra::NativeSemaphoreWait::Supported(2));

    constexpr std::array<std::size_t, 3> channels{0, 1, 2};
    std::array<u32, 3> words{0, 0, 0};
    std::array<bool, 3> pending{true, true, true};
    std::vector<std::size_t> order;
    const auto ready = [&](std::size_t c) {
        return pending[c] && words[c] >= 1;
    };
    const auto dispatch = [&](std::size_t c) {
        order.push_back(c);
        pending[c] = false;
        if (c > 0) words[c - 1] = 1;
    };
    VERIFY(Tegra::ResumeReadyNativeChannels(channels, ready, dispatch) == 0);
    VERIFY(order.empty());
    words[2] = 1;
    VERIFY(Tegra::ResumeReadyNativeChannels(channels, ready, dispatch) == 3);
    VERIFY((order == std::vector<std::size_t>{2, 1, 0}));
    VERIFY(Tegra::ResumeReadyNativeChannels(channels, ready, dispatch) == 0);
}
} // namespace

int main() {
    graphics_bootstrap();
    native_graphics_memory();
    native_image_sizing();
    native_video_layout();
    graphics_syncpoints();
    gpu_wait_scheduling();
    if (failed == 0) {
        std::cout << "NX2_EDEN_NS2_NATIVE_CONTRACT_PASS assertions=" << assertions << '\n';
    } else {
        std::cerr << "NX2_EDEN_NS2_NATIVE_CONTRACT_FAIL assertions=" << assertions
                  << " failures=" << failed << '\n';
    }
    return failed == 0 ? 0 : 1;
}
