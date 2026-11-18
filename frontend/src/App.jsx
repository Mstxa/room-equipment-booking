import { useState } from "react";
import "./App.css";

const bookingStatuses = {
  requested: "รอการยืนยัน",
  confirmed: "ยืนยันแล้ว",
  cancelled: "ยกเลิกแล้ว",
  completed: "เสร็จสิ้น",
};

const minutes = Array.from({ length: 60 }, (_, index) =>
  String(index).padStart(2, "0"),
);
const hours = minutes.slice(0, 24);

const bookingTime = new Intl.DateTimeFormat("th-TH", {
  dateStyle: "medium",
  timeStyle: "short",
  hourCycle: "h23",
  timeZone: "Asia/Bangkok",
});

const tableDate = new Intl.DateTimeFormat("th-TH", {
  dateStyle: "medium",
  timeZone: "Asia/Bangkok",
});

const tableTime = new Intl.DateTimeFormat("th-TH", {
  timeStyle: "short",
  hourCycle: "h23",
  timeZone: "Asia/Bangkok",
});

function TimeSelect({ id, label, value, onChange }) {
  const [hour, minute = ""] = value.split(":");

  return (
    <div role="group" aria-labelledby={id}>
      <span className="time-label" id={id}>{label}</span>
      <div className="time-select">
        <select
          aria-label={`${label} ชั่วโมง`}
          value={hour}
          onChange={(event) => onChange(`${event.target.value}:${minute}`)}
          required
        >
          <option value="">ชม.</option>
          {hours.map((option) => <option key={option}>{option}</option>)}
        </select>
        <span aria-hidden="true">:</span>
        <select
          aria-label={`${label} นาที`}
          value={minute}
          onChange={(event) => onChange(`${hour}:${event.target.value}`)}
          required
        >
          <option value="">นาที</option>
          {minutes.map((option) => <option key={option}>{option}</option>)}
        </select>
      </div>
    </div>
  );
}

async function request(path, options) {
  const response = await fetch(`/api${path}`, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? "กรุณาตรวจสอบรูปแบบอีเมลและรหัสผ่านตามที่ระบุ"
          : "ส่งคำขอไม่สำเร็จ",
    );
  }

  return data;
}

function BookingAssistant({ token, saving, onConfirm }) {
  const [message, setMessage] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function askAssistant(event) {
    event.preventDefault();

    const text = message.trim();
    if (!text) return;

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const answer = await request("/ai/message", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: text }),
      });
      setResult(answer);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function confirmDraft() {
    if (loading || saving || result?.kind !== "pending_confirmation") return;

    setLoading(true);
    setError("");

    try {
      const confirmed = await onConfirm(result.action_id);
      setResult(confirmed);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel assistant" aria-labelledby="assistant-title">
      <h2 id="assistant-title">ผู้ช่วยจองด้วยข้อความ</h2>
      <p className="muted">โหมดเดโม (Mock) รองรับประโยคตัวอย่างสำหรับทดสอบ</p>

      <form onSubmit={askAssistant}>
        <label htmlFor="assistant-message">พิมพ์คำขอของคุณ</label>
        <p>
          <textarea
            id="assistant-message"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            rows={5}
            placeholder="ระบุห้อง วันที่ และช่วงเวลา หรือเลขรายการที่ต้องการแก้ไขหรือยกเลิก"
            maxLength={1000}
            disabled={loading}
            required
          />
        </p>
        <button type="submit" disabled={loading || !message.trim()}>
          {loading ? "กำลังประมวลผล…" : "ส่งคำขอ"}
        </button>
      </form>

      {error && <p role="alert">{error}</p>}
      {result?.kind === "clarification" && <p role="status">{result.message}</p>}
      {result?.kind === "availability" && (
        <p role="status">
          <strong>{result.resource_name}</strong>
          {" · "}
          {bookingTime.formatRange(
            new Date(result.start_at),
            new Date(result.end_at),
          )}
          {" · "}
          <strong>{result.available ? "ว่าง" : "ไม่ว่าง"}</strong>
        </p>
      )}
      {result?.kind === "pending_confirmation" && (
        <div className="confirmation">
          <p>
            <strong>
              {result.action_type === "edit"
                ? `รอยืนยันการแก้ไขเลขที่ ${result.booking_id}`
                : result.action_type === "cancel"
                  ? `รอยืนยันการยกเลิกเลขที่ ${result.booking_id}`
                  : "รอยืนยันการจอง"}
            </strong>
          </p>

          {result.action_type === "edit" && (
            <p>
              เดิม · {result.original_resource_name}
              {" · "}
              {bookingTime.formatRange(
                new Date(result.original_start_at),
                new Date(result.original_end_at),
              )}
            </p>
          )}

          <p>
            {result.action_type === "edit" && "ใหม่ · "}
            {result.resource_name}
            {" · "}
            {bookingTime.formatRange(
              new Date(result.start_at),
              new Date(result.end_at),
            )}
          </p>

          <button
            type="button"
            onClick={confirmDraft}
            disabled={loading || saving}
          >
            {loading
              ? "กำลังยืนยัน…"
              : result.action_type === "edit"
                ? "ยืนยันการแก้ไข"
                : result.action_type === "cancel"
                  ? "ยืนยันการยกเลิก"
                  : "ยืนยันการจองผ่านข้อความ"}
          </button>
        </div>
      )}

      {result?.kind === "confirmed" && (
        <p role="status">
          {result.action_type === "edit"
            ? "แก้ไขสำเร็จ"
            : result.action_type === "cancel"
              ? "ยกเลิกสำเร็จ"
              : "จองสำเร็จ"}
          {" เลขรายการ "}
          {result.booking_id}
          {result.refreshFailed &&
            " · โหลดรายการจองไม่สำเร็จ กรุณาออกจากระบบแล้วเข้าใหม่เพื่อดูรายการ"}
        </p>
      )}
    </section>
  );
}

