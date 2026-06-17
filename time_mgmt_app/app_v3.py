import streamlit as st
from datetime import datetime, timedelta
import random
import time
import json
import csv
import io
import os
import smtplib
from email.message import EmailMessage
from zoneinfo import ZoneInfo          # stdlib, Python >= 3.9

st.set_page_config(
    page_title="Workday Tracker",
    page_icon="⏱️",
    layout="centered",
)

TZ = ZoneInfo("Europe/Zurich")         # CET in winter, CEST in summer, auto
BACKUP_FILE = "workday_backup.json"     # local safety net
WORKDAY = timedelta(hours=8)
LABELS = ["Meeting", "Jira", "Training", "Other"]

# ─── THEME ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Share+Tech+Mono&family=Barlow:ital,wght@0,400;0,600;1,400&display=swap');

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background-color: #0e0e0e !important;
    color: #e8dcc8 !important;
}
[data-testid="stHeader"]            { background: transparent !important; }
[data-testid="stSidebar"]           { background: #111 !important; }
section.main > div                  { padding-top: 1.5rem; }

h1 {
    font-family: 'Bebas Neue', sans-serif !important;
    color: #f5c518 !important;
    font-size: 3rem !important;
    letter-spacing: 4px;
    text-align: center;
    text-shadow: 0 0 30px rgba(245,197,24,0.3);
    margin-bottom: 0 !important;
}
h3 {
    font-family: 'Bebas Neue', sans-serif !important;
    color: #f5c518 !important;
    letter-spacing: 2px;
    font-size: 1.4rem !important;
}
p, label, div { font-family: 'Barlow', sans-serif !important; }

input[type="text"], textarea, [data-baseweb="select"] > div {
    background-color: #1a1a1a !important;
    color: #e8dcc8 !important;
    border: 1px solid #333 !important;
    border-radius: 4px !important;
    font-family: 'Share Tech Mono', monospace !important;
    caret-color: #f5c518;
}
input[type="text"]:focus, textarea:focus {
    border-color: #f5c518 !important;
    box-shadow: 0 0 0 2px rgba(245,197,24,0.15) !important;
}
label {
    color: #aaa !important;
    font-size: 0.85rem !important;
    letter-spacing: 1px;
    text-transform: uppercase;
}

[data-testid="stMetricValue"] {
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 1.8rem !important;
    color: #f5c518 !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.75rem !important;
    color: #777 !important;
    text-transform: uppercase;
    letter-spacing: 1px;
}
[data-testid="stMetricDelta"] { font-size: 0.8rem !important; }
[data-testid="metric-container"] {
    background: #161616;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 12px 16px !important;
}

.stButton > button {
    background: #161616 !important;
    color: #f5c518 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 6px !important;
    font-family: 'Barlow', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px;
    transition: all .2s ease;
}
.stButton > button:hover {
    border-color: #f5c518 !important;
    box-shadow: 0 0 10px rgba(245,197,24,0.25) !important;
}

hr {
    border: none !important;
    border-top: 1px solid #2a2a2a !important;
    margin: 1.2rem 0 !important;
}

[data-testid="stAlert"] {
    background: #161616 !important;
    border-left: 4px solid #f5c518 !important;
    color: #e8dcc8 !important;
}

.live-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 20px;
    padding: 3px 12px; font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem; color: #555; float: right; margin-top: -2px;
}
.live-dot {
    width: 7px; height: 7px; background: #2ecc71; border-radius: 50%;
    display: inline-block; box-shadow: 0 0 6px #2ecc7188;
}
.big-clock {
    font-family: 'Share Tech Mono', monospace; font-size: 3.2rem;
    color: #f5c518; letter-spacing: 4px; text-align: center;
    text-shadow: 0 0 20px rgba(245,197,24,0.25);
}
</style>
""", unsafe_allow_html=True)

# ─── MOTIVATIONAL MESSAGES ──────────────────────────────────────────────────

ENTRY_MSG = [
    "You're here and ready. Let's make today count, one focused block at a time.",
    "Fresh start, clear goals. Steady focus beats frantic effort, so let's pace it well.",
    "Welcome in. Small consistent wins add up to a strong day. Let's begin.",
    "Good to see you. Plan the work, work the plan, and the day takes care of itself.",
    "Showing up is half the battle, and you've already done it. Let's build momentum.",
]

LUNCH_START_MSG = [
    "Well earned. Step away, recharge, and you'll come back sharper.",
    "A real break makes the afternoon stronger. Enjoy your lunch.",
    "Rest is part of the work. Take the time, you've earned it.",
    "Good moment to reset. Eat well and give your focus a chance to recover.",
]

AFTER_LUNCH_MSG = [
    "Refueled and ready. The afternoon is yours to finish strong.",
    "Back at it. A clear head now turns into a clean finish later.",
    "Second half starts now. Pick one priority and give it your best.",
    "Nicely recharged. Let's close the day with intention.",
]

FINAL_MSG = [
    "Full day complete. You showed up and delivered. Time to rest and recharge.",
    "That's a solid day's work. Log off with a clear conscience.",
    "Hours done and goals met. Switch off and enjoy your evening.",
    "Strong finish. Recovery is what makes tomorrow's effort possible, so go relax.",
]

SHORT_MSG = [
    "A little short today, and that's okay. Note it, adjust tomorrow, keep moving forward.",
    "Not quite full hours, but progress is progress. You can balance it out tomorrow.",
    "Slightly under target. No drama, just a small gap to close when it suits you.",
    "Honest tracking beats a perfect number. Make it up when you can and stay steady.",
]

TIMER_START_MSG = [
    "Timer running. Protect this block and give it your full attention.",
    "You're on the clock for this one. Single task, single focus.",
    "Locked in. Deep work happens in moments exactly like this.",
    "Tracking now. Quiet focus, one task, real progress.",
]

REGISTER_MSG = [
    "Logged. Another honest block captured, nicely done.",
    "Saved. Your record just got a little more accurate.",
    "Registered. Small entries like this build a trustworthy timesheet.",
    "Captured. That's real, visible progress on the board.",
]

# ─── PERSISTENCE (LOCAL BACKUP) ─────────────────────────────────────────────

def load_state():
    try:
        if os.path.exists(BACKUP_FILE):
            with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"activities": [], "active": None}


def save_state():
    try:
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "activities": st.session_state.activities,
                    "active": st.session_state.active,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception:
        # Never crash on a backup write. The download and email paths remain.
        pass


if "loaded" not in st.session_state:
    data = load_state()
    st.session_state.activities = data.get("activities", [])
    st.session_state.active = data.get("active", None)
    st.session_state.loaded = True
    st.session_state.confirm = None     # holds a pending confirmation key

# ─── TIMER HELPERS ──────────────────────────────────────────────────────────

def real_now() -> datetime:
    return datetime.now(TZ)


def active_elapsed() -> float:
    """Seconds elapsed on the active timer, running or paused."""
    a = st.session_state.active
    if not a:
        return 0.0
    secs = float(a.get("accumulated", 0.0))
    if a.get("running") and a.get("resumed_at"):
        secs += (real_now() - datetime.fromisoformat(a["resumed_at"])).total_seconds()
    return max(secs, 0.0)


def fmt_clock(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def fmt_hm(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m"


def start_activity(label: str, description: str):
    st.session_state.active = {
        "label": label,
        "description": description.strip(),
        "accumulated": 0.0,
        "running": True,
        "resumed_at": real_now().isoformat(),
        "created_at": real_now().isoformat(),
    }
    save_state()


def pause_activity():
    a = st.session_state.active
    if a and a.get("running") and a.get("resumed_at"):
        a["accumulated"] = float(a.get("accumulated", 0.0)) + (
            real_now() - datetime.fromisoformat(a["resumed_at"])
        ).total_seconds()
        a["running"] = False
        a["resumed_at"] = None
        save_state()


def resume_activity():
    a = st.session_state.active
    if a and not a.get("running"):
        a["resumed_at"] = real_now().isoformat()
        a["running"] = True
        save_state()


def register_activity():
    a = st.session_state.active
    if not a:
        return
    duration = active_elapsed()
    start_dt = datetime.fromisoformat(a["created_at"])
    end_dt = real_now()
    st.session_state.activities.append({
        "date": start_dt.strftime("%Y-%m-%d"),
        "label": a["label"],
        "description": a["description"],
        "start": start_dt.strftime("%H:%M"),
        "end": end_dt.strftime("%H:%M"),
        "duration_seconds": int(duration),
    })
    st.session_state.active = None
    save_state()


def discard_activity():
    st.session_state.active = None
    save_state()


def delete_entry(idx: int):
    if 0 <= idx < len(st.session_state.activities):
        st.session_state.activities.pop(idx)
        save_state()


def clear_log():
    st.session_state.activities = []
    save_state()

# ─── EXPORT HELPERS ─────────────────────────────────────────────────────────

def build_summary_text() -> str:
    acts = st.session_state.activities
    if not acts:
        return "No activities registered yet."
    by_date = {}
    for a in acts:
        by_date.setdefault(a["date"], []).append(a)

    lines = ["WORKDAY ACTIVITY LOG", ""]
    grand_total = 0
    for date in sorted(by_date):
        day = by_date[date]
        lines.append(f"Date: {date}")
        totals = {}
        day_total = 0
        for a in day:
            totals[a["label"]] = totals.get(a["label"], 0) + a["duration_seconds"]
            day_total += a["duration_seconds"]
        for label in sorted(totals):
            lines.append(f"  {label}: {fmt_hm(totals[label])}")
        lines.append(f"  Total tracked: {fmt_hm(day_total)}")
        lines.append("")
        lines.append("  Entries:")
        for a in day:
            desc = f" ({a['description']})" if a["description"] else ""
            lines.append(
                f"    {a['start']} to {a['end']}  {a['label']}{desc}: {fmt_hm(a['duration_seconds'])}"
            )
        lines.append("")
        grand_total += day_total

    if len(by_date) > 1:
        lines.append(f"GRAND TOTAL: {fmt_hm(grand_total)}")
    return "\n".join(lines).rstrip()


def build_csv_bytes() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "label", "description", "start", "end",
                     "duration_hms", "duration_minutes"])
    for a in st.session_state.activities:
        writer.writerow([
            a["date"], a["label"], a["description"], a["start"], a["end"],
            fmt_hm(a["duration_seconds"]),
            round(a["duration_seconds"] / 60, 1),
        ])
    return buf.getvalue().encode("utf-8")


def email_configured() -> bool:
    try:
        return "email" in st.secrets
    except Exception:
        return False


def send_backup_email() -> tuple[bool, str]:
    if not email_configured():
        return False, "Email is not configured. See the setup note below."
    try:
        cfg = st.secrets["email"]
        msg = EmailMessage()
        msg["Subject"] = f"Workday backup {real_now().strftime('%Y-%m-%d %H:%M')}"
        msg["From"] = cfg["sender"]
        msg["To"] = cfg["recipient"]
        msg.set_content(build_summary_text())
        msg.add_attachment(
            build_csv_bytes(),
            maintype="text",
            subtype="csv",
            filename=f"workday_{real_now().strftime('%Y%m%d_%H%M')}.csv",
        )
        with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as server:
            server.starttls()
            server.login(cfg["sender"], cfg["password"])
            server.send_message(msg)
        return True, f"Backup sent to {cfg['recipient']}."
    except Exception as e:
        return False, f"Email failed: {e}"

# ─── CALCULATOR HELPERS (original, cleaned) ─────────────────────────────────

def get_now() -> datetime:
    n = datetime.now(TZ)
    return n.replace(tzinfo=None, year=1900, month=1, day=1)


def parse_time(raw: str):
    if not raw or not raw.strip():
        return None
    s = raw.strip().upper()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p",
                "%I:%M%p", "%H.%M.%S", "%H.%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def fmt_td(td: timedelta) -> str:
    total = abs(int(td.total_seconds()))
    h, rem = divmod(total, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m"


def pct_color(p: float) -> str:
    if p >= 1.0:
        return "#2ecc71"
    if p >= 0.6:
        return "#f5c518"
    return "#e67e22"

# ─── UI COMPONENTS ──────────────────────────────────────────────────────────

def live_stamp(now: datetime):
    st.markdown(
        f'<div class="live-badge"><span class="live-dot"></span>'
        f'LIVE &nbsp;&middot;&nbsp; {now.strftime("%H:%M:%S")} CET</div>',
        unsafe_allow_html=True,
    )


def progress_bar(pct: float, label: str):
    p = min(max(pct, 0), 1)
    color = pct_color(p)
    st.markdown(f"""
