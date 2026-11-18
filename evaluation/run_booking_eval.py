import json
import os
from collections import Counter

from llm_client import interpret_availability


RESOURCES = [
    {"id": 1, "name": "ห้องประชุมใหญ่"},
    {"id": 2, "name": "ห้องประชุมเล็ก"},
    {"id": 3, "name": "โปรเจกเตอร์"},
]

BIG_ROOM_SLOT = {
    "resource_id": 1,
    "start_at": "2026-11-19T14:00:00+07:00",
    "end_at": "2026-11-19T15:00:00+07:00",
}

CASES = [
    (
        "TH-01", "TH",
        "จองห้องประชุมใหญ่วันที่ 19 พฤศจิกายน 2026 เวลา 14:00 ถึง 15:00",
        ("prepare_booking", BIG_ROOM_SLOT),
    ),
    (
        "TH-02", "TH",
        "ยกเลิกการจองเลขที่ 42",
        ("prepare_cancellation", {"booking_id": 42}),
    ),
    (
        "TH-03", "TH",
        "แก้ไขการจองเลขที่ 42 เป็นห้องประชุมเล็ก วันที่ 2026-11-20 เวลา 15:00 ถึง 16:00",
        (
            "prepare_edit",
            {
                "booking_id": 42,
                "resource_id": 2,
                "start_at": "2026-11-20T15:00:00+07:00",
                "end_at": "2026-11-20T16:00:00+07:00",
            },
        ),
    ),
    (
        "TH-04", "TH",
        "ห้องประชุมใหญ่ว่างไหม",
        None,
    ),
    (
        "EN-01", "EN",
        "Book the big meeting room on 2026-11-19 from 14:00 to 15:00.",
        ("prepare_booking", BIG_ROOM_SLOT),
    ),
    (
        "EN-02", "EN",
        "Cancel booking number 42.",
        ("prepare_cancellation", {"booking_id": 42}),
    ),
    (
        "EN-03", "EN",
        "Is the projector free on 2026-11-19 from 14:00 to 15:00?",
        ("check_availability", {**BIG_ROOM_SLOT, "resource_id": 3}),
    ),
    (
        "EN-04", "EN",
        "Is the projector free?",
        None,
    ),
]


def main():
    os.environ["LLM_MODE"] = "mock"
    totals = Counter()
    passes = Counter()
    failures = []

    print("Mode: mock | Scope: tool selection and arguments")
    for case_id, language, message, expected in CASES:
        totals[language] += 1
        try:
            result = interpret_availability(message, RESOURCES)
            actual = None if result is None else (result[0], json.loads(result[1]))
        except Exception as exc:
            actual = {"error": f"{type(exc).__name__}: {exc}"}

        if actual == expected:
            passes[language] += 1
            print(f"PASS {case_id}")
        else:
            failures.append((case_id, message, expected, actual))
            print(f"FAIL {case_id}")

    print(f"\nTotal: {sum(passes.values())}/{len(CASES)}")
    for language in ("TH", "EN"):
        print(f"{language}: {passes[language]}/{totals[language]}")

    for case_id, message, expected, actual in failures:
        print(f"\n{case_id} | {message}")
        print(f"  Expected: {expected!r}")
        print(f"  Actual:   {actual!r}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())