export default function App() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [registering, setRegistering] = useState(false);
  const [confirmPassword, setConfirmPassword] = useState("");
  const [authNotice, setAuthNotice] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [account, setAccount] = useState(null);
  const [bookings, setBookings] = useState([]);
  const [resources, setResources] = useState([]);
  const [resourceId, setResourceId] = useState("");
  const [date, setDate] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [bookingError, setBookingError] = useState("");
  const [bookingNotice, setBookingNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function switchAuthMode() {
    setRegistering((current) => !current);
    setPassword("");
    setConfirmPassword("");
    setShowPassword(false);
    setError("");
    setAuthNotice("");
  }

  async function register(event) {
    event.preventDefault();
    setError("");
    setAuthNotice("");
    if (password !== confirmPassword) {
      setError("รหัสผ่านทั้งสองช่องไม่ตรงกัน");
      return;
    }

    setLoading(true);
    try {
      const user = await request("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          confirm_password: confirmPassword,
        }),
      });
      setEmail(user.email);
      setRegistering(false);
      setPassword("");
      setConfirmPassword("");
      setShowPassword(false);
      setAuthNotice("สร้างบัญชีสำเร็จ กรุณาเข้าสู่ระบบด้วยรหัสผ่านที่ตั้งไว้");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function login(event) {
    event.preventDefault();
    setError("");
    setAuthNotice("");
    setLoading(true);

    try {
      const { access_token } = await request("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const headers = { Authorization: `Bearer ${access_token}` };
            const [user, items, resourceList] = await Promise.all([
        request("/auth/me", { headers }),
        request("/bookings", { headers }),
        request("/resources"),
      ]);

      setAccount({ ...user, token: access_token });
      setBookings(items);
      setResources(resourceList);
      setResourceId("");
      setEditingId(null);
      setDate("");
      setStartTime("");
      setEndTime("");
      setBookingError("");
      setBookingNotice("");
      setPassword("");
      setShowPassword(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function resetBookingForm() {
    setEditingId(null);
    setResourceId("");
    setDate("");
    setStartTime("");
    setEndTime("");
    setBookingError("");
    setBookingNotice("");
  }

  function startBookingEdit(booking) {
    // The form accepts Bangkok time (UTC+7).
    const start = new Date(Date.parse(booking.start_at) + 7 * 60 * 60 * 1000)
      .toISOString();
    const end = new Date(Date.parse(booking.end_at) + 7 * 60 * 60 * 1000)
      .toISOString();

    setEditingId(booking.id);
    setResourceId(String(booking.resource_id));
    setDate(start.slice(0, 10));
    setStartTime(start.slice(11, 16));
    setEndTime(end.slice(11, 16));
    setBookingError("");
    setBookingNotice("");
  }

  async function submitBooking(event) {
    event.preventDefault();
    setBookingError("");
    setBookingNotice("");

    if (startTime >= endTime) {
      setBookingError("เวลาสิ้นสุดต้องอยู่หลังเวลาเริ่ม");
      return;
    }

    const isEditing = editingId !== null;
    setSaving(true);

    try {
      const saved = await request(
        isEditing ? `/bookings/${editingId}` : "/bookings",
        {
          method: isEditing ? "PATCH" : "POST",
          headers: {
            Authorization: `Bearer ${account.token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            resource_id: Number(resourceId),
            start_at: `${date}T${startTime}:00+07:00`,
            end_at: `${date}T${endTime}:00+07:00`,
          }),
        },
      );

      const resource = resources.find((item) => item.id === saved.resource_id);
      const updated = { ...saved, resource_name: resource?.name ?? "ทรัพยากร" };

      setBookings((items) =>
        [...items.filter((item) => item.id !== saved.id), updated].sort(
          (first, second) =>
            new Date(first.start_at) - new Date(second.start_at) ||
            first.id - second.id,
        ),
      );

      resetBookingForm();
      setBookingNotice(
        `${isEditing ? "แก้ไขสำเร็จ" : "จองสำเร็จ"} เลขรายการ ${saved.id}`,
      );
    } catch (err) {
      setBookingError(
        err.message === "This resource is already booked during the requested time"
          ? "ห้องหรืออุปกรณ์นี้ถูกจองในช่วงเวลาที่เลือกแล้ว"
          : err.message,
      );
    } finally {
      setSaving(false);
    }
  }

  async function cancelBooking(booking) {
    const confirmed = window.confirm(
      `ยืนยันยกเลิกการจอง ${booking.resource_name} เลขรายการ ${booking.id} หรือไม่?`,
    );
    if (!confirmed) return;

    setBookingError("");
    setBookingNotice("");
    setSaving(true);

    try {
      const cancelled = await request(`/bookings/${booking.id}/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${account.token}` },
      });

      setBookings((items) =>
        items.map((item) =>
          item.id === cancelled.id ? { ...item, ...cancelled } : item,
        ),
      );

      if (editingId === cancelled.id) resetBookingForm();
      setBookingNotice(`ยกเลิกสำเร็จ เลขรายการ ${cancelled.id}`);
    } catch (err) {
      setBookingError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function confirmAssistantBooking(actionId) {
    setSaving(true);

    const headers = { Authorization: `Bearer ${account.token}` };

    try {
      const confirmed = await request(`/ai/confirm/${actionId}`, {
        method: "POST",
        headers,
      });

      try {
        const items = await request("/bookings", { headers });
        setBookings(items);
        return confirmed;
      } catch {
        return { ...confirmed, refreshFailed: true };
      }
    } finally {
      setSaving(false);
    }
  }

  function logout() {
    setAccount(null);
    setBookings([]);
    setEmail("");
    setPassword("");
    setShowPassword(false);
    setError("");
  }

  return (
    <main className={account ? "workspace" : "login-page"} lang="th">
      {account ? (
        <>
          <header className="workspace-header">
            <h1>ระบบจองห้องและอุปกรณ์</h1>
            <div className="account-controls">
              <span>{account.email}</span>
              <button className="secondary" type="button" onClick={logout} disabled={saving}>
                ออกจากระบบ
              </button>
            </div>
          </header>

          <div className="booking-grid">
            <form className="panel booking-form" onSubmit={submitBooking}>
              <h2>
                {editingId === null
                  ? "จองห้องหรืออุปกรณ์"
                  : `แก้ไขการจองเลขที่ ${editingId}`}
              </h2>

              <fieldset disabled={saving}>
                <legend>เวลาไทย (UTC+7) · รูปแบบ 24 ชั่วโมง เช่น 14:30</legend>

                <p>
                  <label>
                    ห้องหรืออุปกรณ์
                    <select
                      value={resourceId}
                      onChange={(event) => setResourceId(event.target.value)}
                      required
                    >
                      <option value="">เลือกห้องหรืออุปกรณ์</option>
                      {resources.map((resource) => (
                        <option key={resource.id} value={resource.id}>
                          {resource.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </p>

                <p>
                  <label>
                    วันที่
                    <input
                      type="date"
                      value={date}
                      onChange={(event) => setDate(event.target.value)}
                      required
                    />
                  </label>
                </p>

                <TimeSelect
                  id="booking-start"
                  label="เวลาเริ่ม"
                  value={startTime}
                  onChange={setStartTime}
                />

                <TimeSelect
                  id="booking-end"
                  label="เวลาสิ้นสุด"
                  value={endTime}
                  onChange={setEndTime}
                />

                <div className="form-actions">
                  <button type="submit" disabled={resources.length === 0}>
                    {saving
                      ? "กำลังบันทึก…"
                      : editingId === null
                        ? "ยืนยันการจอง"
                        : "บันทึกการแก้ไข"}
                  </button>
                  {editingId !== null && (
                    <button className="secondary" type="button" onClick={resetBookingForm}>
                      กลับไปจองใหม่
                    </button>
                  )}
                </div>
              </fieldset>

              {bookingError && <p role="alert">{bookingError}</p>}
              {bookingNotice && <p role="status">{bookingNotice}</p>}
            </form>

            <BookingAssistant
              token={account.token}
              saving={saving}
              onConfirm={confirmAssistantBooking}
            />
          </div>

          <section className="panel bookings" aria-labelledby="bookings-title">
            <h2 id="bookings-title">รายการจองของฉัน</h2>
            {bookings.length === 0 ? (
              <p className="empty">ยังไม่มีรายการจอง</p>
            ) : (
              <div className="booking-table-scroll" role="region" aria-labelledby="bookings-title" tabIndex={0}>
                <table className="booking-table" aria-labelledby="bookings-title">
                  <thead>
                    <tr>
                      <th scope="col">เลขรายการ</th>
                      <th scope="col">ห้องหรืออุปกรณ์</th>
                      <th scope="col">วันที่</th>
                      <th scope="col">เวลา (UTC+7)</th>
                      <th scope="col">สถานะ</th>
                      <th scope="col">จัดการ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bookings.map((booking) => (
                      <tr key={booking.id}>
                        <td className="booking-id">{booking.id}</td>
                        <th scope="row">{booking.resource_name}</th>
                        <td>
                          {tableDate.formatRange(
                            new Date(booking.start_at),
                            new Date(booking.end_at),
                          )}
                        </td>
                        <td className="booking-slot-time">
                          {tableTime.format(new Date(booking.start_at))}
                          {"–"}
                          {tableTime.format(new Date(booking.end_at))}
                        </td>
                        <td>
                          <span className="status" data-status={booking.status}>
                            {bookingStatuses[booking.status] ?? booking.status}
                          </span>
                        </td>
                        <td>
                          <div className="booking-actions">
                            {["requested", "confirmed"].includes(booking.status) &&
                              new Date(booking.start_at).getTime() > Date.now() && (
                                <>
                                  <button
                                    type="button"
                                    disabled={saving}
                                    className="secondary"
                                    onClick={() => startBookingEdit(booking)}
                                  >
                                    แก้ไข
                                  </button>
                                  <button
                                    type="button"
                                    disabled={saving}
                                    className="danger"
                                    onClick={() => cancelBooking(booking)}
                                  >
                                    ยกเลิก
                                  </button>
                                </>
                              )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : (
        <form className="panel login-card" onSubmit={registering ? register : login}>
          <div className="calendar-mark" aria-hidden="true" />
          <h1>ระบบจองห้องและอุปกรณ์</h1>
          <p className="muted login-intro">
            {registering ? "สร้างบัญชีเพื่อเริ่มจองห้องหรืออุปกรณ์" : "เข้าสู่ระบบเพื่อจองห้องหรืออุปกรณ์"}
          </p>
          <p>
            <label>
              อีเมล
              <input
                type="email"
                placeholder="name@example.com"
                maxLength={254}
                disabled={loading}
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
          </p>
          <div className="password-field">
            <label htmlFor="login-password">รหัสผ่าน</label>
            <div className="password-control">
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                autoComplete={registering ? "new-password" : "current-password"}
                minLength={registering ? 8 : undefined}
                maxLength={128}
                disabled={loading}
                aria-describedby={registering ? "password-help" : undefined}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              <button
                className="password-toggle"
                type="button"
                aria-controls="login-password"
                aria-label={showPassword ? "ซ่อนรหัสผ่าน" : "แสดงรหัสผ่าน"}
                onClick={() => setShowPassword((visible) => !visible)}
              >
                {showPassword ? "ซ่อน" : "แสดง"}
              </button>
            </div>
          </div>
          {registering && (
            <>
              <p className="muted password-help" id="password-help">
                รหัสผ่านต้องมีความยาว 8–128 ตัวอักษร
              </p>
              <div className="password-field">
                <label htmlFor="confirm-password">ยืนยันรหัสผ่าน</label>
                <input
                  id="confirm-password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={128}
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  disabled={loading}
                  required
                />
              </div>
            </>
          )}
          <button type="submit" disabled={loading}>
            {loading
              ? "กำลังดำเนินการ…"
              : registering ? "สร้างบัญชี" : "เข้าสู่ระบบ"}
          </button>
          <button className="secondary auth-switch" type="button" onClick={switchAuthMode} disabled={loading}>
            {registering ? "มีบัญชีแล้ว เข้าสู่ระบบ" : "ยังไม่มีบัญชี สร้างบัญชีใหม่"}
          </button>
          {authNotice && <p role="status">{authNotice}</p>}
          {error && <p role="alert">{error}</p>}
        </form>
      )}
    </main>
  );
}