<div style="margin:12px 0 4px 0">
  <div style="background:#222;border-radius:6px;overflow:hidden;height:16px">
    <div style="width:{p*100:.1f}%;background:{color};height:100%;
    border-radius:6px;transition:width .4s ease;
    box-shadow:0 0 8px {color}88"></div>
  </div>
  <div style="color:#777;font-size:0.8rem;margin-top:4px;font-family:'Share Tech Mono',monospace">
    {label}
  </div>
</div>""", unsafe_allow_html=True)


def result_card(html: str, accent: str = "#f5c518"):
    st.markdown(f"""
<div style="background:#161616;border-left:4px solid {accent};
border-radius:0 8px 8px 0;padding:14px 18px;margin:8px 0;
font-family:'Barlow',sans-serif;font-size:1.05rem;line-height:1.6">
{html}
</div>""", unsafe_allow_html=True)


def coach_says(msg: str):
    st.markdown(f"""
<div style="border-left:3px solid #f5c51844;padding:8px 16px;margin:14px 0 6px 0;
color:#b9ad97;font-style:italic;font-family:'Barlow',sans-serif;font-size:0.95rem">
&#128161; &nbsp;{msg}
</div>""", unsafe_allow_html=True)


def time_badge(label: str, t: datetime, color: str = "#f5c518"):
    st.markdown(f"""
