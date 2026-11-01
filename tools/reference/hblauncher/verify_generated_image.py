#!/usr/bin/env python3
"""Strict, host-only attestation for the original generated HBX app image.

The report comes from the pinned third-party build tool: checking its hashes
does not authenticate a compromised build tool or malicious paired inputs.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

MAX_IMAGE = 2 * 1024 * 1024
MAX_REPORT = 64 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class Refused(ValueError):
    pass


def insist(ok, reason):
    if not ok:
        raise Refused(reason)


def no_duplicate_pairs(pairs):
    d = {}
    for key, value in pairs:
        if key in d:
            raise Refused("duplicate_json_key:" + key)
        d[key] = value
    return d


def read_bounded(source, maximum, label):
    raw = source.read(maximum + 1)
    insist(len(raw) <= maximum, label + "_too_large")
    return raw


def bounded_input_negative_cases():
    for label, maximum in (("report", MAX_REPORT), ("code", MAX_IMAGE), ("data", MAX_IMAGE)):
        class OversizedSource:
            def read(self, size):
                insist(size == maximum + 1, "image_input_read_was_not_bounded")
                return bytes(size)
        try:
            read_bounded(OversizedSource(), maximum, label)
        except Refused as error:
            if str(error) != label + "_too_large":
                raise
        else:
            raise Refused("oversized_image_input_admitted:" + label)
    return 3


def parse_address(v):
    insist(isinstance(v, str) and v.startswith("0x"), "address_not_hex")
    try:
        n = int(v, 16)
    except ValueError as ex:
        raise Refused("bad_hex_address") from ex
    insist(0 <= n < 2**64, "address_range")
    return n


def check(report, code, data):
    insist(isinstance(report, dict), "invalid_report")
    insist(report.get("format") == "hblauncher-native-app/1" and
           report.get("id") == "hello-cpu" and
           report.get("kind") == "native" and
           type(report.get("abi")) is int and report["abi"] == 3,
           "wrong_source_profile")
    for field, value in (("codeBytes", len(code)), ("dataBytes", len(data))):
        insist(type(report.get(field)) is int and report[field] == value,
               "declared_extent_mismatch:" + field)
    insist(4 <= len(code) <= MAX_IMAGE and not (len(code) % 4) and
           len(data) <= MAX_IMAGE, "image_size_or_alignment")
    for name, raw in (("codeSha256", code), ("dataSha256", data)):
        digest = report.get(name)
        insist(isinstance(digest, str) and SHA256.fullmatch(digest) is not None,
               "invalid_digest:" + name)
        insist(hashlib.sha256(raw).hexdigest() == digest,
               "image_digest_mismatch:" + name)
    extent = report.get("dataRegionBytes")
    insist(type(extent) is int and len(data) <= extent <= MAX_IMAGE,
           "invalid_data_region")
    cb = parse_address(report.get("codeBase"))
    db = parse_address(report.get("dataBase"))
    main = parse_address(report.get("hbxAppMain"))
    start = parse_address(report.get("entry"))
    insist(cb % 4096 == 0 and db % 4096 == 0 and
           start == cb and main % 4 == 0 and cb <= main <= cb+len(code)-4,
           "code_entry_identity")
    insist(db >= cb + len(code) or cb >= db + extent,
           "image_mapping_overlap")
    insist(cb + len(code) < 2**64 and db + extent < 2**64,
           "mapping_overflow")
    return {
        "original_hbx_code_sha256": report["codeSha256"],
        "original_hbx_data_sha256": report["dataSha256"],
        "hbx_source_profile": "hello-cpu/HBX-v3",
        "original_binary_admission": "checked_against_pinned_builder_report",
        "switch2_hardware_verified": False,
    }


def negative_cases(report, code, data):
    tests = []
    mutated = bytearray(code)
    mutated[0] ^= 1
    tests.append(("modified_code_byte", report, bytes(mutated), data))
    tests.append(("truncated_code", report, code[:-4], data))
    tests.append(("extra_code", report, code + b"\0\0\0\0", data))
    tests.append(("changed_data", report, code, data + b"\xff"))
    report_changes = [
        ("changed_code_hash", "codeSha256", "0" * 64),
        ("changed_data_hash", "dataSha256", "0" * 64),
        ("false_code_size", "codeBytes", len(code) - 4),
        ("false_data_size", "dataBytes", len(data) + 1),
        ("short_data_extent", "dataRegionBytes", -1),
        ("wrong_entry", "entry", "0xdeadbeef"),
        ("wrong_main", "hbxAppMain", "0xdeadbeef"),
        ("moved_code_base", "codeBase", "0xc000001"),
        ("misaligned_data_base", "dataBase", "0xd000001"),
        ("overlapping_data", "dataBase", report["codeBase"]),
        ("wrong_abi", "abi", 4),
        ("wrong_kind", "kind", "linux"),
        ("wrong_format", "format", "NX2OWNED"),
    ]
    for label, key, value in report_changes:
        d = copy.deepcopy(report)
        d[key] = value
        tests.append((label, d, code, data))
    for label, altered, c, d in tests:
        try:
            check(altered, c, d)
        except Refused:
            continue
        raise Refused("invalid_original_binary_admitted:" + label)
    for malformed in ('{"abi":3,"abi":3}', '{"codeBytes":1,"codeBytes":2}'):
        try:
            json.loads(malformed, object_pairs_hook=no_duplicate_pairs)
        except Refused:
            continue
        raise Refused("duplicate_json_admitted")
    return len(tests) + 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    args = parser.parse_args()
    try:
        insist(args.report.stat().st_size <= MAX_REPORT, "report_too_large")
        insist(args.code.stat().st_size <= MAX_IMAGE, "code_too_large")
        insist(args.data.stat().st_size <= MAX_IMAGE, "data_too_large")
        with args.report.open("rb") as source:
            report = json.loads(read_bounded(source, MAX_REPORT, "report").decode("utf-8"),
                                object_pairs_hook=no_duplicate_pairs)
        with args.code.open("rb") as source:
            code = read_bounded(source, MAX_IMAGE, "code")
        with args.data.open("rb") as source:
            data = read_bounded(source, MAX_IMAGE, "data")
        accepted = check(report, code, data)
        negatives = negative_cases(report, code, data)
        input_negatives = bounded_input_negative_cases()
    except (OSError, Refused, ValueError, TypeError) as e:
        parser.exit(2, "NX2_HBX_IMAGE_REFUSED:" + str(e) + "\n")
    print("NX2_HBX_ORIGINAL_IMAGE_ADMISSION_PASS")
    for key in ("original_hbx_code_sha256", "original_hbx_data_sha256",
                "hbx_source_profile", "original_binary_admission"):
        print(key + "=" + accepted[key])
    print("hbx_image_negative_cases=" + str(negatives))
    print("hbx_image_bounded_input_negative_cases=" + str(input_negatives))
    print("console_code_executed=0")


if __name__ == "__main__":
    main()
