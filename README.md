# Room and Equipment Booking

A React application with a Python API and PostgreSQL database for booking meeting rooms and equipment. Users can register, sign in, create and view bookings, and edit or cancel their own bookings through a form or supported assistant requests.

The interface uses Thai. The assistant has an offline Mock mode and an OpenAI mode. All booking times use Asia/Bangkok (UTC+7), displayed in 24-hour format.

## Runtime and dependencies

Docker Desktop with Docker Compose v2 must be running. Docker runs the application dependencies, so local Python and Node installations are optional.

| Component | Configuration |
| --- | --- |
| Backend | Python 3.12, FastAPI, Uvicorn |
| Database | PostgreSQL 16 |
| Frontend | Node 22, React 19, Vite 8 |
| Authentication | PyJWT and pwdlib with Argon2 |
| Model HTTP client | httpx |
| Registration email validation | email-validator |

Python dependencies are listed in `backend/requirements.txt`. Frontend dependency ranges are in `frontend/package.json`, with resolved versions in `frontend/package-lock.json`. Container image tags and Python dependencies are not pinned to exact patch versions.

## First-time setup

Clone this repository and open PowerShell in its root directory, containing `compose.yaml`.

For a new checkout, create the local configuration:

```powershell
Copy-Item .env.example .env
$authSecret = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
(Get-Content .env) -replace '^AUTH_SECRET=.*$', "AUTH_SECRET=$authSecret" | Set-Content -Encoding ascii .env
Remove-Variable authSecret
```

Keep the default `LLM_MODE=mock` to run without an LLM API key. The example database URL targets the Compose database service.

Start all services with one command:

```powershell
docker compose up --build
```

The startup command waits for database health, applies unapplied SQL migrations, seeds demo users/resources, and starts the API. Wait for the Uvicorn startup message before signing in or running tests. If the frontend starts earlier, refresh after the API is ready.

| Page | URL |
| --- | --- |
| Application | http://127.0.0.1:5173 |
| Interactive API documentation | http://127.0.0.1:8000/docs |
| API/database health | http://127.0.0.1:8000/health |

Keep the startup terminal open. Use a second PowerShell terminal in the repository root for test commands.

To check readiness:

```powershell
docker compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status)"
```

Expect `200`. To inspect a startup failure:

```powershell
docker compose ps -a
docker compose logs --tail 80 backend
```

## Accounts and resources

| Demo email | Demo password |
| --- | --- |
| alice@example.com | DemoAlice123! |
| bob@example.com | DemoBob123! |

These credentials are for local demonstration. You can also select the create-account button on the login page. Registration requires a valid email format, a password of 8–128 characters, and matching password confirmation. Duplicate emails are rejected. After registering, sign in with the new account.

Registration validates email syntax. Email ownership verification and password recovery are not implemented.

Seeded resources are the large meeting room (`ห้องประชุมใหญ่`), small meeting room (`ห้องประชุมเล็ก`), and projector (`โปรเจกเตอร์`). Seeding preserves existing demo accounts and resources.

## Booking workflow and design

- Select a resource, date, start time and end time, then submit the form.
- Bookings belong to authenticated users. Edit and cancel controls are available for eligible future bookings.
- The database has an exclusion constraint preventing overlapping active bookings for the same resource, including concurrent requests. Active statuses in this constraint are `requested` and `confirmed`. Adjacent time slots can meet at an endpoint.
- Cancellation keeps the booking history and changes its status to `cancelled`.
- Every resource shares the same opening hours, Monday–Friday, 09:00–18:00 Bangkok time. The start must be in the future, the end must follow the start, and both must fall on the same Bangkok date. Weekends, overnight slots and out-of-hours slots are rejected. There is no holiday calendar or per-resource schedule.
- A normal booking is created as `confirmed`. Assistant requests first create a pending action and create or change a booking only after confirmation. There is no automatic transition to `completed`; elapsed confirmed bookings remain in history and cannot be edited or cancelled.
- Pending actions do not hold a slot. Availability is enforced again when a booking is inserted or edited. An unconfirmed expired action is rejected. Confirmation locks the pending action row, and the booking change and confirmation marker are committed together.
- Edit and cancellation confirmations compare the current resource and time range against the draft's original values. If those values changed, confirmation is rejected and the user must prepare a new request.
- Assistant changes require a pending action followed by explicit user confirmation.
- Confirmation is checked on the backend. The tests cover ownership of pending confirmations and repeated confirmation returning the same booking ID.
- A shared form serves both rooms and equipment. Each resource represents one independently bookable item. Equipment quantities and pickup/return workflows are not implemented.
- The frontend stores the signed-in account and bearer token in React state. Refreshing the page requires signing in again. Tokens issued by the API expire after one hour.

## Assistant examples

Mock mode recognizes specific templates. Use ISO dates (`YYYY-MM-DD`) and 24-hour times (`HH:mm`) for the templates below. Choose a future date and an available slot when testing actual bookings. The sample dates below are illustrative.

Create a booking:

```text
จองโปรเจกเตอร์ วันที่ 2026-11-23 เวลา 09:00 ถึง 10:00
Book the projector on 2026-11-23 from 09:00 to 10:00.
```

Check availability:

```text
โปรเจกเตอร์ วันที่ 2026-11-23 เวลา 09:00 ถึง 10:00 ว่างไหม
Is the projector free on 2026-11-23 from 09:00 to 10:00?
```

Edit a booking, replacing `53` with your own active booking ID:

```text
แก้ไขการจองเลขที่ 53 เป็นห้องประชุมเล็ก วันที่ 2026-11-23 เวลา 13:00 ถึง 14:00
Change booking number 53 to the small meeting room on 2026-11-23 from 13:00 to 14:00.
```

