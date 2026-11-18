import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException

from booking_service import validate_booking_time
from redaction import redact_for_llm


class BookingRulesTest(unittest.TestCase):
    def setUp(self):
        self.clock = patch("booking_service.datetime")
        frozen = self.clock.start()
        self.addCleanup(self.clock.stop)
        frozen.now.return_value = datetime(2030, 1, 1, tzinfo=timezone.utc)

    def slot(self, date, start, end):
        return (
            datetime.fromisoformat(f"{date}T{start}:00+07:00"),
            datetime.fromisoformat(f"{date}T{end}:00+07:00"),
        )

    def test_weekday_opening_and_closing_boundaries(self):
        start, end = self.slot("2030-01-07", "09:00", "18:00")
        validate_booking_time(start, end)
        validate_booking_time(
            start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        )

    def test_rejects_weekends_and_out_of_hours(self):
        for date, start, end in (
            ("2030-01-05", "10:00", "11:00"),
            ("2030-01-06", "10:00", "11:00"),
            ("2030-01-07", "08:59", "10:00"),
            ("2030-01-07", "17:00", "18:01"),
        ):
            with self.subTest(date=date, start=start, end=end):
                with self.assertRaises(HTTPException) as error:
                    validate_booking_time(*self.slot(date, start, end))
                self.assertEqual(error.exception.status_code, 422)

    def test_rejects_past_and_invalid_time_order(self):
        for date, start, end in (
            ("2029-12-31", "10:00", "11:00"),
            ("2030-01-07", "10:00", "10:00"),
            ("2030-01-07", "11:00", "10:00"),
        ):
            with self.subTest(date=date, start=start, end=end):
                with self.assertRaises(HTTPException) as error:
                    validate_booking_time(*self.slot(date, start, end))
                self.assertEqual(error.exception.status_code, 422)

    def test_rejects_cross_day_slot(self):
        start, end = self.slot("2030-01-07", "09:00", "10:00")
        with self.assertRaises(HTTPException) as error:
            validate_booking_time(start, end + timedelta(days=1))
        self.assertEqual(error.exception.status_code, 422)


class RedactionTest(unittest.TestCase):
    def test_masks_supported_personal_data_and_secret_formats(self):
        for text, expected in (
            ("alice@example.com", "[REDACTED_EMAIL]"),
            ("1-2345-67890-12-3", "[REDACTED_THAI_ID]"),
            ("081-234-5678", "[REDACTED_PHONE]"),
            ("+66 81 234 5678", "[REDACTED_PHONE]"),
            ("02-123-4567", "[REDACTED_PHONE]"),
            ("sk-abcdefghijklmnop1234", "[REDACTED_API_KEY]"),
            ("AIza" + "A" * 35, "[REDACTED_API_KEY]"),
            ("api_key=abcdefghijklmnop", "api_key=[REDACTED_API_KEY]"),
        ):
            with self.subTest(text=text):
                self.assertEqual(redact_for_llm(text), expected)

    def test_keeps_booking_arguments_and_masks_appended_email(self):
        request = "จองโปรเจกเตอร์ วันที่ 2030-01-07 เวลา 09:00 ถึง 10:00"
        self.assertEqual(redact_for_llm(request), request)
        self.assertEqual(
            redact_for_llm(request + " alice@example.com"),
            request + " [REDACTED_EMAIL]",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