<div style="display:inline-block;background:#1a1a1a;border:1px solid {color};
border-radius:6px;padding:8px 16px;margin:4px 6px 4px 0;text-align:center;min-width:160px">
  <div style="color:#888;font-size:0.7rem;letter-spacing:1px;text-transform:uppercase;
  font-family:'Barlow',sans-serif">{label}</div>
  <div style="color:{color};font-family:'Bebas Neue',sans-serif;font-size:1.6rem;
  letter-spacing:2px">{t.strftime('%H:%M')}</div>
</div>""", unsafe_allow_html=True)

# ─── ACTIVITY TIMER SECTION ─────────────────────────────────────────────────

def render_timer():
    st.markdown("### ⏱️ Activity Timer")

    a = st.session_state.active

    # ── No active timer: start a new one ──
    if not a:
        coach_says(random.choice(TIMER_START_MSG))
        c1, c2 = st.columns([1, 2])
        with c1:
            label = st.selectbox("Label", LABELS, key="new_label")
        with c2:
            custom = ""
            if label == "Other":
                custom = st.text_input("Custom label", key="new_custom",
                                       placeholder="e.g. Code review")
        desc = st.text_input("Description (optional, but always available)",
                             key="new_desc", placeholder="What are you working on?")
        final_label = custom.strip() if (label == "Other" and custom.strip()) else label
        if st.button("▶  Start timer", use_container_width=True):
            if label == "Other" and not custom.strip() and not desc.strip():
                st.warning("Add a custom label or a description so this block is identifiable.")
            else:
                start_activity(final_label, desc)
                st.rerun()
        return

    # ── Active timer present ──
    elapsed = active_elapsed()
    running = a.get("running")
    status_color = "#2ecc71" if running else "#e67e22"
    status_text = "RUNNING" if running else "PAUSED"

    desc = f" &mdash; {a['description']}" if a["description"] else ""
    st.markdown(f"""