Cancel a booking:

```text
ยกเลิกการจองเลขที่ 53
Cancel booking number 53.
```

Supported English resource names include `big meeting room`, `large meeting room`, `small meeting room` and `projector`. Incomplete or unsupported Mock requests return no tool call and prompt the user for details.

The offline Mock uses regular expressions and a small set of legacy fixtures. OpenAI mode sends redacted text to the Responses API with backend tool definitions for availability, preparation of bookings, edits and cancellations. Backend endpoints execute those actions. The frontend communicates with the application API.

## OpenAI configuration

Edit your local `.env`:

```dotenv
LLM_MODE=openai
LLM_API_KEY=YOUR_API_KEY
LLM_MODEL=gpt-4.1-mini
```

Use a model available to your API account. Apply configuration changes with:

```powershell
docker compose up -d --build backend
```

The key stays in the backend environment. Keep `.env` out of Git.

The model request has a 15-second HTTP timeout. Request/network failures and unsuccessful provider responses produce a service-unavailable message directing users to the form. Incomplete or malformed provider output is rejected. Manual booking remains independently available.

Live OpenAI operation remains unverified after the API account returned insufficient-credit errors.

## Guardrails and logging

The model client calls `redact_for_llm` before sending the user text. Its instructions treat that text as untrusted input, require explicit booking details, and ask for no tool call for incomplete or unrelated requests. It accepts at most one supported function call per response.

The client logs the serialized model request and the provider response body to the backend application log. Provider responses may contain user-related content. The output logging has no additional redaction in `llm_client.py`.

Model instructions and pattern-based masking have limits. They cannot guarantee detection of every prompt injection or every personal-data format. An instruction to the model is insufficient to enforce booking ownership, availability or confirmation, so those checks belong in backend booking operations.

The reviewed redaction rules cover email addresses, Thai 13-digit ID-like strings (including spaces or hyphens), common Thai mobile/landline formats, OpenAI-style and Google-style API keys, and long values labelled as API keys. Matching values are replaced with category markers before model input is constructed.

This is pattern matching. It may mask a harmless matching number and may miss obfuscated data, uncommon separators, non-Thai phone formats, other secret formats, or personal information such as names and addresses. It does not validate whether an ID belongs to anyone or verify email ownership. Prompt injection is addressed with instructions, a limited tool allowlist, validated arguments, authenticated endpoints and explicit confirmation. Model behavior under adversarial inputs has not been comprehensively evaluated.

## Automated backend tests

With the services running and the health check returning `200`:

```powershell
docker compose exec -T -w /app backend python -m unittest discover -s tests -p "test_booking_concurrency.py" -v
```

The latest observed run passed all three tests:

1. Concurrent requests for the same slot yield one successful booking and one conflict.
2. Only the pending action owner can confirm it, and repeating confirmation returns the same booking ID.
3. The normal booking API remains usable when the model HTTP request is mocked to time out.

The timeout test simulates the model failure and requires no LLM key. The tests use the running API/database and demo accounts. Their successful test bookings are cancelled during cleanup.

An additional six unit tests in `backend/tests/test_booking_rules.py` cover opening/closing boundaries, UTC conversion, weekends, invalid time ranges, overnight bookings and supported redaction examples. These six tests passed locally without a database or model key.

Run both test files after installing the final update:

```powershell
docker compose exec -T -w /app backend python -m unittest discover -s tests -p "test_booking*.py" -v
```

Expect nine tests. The combined run against the running application is still pending after the final update.

## Natural-language evaluation

With the backend running, execute the following commands from the project root in PowerShell. No LLM API key is required.

```powershell
docker compose cp .\evaluation\run_booking_eval.py backend:/tmp/run_booking_eval.py
docker compose exec -T -w /app -e PYTHONPATH=/app -e PYTHONIOENCODING=utf-8 backend python /tmp/run_booking_eval.py
```

The harness compares the tool name and arguments returned in Mock mode with the expected result for eight labeled requests. A result of `None` is expected for incomplete requests. The runner prints each mismatch and exits with code `1` when any case fails.

| Language | Passed | Total |
| --- | ---: | ---: |
| Thai | 4 | 4 |
| English | 4 | 4 |
| **Overall** | **8** | **8** |

No failures were observed in this run.

This evaluation checks tool selection and arguments on eight fixed
requests in Mock mode. Two cases are incomplete requests, for which
returning no tool call is the expected result.

The Mock uses predefined patterns. Passing these cases does not establish
accuracy on unseen wording or live LLM performance. Database availability,
booking conflicts, ownership, and confirmation are outside this harness's
scope. Live OpenAI evaluation remains pending due to insufficient API credit.

## Updating and stopping the application

After changing source files copied into a container image, rebuild the affected services:

```powershell
docker compose up -d --build backend frontend
```

To stop the local services:

```powershell
docker compose down
```

The database is stored in the named `booking-data` volume and persists across container recreation.

## Submission status and trade-offs

The selected additional feature is the repeatable evaluation harness.

Verified on a local Git clone:
- Backend tests passed, 9/9.
- Mock evaluation passed, 8/8.
- Frontend lint passed.
- Frontend production build passed.

Concurrent booking testing exposed a PostgreSQL deadlock. Resource locks
were changed to FOR NO KEY UPDATE to serialize writes for the same
resource. The combined backend tests passed after this fix.
This approach trades per-resource write concurrency for simpler locking.

The assistant's Mock mode supports predefined Thai and English templates.
Its evaluation score does not measure live model performance or accuracy
on arbitrary wording. Live OpenAI testing remains pending because the API
account had insufficient credit.