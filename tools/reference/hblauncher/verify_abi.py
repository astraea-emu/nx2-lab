#!/usr/bin/env python3
"""Independent host-only conformance intake for a frozen HBLauncher SDK ABI.

An upstream custom HBX ABI is NOT Nintendo Horizon or a verified console ABI.
No external repository files are copied into NX2 Lab.
"""
import argparse
import copy
import json
from pathlib import Path

EXPECTED = {
    "abiVersion": 3,
    "ctxSize": 696,
    "gpuSize": 256,
    "vkDispatchFields": 73,
    "vkDispatchBytes": 584,
    "ctx": {
        "magic": 0, "abi_version": 4, "size": 8, "flags": 12,
        "now_ns": 40, "tick_hz": 48, "heap_base": 64,
        "stack_base": 112, "stack_size": 120, "ui": 176,
        "gpu": 200, "input": 456, "args": 520,
    },
    "gpu": {"instance": 0, "device": 16, "queue": 24, "dispatch": 192,
            "vi_window": 200, "present_state": 232},
}
MAX_BYTES = 64 * 1024


class Refused(ValueError):
    pass


def no_duplicate_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise Refused("duplicate_key:" + key)
        obj[key] = value
    return obj


def read_abi(source):
    """Bound bytes before JSON decoding, even if an input file grows."""
    data = source.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Refused("oversized_abi_json")
    return json.loads(data, object_pairs_hook=no_duplicate_pairs)


def bounded_input_negative_cases():
    class OversizedSource:
        def read(self, size):
            if size != MAX_BYTES + 1:
                raise Refused("abi_read_was_not_bounded")
            return bytes(size)
    try:
        read_abi(OversizedSource())
    except Refused as error:
        if str(error) != "oversized_abi_json":
            raise
    else:
        raise Refused("oversized_abi_json_admitted")
    return 1


def verify(obj):
    if not isinstance(obj, dict):
        raise Refused("top_level_not_object")
    for key, expected in EXPECTED.items():
        value = obj.get(key)
        if isinstance(expected, dict):
            if not isinstance(value, dict):
                raise Refused("missing_object:" + key)
            for field, fixed in expected.items():
                got = value.get(field)
                if type(got) is not int or got != fixed:
                    raise Refused("changed_field:" + key + "." + field)
            offsets = [v for v in value.values() if type(v) is int]
            if len(offsets) != len(value) or len(set(offsets)) != len(offsets):
                raise Refused("invalid_or_duplicate_offsets:" + key)
        elif type(value) is not int or value != expected:
            raise Refused("changed_field:" + key)
    ctx = obj["ctx"]
    gpu = obj["gpu"]
    if len(ctx) < 26 or len(gpu) < 15:
        raise Refused("incomplete_source_abi")
    if not all(type(v) is int and 0 <= v < obj["ctxSize"] for v in ctx.values()):
        raise Refused("ctx_offset_out_of_range")
    if not all(type(v) is int and 0 <= v < obj["gpuSize"] for v in gpu.values()):
        raise Refused("gpu_offset_out_of_range")
    if ctx["gpu"] + obj["gpuSize"] > obj["ctxSize"]:
        raise Refused("gpu_region_overflow")
    if obj["vkDispatchBytes"] != obj["vkDispatchFields"] * 8:
        raise Refused("vk_dispatch_size_mismatch")
    return {"sdk": "HBLauncher", "contract": "custom_hbx_v3",
            "classification": "externally_authored_host_only",
            "horizon_abi_verified": False,
            "switch2_device_observed": False,
            "ctx_size": obj["ctxSize"], "gpu_size": obj["gpuSize"],
            "critical_offsets_checked": sum(
                len(v) if isinstance(v, dict) else 1
                for v in EXPECTED.values())}


def negative_cases(obj):
    variations = []
    for key, value in [("abiVersion", 4), ("ctxSize", 512),
                       ("gpuSize", 128), ("vkDispatchFields", 74),
                       ("vkDispatchBytes", 576)]:
        altered = copy.deepcopy(obj)
        altered[key] = value
        variations.append((key, altered))
    for group, key, value in [
        ("ctx", "size", 9), ("ctx", "magic", 4),
        ("ctx", "gpu", 224), ("ctx", "args", -1),
        ("ctx", "stack_base", 696), ("gpu", "queue", 16),
        ("gpu", "dispatch", 196), ("gpu", "present_state", 260),
    ]:
        altered = copy.deepcopy(obj)
        altered[group][key] = value
        variations.append((group + "." + key, altered))
    for group, key in [("ctx", "magic"), ("gpu", "instance")]:
        altered = copy.deepcopy(obj)
        altered[group].pop(key)
        variations.append(("missing_" + group + "." + key, altered))
    altered = copy.deepcopy(obj)
    altered["ctx"]["flags"] = True
    variations.append(("boolean_as_offset", altered))
    for name, altered in variations:
        try:
            verify(altered)
        except Refused:
            continue
        raise Refused("negative_accepted:" + name)
    for malformed in ['{"abiVersion":3,"abiVersion":3}',
                      '{"ctx":{"gpu":200,"gpu":200}}']:
        try:
            json.loads(malformed, object_pairs_hook=no_duplicate_pairs)
        except Refused:
            continue
        raise Refused("duplicate_json_key_accepted")
    return len(variations) + 2


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--abi", required=True, type=Path)
    p.add_argument("--source-revision", required=True)
    args = p.parse_args()
    try:
        with args.abi.open("rb") as source:
            obj = read_abi(source)
        result = verify(obj)
        count = negative_cases(obj)
        input_count = bounded_input_negative_cases()
    except (OSError, Refused, ValueError, TypeError) as e:
        p.exit(2, "HBX_CONTRACT_REFUSED:" + str(e) + "\n")
    result.update({"source_revision": args.source_revision,
                   "negative_cases": count, "bounded_input_negative_cases": input_count})
    print("NX2_HBX_HOST_ABI_CONTRACT_PASS")
    print("hbx_abi_version=3")
    print(f"hbx_contract_negative_cases={count}")
    print(f"hbx_bounded_input_negative_cases={input_count}")
    print("console_observations=0")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