<div style="background:#161616;border:1px solid {status_color}55;border-radius:10px;
padding:18px;margin:6px 0 12px 0">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div style="color:#f5c518;font-family:'Bebas Neue',sans-serif;font-size:1.4rem;
    letter-spacing:2px">{a['label']}</div>
    <div style="color:{status_color};font-family:'Share Tech Mono',monospace;
    font-size:0.8rem;letter-spacing:2px">{status_text}</div>
  </div>
  <div style="color:#8a8170;font-size:0.9rem;margin-top:2px">{a['description'] or 'No description'}</div>
  <div class="big-clock" style="margin-top:10px">{fmt_clock(elapsed)}</div>
</div>""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        if running:
            if st.button("⏸  Pause", use_container_width=True):
                pause_activity()
                st.rerun()
        else:
            if st.button("▶  Resume", use_container_width=True):
                resume_activity()
                st.rerun()
    with c2:
        if st.button("✅  Register", use_container_width=True):
            st.session_state.confirm = "register"
            st.rerun()
    with c3:
        if st.button("🗑  Discard", use_container_width=True):
            st.session_state.confirm = "discard"
            st.rerun()

    # ── Confirmations ──
    if st.session_state.confirm == "register":
        st.warning(f"Are you sure you want to register this task?  "
                   f"**{a['label']}** at **{fmt_hm(elapsed)}**.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("Yes, register it", use_container_width=True):
                register_activity()
                st.session_state.confirm = None
                st.rerun()
        with cc2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.confirm = None
                st.rerun()

    if st.session_state.confirm == "discard":
        st.warning("Discard this timer without registering it? This cannot be undone.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("Yes, discard", use_container_width=True):
                discard_activity()
                st.session_state.confirm = None
                st.rerun()
        with cc2:
            if st.button("Keep it", use_container_width=True):
                st.session_state.confirm = None
                st.rerun()

    st.caption("To switch tasks, register or discard this one, then start the next.")

# ─── REGISTERED LOG SECTION ─────────────────────────────────────────────────

def render_log():
    acts = st.session_state.activities
    st.markdown("### 📋 Registered Activities")

    if not acts:
        st.markdown(
            "<div style='color:#666;font-style:italic;padding:6px 0'>"
            "Nothing registered yet. Start a timer above, and your blocks land here."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    coach_says(random.choice(REGISTER_MSG))

    # Totals by label (current run, all dates combined)
    totals = {}
    grand = 0
    for a in acts:
        totals[a["label"]] = totals.get(a["label"], 0) + a["duration_seconds"]
        grand += a["duration_seconds"]

    cols = st.columns(max(len(totals), 1))
    for col, (label, secs) in zip(cols, sorted(totals.items())):
        with col:
            st.metric(label, fmt_hm(secs))

    st.markdown("")
    result_card(f"⏱️ Total tracked: <strong>{fmt_hm(grand)}</strong> "
                f"across <strong>{len(acts)}</strong> registered "
                f"{'block' if len(acts) == 1 else 'blocks'}.", "#2ecc71")

    # Entry rows
    for i, a in enumerate(acts):
        desc = f" &middot; {a['description']}" if a["description"] else ""
        r1, r2 = st.columns([6, 1])
        with r1:
            st.markdown(f"""
<div style="background:#161616;border:1px solid #2a2a2a;border-radius:6px;
padding:8px 14px;margin:3px 0;font-family:'Barlow',sans-serif">
  <span style="color:#f5c518;font-weight:600">{a['label']}</span>
  <span style="color:#8a8170">{desc}</span>
  <span style="float:right;color:#e8dcc8;font-family:'Share Tech Mono',monospace">
  {a['start']}&ndash;{a['end']} &nbsp; {fmt_hm(a['duration_seconds'])}</span>
</div>""", unsafe_allow_html=True)
        with r2:
            if st.button("✕", key=f"del_{i}", help="Delete this entry"):
                delete_entry(i)
                st.rerun()

    st.markdown("---")

    # Copy / paste area
    summary = build_summary_text()
    st.markdown("#### 📤 Copy, Download, or Email")
    st.caption("Select all in the box below to copy your hours, or use the buttons.")
    st.text_area("Copyable summary", summary, height=200, key="copy_area",
                 label_visibility="collapsed")

    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button(
            "⬇  CSV",
            data=build_csv_bytes(),
            file_name=f"workday_{real_now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "⬇  TXT",
            data=summary.encode("utf-8"),
            file_name=f"workday_{real_now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with d3:
        if st.button("✉  Email backup", use_container_width=True):
            ok, info = send_backup_email()
            (st.success if ok else st.warning)(info)

    if not email_configured():
        with st.expander("How to enable email backup"):
            st.markdown(
                "Create a file `.streamlit/secrets.toml` next to this app with:\n\n"
                "```toml\n"
                "[email]\n"
                "sender = \"you@gmail.com\"\n"
                "password = \"your-app-password\"\n"
                "smtp_server = \"smtp.gmail.com\"\n"
                "smtp_port = 587\n"
                "recipient = \"you@example.com\"\n"
                "```\n\n"
                "For Gmail, generate an App Password (not your normal password). "
                "On Streamlit Cloud, paste the same block into the app's Secrets settings."
            )

    st.markdown("")
    if st.button("🧹  Clear all registered activities"):
        st.session_state.confirm = "clear"
        st.rerun()
    if st.session_state.confirm == "clear":
        st.warning("Clear the entire log? Download or email a backup first if you need it.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("Yes, clear everything", use_container_width=True):
                clear_log()
                st.session_state.confirm = None
                st.rerun()
        with cc2:
            if st.button("Keep my log", use_container_width=True):
                st.session_state.confirm = None
                st.rerun()

# ─── CALCULATOR LOGIC (original states, motivational copy) ──────────────────

def run_calculator(entry, start_lunch, end_lunch, leave, now):

    if leave:
        lunch_dur = (end_lunch - start_lunch) if (start_lunch and end_lunch) else timedelta(0)
        worked = leave - entry - lunch_dur
        deficit = WORKDAY - worked
        pct = worked / WORKDAY

        st.markdown("### 📊 Day Summary")
        progress_bar(pct, f"{min(pct,1)*100:.1f}% of an 8 hour workday completed")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Hours Worked", fmt_td(max(worked, timedelta(0))))
        with c2:
            st.metric("Lunch", fmt_td(lunch_dur) if lunch_dur.total_seconds() > 0 else "—")
        with c3:
            if deficit.total_seconds() > 0:
                st.metric("Deficit", fmt_td(deficit))
            else:
                st.metric("Surplus", fmt_td(-deficit))

        st.markdown("")
        if worked >= WORKDAY:
            extra = (" Banked <strong>" + fmt_td(-deficit) + "</strong> extra, nice work."
                     if deficit.total_seconds() < 0 else " Right on target.")
            result_card(f"✅ Full day done. You worked <strong>{fmt_td(worked)}</strong>.{extra}",
                        "#2ecc71")
            coach_says(random.choice(FINAL_MSG))
        else:
            result_card(
                f"You worked <strong>{fmt_td(worked)}</strong> of 8h 00m, "
                f"<strong style='color:#e67e22'>{fmt_td(deficit)} to go</strong>. "
                f"No pressure, balance it tomorrow.",
                "#e67e22")
            coach_says(random.choice(SHORT_MSG))

    elif end_lunch and start_lunch:
        pre_lunch = start_lunch - entry
        lunch_dur = end_lunch - start_lunch
        worked_after = max(now - end_lunch, timedelta(0))
        total_worked = pre_lunch + worked_after
        remaining = max(WORKDAY - total_worked, timedelta(0))
        predicted_leave = end_lunch + (WORKDAY - pre_lunch)
        pct = total_worked / WORKDAY

        st.markdown("### 🍽️ Back from Lunch")
        live_stamp(now)
        coach_says(random.choice(AFTER_LUNCH_MSG))
        progress_bar(pct, f"{min(pct,1)*100:.1f}% of the workday done"
                     + (f", {fmt_td(remaining)} still to go" if remaining.total_seconds() > 0
                        else ", full day done"))

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Total Worked", fmt_td(total_worked))
        with c2:
            st.metric("Lunch", fmt_td(lunch_dur))
        with c3:
            if remaining.total_seconds() > 0:
                st.metric("Remaining", fmt_td(remaining))
            else:
                st.metric("Overtime", fmt_td(total_worked - WORKDAY))

        st.markdown("")
        result_card(f"Lunch was <strong>{fmt_td(lunch_dur)}</strong>. Target finish:")
        time_badge("Leave at", predicted_leave)

    elif start_lunch:
        worked_so_far = start_lunch - entry
        lunch_so_far = max(now - start_lunch, timedelta(0))
        remaining_after_lunch = max(WORKDAY - worked_so_far, timedelta(0))
        leave_30 = start_lunch + remaining_after_lunch + timedelta(minutes=30)
        leave_60 = start_lunch + remaining_after_lunch + timedelta(hours=1)
        pct = worked_so_far / WORKDAY

        st.markdown("### 🌿 Lunch Break")
        live_stamp(now)
        coach_says(random.choice(LUNCH_START_MSG))
        progress_bar(pct, f"{pct*100:.1f}% of the workday done before lunch")

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Worked (pre-lunch)", fmt_td(worked_so_far))
        with c2:
            st.metric("Lunch so far", fmt_td(lunch_so_far))

        st.markdown("")
        result_card("Depending on your lunch length:")
        c1, c2 = st.columns(2)
        with c1:
            time_badge("30-min lunch", leave_30)
            st.markdown("<div style='color:#777;font-size:0.8rem;text-align:center'>Leave at ↑</div>",
                        unsafe_allow_html=True)
        with c2:
            time_badge("1-hour lunch", leave_60)
            st.markdown("<div style='color:#777;font-size:0.8rem;text-align:center'>Leave at ↑</div>",
                        unsafe_allow_html=True)

    else:
        worked_now = max(now - entry, timedelta(0))
        remaining_now = max(WORKDAY - worked_now, timedelta(0))
        overtime_now = max(worked_now - WORKDAY, timedelta(0))
        pct_now = worked_now / WORKDAY
        leave_30 = entry + WORKDAY + timedelta(minutes=30)
        leave_60 = entry + WORKDAY + timedelta(hours=1)

        st.markdown("### 🕐 Day in Progress")
        live_stamp(now)
        coach_says(random.choice(ENTRY_MSG))
        progress_bar(pct_now, f"{min(pct_now,1)*100:.1f}% done"
                     + (f", {fmt_td(remaining_now)} left" if remaining_now.total_seconds() > 0
                        else ", full day logged"))

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Worked so far", fmt_td(worked_now))
        with c2:
            if remaining_now.total_seconds() > 0:
                st.metric("Remaining", fmt_td(remaining_now))
            else:
                st.metric("Overtime", fmt_td(overtime_now))

        st.markdown("")
        result_card("Depending on your lunch length:")
        c1, c2 = st.columns(2)
        with c1:
            time_badge("30-min lunch", leave_30)
            st.markdown("<div style='color:#777;font-size:0.8rem;text-align:center'>Leave at ↑</div>",
                        unsafe_allow_html=True)
        with c2:
            time_badge("1-hour lunch", leave_60)
            st.markdown("<div style='color:#777;font-size:0.8rem;text-align:center'>Leave at ↑</div>",
                        unsafe_allow_html=True)


def render_calculator():
    st.markdown("### 🧮 Workday Calculator")
    col_a, col_b = st.columns(2)
    with col_a:
        entry_raw = st.text_input("🕐 Entry time", placeholder="08:30  /  8:30 AM  /  08:30:00")
        end_lunch_raw = st.text_input("🍽️ Lunch end (optional)", placeholder="13:00")
    with col_b:
        start_lunch_raw = st.text_input("🌿 Lunch start (optional)", placeholder="12:15")
        leave_raw = st.text_input("🚪 Actual leave (optional)", placeholder="17:45")

    entry = parse_time(entry_raw)
    start_lunch = parse_time(start_lunch_raw)
    end_lunch = parse_time(end_lunch_raw)
    leave = parse_time(leave_raw)
    now = get_now()

    bad = [(lbl, raw) for lbl, raw, val in [
        ("Entry", entry_raw, entry),
        ("Lunch start", start_lunch_raw, start_lunch),
        ("Lunch end", end_lunch_raw, end_lunch),
        ("Leave", leave_raw, leave),
    ] if raw and raw.strip() and val is None]

    if bad:
        fields = ", ".join(f[0] for f in bad)
        st.error(f"Couldn't read: **{fields}**. "
                 f"Try formats like `08:30`, `8:30`, `08:30:00`, or `8:30 AM`.")
    elif not entry:
        st.markdown(
            "<div style='text-align:center;padding:20px 0;color:#555;"
            "font-family:Bebas Neue,sans-serif;font-size:1.2rem;letter-spacing:2px'>"
            "Drop your entry time above and we'll map out your finish line."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        run_calculator(entry, start_lunch, end_lunch, leave, now)

    return entry, leave, bad

# ─── PAGE ───────────────────────────────────────────────────────────────────

st.markdown("<h1>⏱️ WORKDAY TRACKER</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;color:#8a8170;font-style:italic;font-size:0.95rem;"
    "font-family:Barlow,sans-serif;margin-top:0'>"
    "Track your focus, capture your hours, finish strong.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

render_timer()
render_log()

st.markdown("---")

entry, leave, bad = render_calculator()

# ─── LIVE AUTO-REFRESH ──────────────────────────────────────────────────────
# 1s tick when a timer is running, slower tick for the live calculator countdown.
timer_running = bool(st.session_state.active and st.session_state.active.get("running"))
calc_live = bool(entry and not leave and not bad)

if timer_running:
    time.sleep(1)
    st.rerun()
elif calc_live:
    time.sleep(30)
    st.rerun()
