import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from threading import Barrier
from unittest.mock import patch

import httpx

from fastapi.testclient import TestClient

from main import app


API = "http://127.0.0.1:8000"
BANGKOK = timezone(timedelta(hours=7))

DEMO_ACCOUNTS = (
    {"email": "alice@example.com", "password": "DemoAlice123!"},
    {"email": "bob@example.com", "password": "DemoBob123!"},
)


class BookingConcurrencyTest(unittest.TestCase):
    def login(self, account):
        response = httpx.post(f"{API}/auth/login", json=account, timeout=10)
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def find_free_slot(self, headers):
        response = httpx.get(f"{API}/resources", timeout=10)
        self.assertEqual(response.status_code, 200, response.text)
        room = next(
            (resource for resource in response.json() if resource["type"] == "room"),
            None,
        )
        self.assertIsNotNone(room, "No active meeting room found")

        first_day = datetime.now(BANGKOK).date() + timedelta(days=7)

        for offset in range(14):
            day = first_day + timedelta(days=offset)
            if day.weekday() >= 5:
                continue

            start = datetime.combine(day, time(10, 0), tzinfo=BANGKOK)
            end = start + timedelta(hours=1)
            slot = {
                "resource_id": room["id"],
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            }

            response = httpx.get(
                f"{API}/availability", headers=headers, params=slot, timeout=10
            )
            self.assertEqual(response.status_code, 200, response.text)
            if response.json()["available"]:
                return slot

        self.fail("No free weekday slot found for the concurrency test")

    def cancel_test_booking(self, booking_id, headers):
        response = httpx.post(
            f"{API}/bookings/{booking_id}/cancel",
            headers=headers,
            timeout=10,
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_only_one_request_can_book_the_same_slot(self):
        accounts = [self.login(account) for account in DEMO_ACCOUNTS]
        slot = self.find_free_slot(accounts[0])
        start_together = Barrier(2)

        def submit(headers):
            with httpx.Client(base_url=API, timeout=15) as client:
                start_together.wait(timeout=10)
                return client.post("/bookings", headers=headers, json=slot)

        with ThreadPoolExecutor(max_workers=2) as pool:
            requests = [pool.submit(submit, headers) for headers in accounts]
            responses = [future.result() for future in requests]

        for headers, response in zip(accounts, responses):
            if response.status_code == 201:
                self.addCleanup(
                    self.cancel_test_booking, response.json()["id"], headers
                )

        self.assertCountEqual(
            [response.status_code for response in responses],
            [201, 409],
            [(response.status_code, response.text) for response in responses],
        )
    def test_only_owner_can_confirm_and_confirmation_is_idempotent(self):
        alice = self.login(DEMO_ACCOUNTS[0])
        bob = self.login(DEMO_ACCOUNTS[1])
        slot = self.find_free_slot(bob)

        with httpx.Client(base_url=API, timeout=10) as client:
            draft = client.post("/ai/prepare-booking", headers=bob, json=slot)
            self.assertEqual(draft.status_code, 200, draft.text)
            self.assertEqual(draft.json()["kind"], "pending_confirmation")
            confirm_path = f"/ai/confirm/{draft.json()['action_id']}"

            before = client.get("/availability", headers=bob, params=slot)
            self.assertEqual(before.status_code, 200, before.text)
            self.assertTrue(before.json()["available"])

            denied = client.post(confirm_path, headers=alice)
            self.assertEqual(denied.status_code, 404, denied.text)

            first = client.post(confirm_path, headers=bob)
            self.assertEqual(first.status_code, 200, first.text)
            booking_id = first.json()["booking_id"]
            self.addCleanup(self.cancel_test_booking, booking_id, bob)
            self.assertEqual(first.json()["kind"], "confirmed")

            second = client.post(confirm_path, headers=bob)
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(second.json()["booking_id"], booking_id)

            after = client.get("/availability", headers=bob, params=slot)
            self.assertEqual(after.status_code, 200, after.text)
            self.assertFalse(after.json()["available"])

    def test_manual_booking_still_works_when_ai_times_out(self):
        bob = self.login(DEMO_ACCOUNTS[1])
        slot = self.find_free_slot(bob)

        with TestClient(app) as client:
            with patch.dict(
                "os.environ",
                {
                    "LLM_MODE": "openai",
                    "LLM_API_KEY": "fake-test-key",
                    "LLM_MODEL": "gpt-4.1-mini",
                },
            ), patch(
                "llm_client.httpx.post",
                side_effect=httpx.ReadTimeout("Simulated AI timeout"),
            ) as provider_call:
                ai_response = client.post(
                    "/ai/message",
                    headers=bob,
                    json={"message": "ห้องประชุมใหญ่ว่างไหม"},
                )
                self.assertEqual(ai_response.status_code, 503, ai_response.text)
                self.assertIn("จองผ่านฟอร์ม", ai_response.json()["detail"])
                provider_call.assert_called_once()

                booking = client.post("/bookings", headers=bob, json=slot)

            self.assertEqual(booking.status_code, 201, booking.text)
            self.addCleanup(self.cancel_test_booking, booking.json()["id"], bob)
            self.assertEqual(booking.json()["status"], "confirmed")


if __name__ == "__main__":
    unittest.main(verbosity=2)