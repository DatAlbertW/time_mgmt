"""
WORKDAY TRACKER
===============
Single-file Streamlit app. Stdlib only, no requirements.txt needed.

PERSISTENCE MODEL
-----------------
The timer is stored as a TIMESTAMP, never as a counter. Elapsed time is always
recomputed as (now - started_at), so the clock keeps advancing while the app is
closed, your laptop is off, or you are on a different device. Nothing has to be
"running" anywhere for time to accrue.

State is written to durable storage after every change, and read back whenever a
session starts or goes stale. Three backends, chosen automatically:

  1. GitHub Gist  (survives everything: reboots, device switches, container
                   recycles, redeploys)  -> needs secrets, see SETUP below
  2. Local file   (survives browser refresh, tab close, and computer restart
                   when run locally; on Streamlit Cloud it survives until the
                   container is recycled)
  3. Session only (last resort, warns loudly)

Nothing resets on its own. The log clears only when you press the reset button
and confirm.

SETUP for full cross-device sync
--------------------------------
Create a secret gist at https://gist.github.com with any placeholder content and
note its id from the URL. Create a fine-grained token with Gist read/write at
https://github.com/settings/tokens. Then add to Streamlit secrets
(Manage app -> Settings -> Secrets, or .streamlit/secrets.toml locally):

    [storage]
    github_token = "github_pat_..."
    gist_id = "abc123..."

Open the same app URL on any device and your timer is there, still counting.
"""

import streamlit as st
from datetime import datetime, timedelta
import csv
import inspect
import io
import json
import os
import random
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

st.set_page_config(
    page_title="Workday Tracker",
    page_icon="⏱️",
    layout="centered",
)

WORKDAY = timedelta(hours=8)
LABELS = ["Meeting", "Jira", "Training", "Other"]
RECONCILE_TOLERANCE = 15 * 60           # seconds of gap treated as "close enough"
STALE_TIMER_SECONDS = 12 * 3600         # flag timers that look forgotten
RESYNC_AFTER_SECONDS = 90               # re-read storage if state is older than this
DATA_VERSION = 1
LOCAL_DIR = os.path.join(os.getcwd(), ".workday_data")

# ─── CAPABILITY DETECTION ───────────────────────────────────────────────────
def _tz():
    """Europe/Zurich if the tz database is available, otherwise machine local."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Zurich")
    except Exception:
        return None

TZ = _tz()

_FRAG = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)
HAS_FRAGMENT = _FRAG is not None

_RERUN = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)

def _rerun_takes_scope() -> bool:
    try:
        return "scope" in inspect.signature(_RERUN).parameters
    except Exception:
        return False

RERUN_HAS_SCOPE = _rerun_takes_scope()

def rerun_app():
    """Rerun the whole app, including when called from inside a fragment."""
    if _RERUN is None:
        return
    if RERUN_HAS_SCOPE:
        _RERUN(scope="app")
    else:
        _RERUN()

def button(label, **kwargs):
    """st.button that tolerates older versions lacking use_container_width."""
    try:
        return st.button(label, **kwargs)
    except TypeError:
        kwargs.pop("use_container_width", None)
        return st.button(label, **kwargs)

def text_input(label, **kwargs):
    """st.text_input that tolerates older versions lacking placeholder."""
    try:
        return st.text_input(label, **kwargs)
    except TypeError:
        kwargs.pop("placeholder", None)
        return st.text_input(label, **kwargs)

def read_query_param(name):
    """Read one query param across old and new Streamlit APIs."""
    try:
        val = st.query_params.get(name)
        if isinstance(val, list):
            val = val[0] if val else None
        if val:
            return val
    except Exception:
        pass
    try:
        vals = st.experimental_get_query_params().get(name)
        if vals:
            return vals[0]
    except Exception:
        pass
    return None

# Same URL on every device means the same log. Add ?u=someone to keep a
# separate log, which is only useful if you share the app.
USER_ID = (read_query_param("u") or "default").strip()[:40] or "default"

# ─── TIME HELPERS ───────────────────────────────────────────────────────────
def real_now() -> datetime:
    if TZ is not None:
        return datetime.now(TZ)
    return datetime.now().astimezone()

def today_str() -> str:
    return real_now().strftime("%Y-%m-%d")

def to_iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else None

def from_iso(txt):
    if not txt:
        return None
    try:
        dt = datetime.fromisoformat(txt)
    except Exception:
        return None
    # Stored values are timezone-aware. Attach the current zone if an old
    # naive value shows up, so subtraction never raises.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=real_now().tzinfo)
    return dt

def fmt_clock(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"

def fmt_hm(seconds: float) -> str:
    s = int(abs(seconds))
    h, rem = divmod(s, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m"

def fmt_td(td: timedelta) -> str:
    return fmt_hm(td.total_seconds())

def parse_time(raw: str):
    """Accept 08:30, 8:30, 08:30:00, 8:30 AM, 8.30 and friends."""
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

def parse_date(raw: str):
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def span_seconds(start_dt: datetime, end_dt: datetime) -> int:
    return int((end_dt - start_dt).total_seconds())

def pct_color(p: float) -> str:
    if p >= 1.0:
        return "#2ecc71"
    if p >= 0.6:
        return "#f5c518"
    return "#e67e22"

# ─── STORAGE BACKENDS ───────────────────────────────────────────────────────
class MemoryStore:
    """No durability. Only used when everything else is unavailable."""
    key = "memory"
    label = "Session only"
    durable = False
    detail = ("Nothing is being saved outside this browser tab. Add gist secrets "
              "for cross-device sync, or run the app locally for file storage.")

    def load(self, user):
        return None, None

    def save(self, user, payload):
        return True, None


class FileStore:
    """JSON on the machine running Streamlit."""
    key = "file"
    label = "Local file"
    durable = True
    detail = ("Saved to a file next to the app. This survives browser refreshes, "
              "closing the tab, and restarting your computer when you run the app "
              "locally. On Streamlit Cloud it is lost when the container recycles, "
              "so add gist secrets for true cross-device safety.")

    def _path(self, user):
        return os.path.join(LOCAL_DIR, f"{user}.json")

    def load(self, user):
        try:
            path = self._path(user)
            if not os.path.exists(path):
                return None, None
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f), None
        except Exception as e:
            return None, f"Could not read local file: {e}"

    def save(self, user, payload):
        try:
            os.makedirs(LOCAL_DIR, exist_ok=True)
            tmp = self._path(user) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path(user))    # atomic, never a half-written file
            return True, None
        except Exception as e:
            return False, f"Could not write local file: {e}"


class GistStore:
    """A private GitHub gist as a tiny key-value store. Stdlib HTTP only."""
    key = "gist"
    label = "GitHub Gist"
    durable = True
    detail = ("Saved to your private gist. Your timer survives reboots, redeploys, "
              "and device switches. Open this same URL anywhere to pick it up.")

    API = "https://api.github.com/gists/"

    def __init__(self, token, gist_id):
        self.token = token
        self.gist_id = gist_id

    def _filename(self, user):
        return f"workday_{user}.json"

    def _request(self, method, payload=None, url=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url or (self.API + self.gist_id),
                                     data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "workday-tracker")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}

    def load(self, user):
        try:
            gist = self._request("GET")
            entry = (gist.get("files") or {}).get(self._filename(user))
            if not entry:
                return None, None
            content = entry.get("content")
            if entry.get("truncated") and entry.get("raw_url"):
                with urllib.request.urlopen(entry["raw_url"], timeout=12) as r:
                    content = r.read().decode("utf-8")
            if not content:
                return None, None
            return json.loads(content), None
        except urllib.error.HTTPError as e:
            return None, f"Gist read failed ({e.code}). Check the token and gist id."
        except Exception as e:
            return None, f"Gist read failed: {e}"

    def save(self, user, payload):
        try:
            body = {"files": {self._filename(user): {
                "content": json.dumps(payload, ensure_ascii=False, indent=2)}}}
            self._request("PATCH", body)
            return True, None
        except urllib.error.HTTPError as e:
            return False, f"Gist write failed ({e.code}). Does the token have gist scope?"
        except Exception as e:
            return False, f"Gist write failed: {e}"


def _build_store():
    """Pick the most durable backend available. Never raises."""
    try:
        cfg = st.secrets["storage"]
        token, gist_id = cfg.get("github_token"), cfg.get("gist_id")
        if token and gist_id:
            return GistStore(token, gist_id)
    except Exception:
        pass
    try:
        os.makedirs(LOCAL_DIR, exist_ok=True)
        probe = os.path.join(LOCAL_DIR, ".probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return FileStore()
    except Exception:
        return MemoryStore()

STORE = _build_store()

# ─── SERIALISATION ──────────────────────────────────────────────────────────
def serialise_state():
    a = st.session_state.active
    active = None
    if a:
        active = dict(a)
        active["created_at"] = to_iso(a.get("created_at"))
        active["started_at"] = to_iso(a.get("started_at"))
    return {
        "version": DATA_VERSION,
        "saved_at": to_iso(real_now()),
        "activities": st.session_state.activities,
        "active": active,
    }

def apply_loaded(data):
    """Replace in-memory state with what storage holds."""
    if not isinstance(data, dict):
        return
    st.session_state.activities = data.get("activities") or []
    a = data.get("active")
    if a:
        a = dict(a)
        a["created_at"] = from_iso(a.get("created_at"))
        a["started_at"] = from_iso(a.get("started_at"))
        # A record with no usable start timestamp is unusable, drop it rather
        # than crash later on subtraction.
        if a.get("started_at") is None:
            a = None
    st.session_state.active = a
    st.session_state.last_sync = real_now()

def persist():
    """Write current state. Called after every mutation, never on a clock tick."""
    ok, err = STORE.save(USER_ID, serialise_state())
    st.session_state.store_error = err
    if ok:
        st.session_state.last_saved = real_now()
    return ok

def pull(force=False):
    """Read storage into state if this session has never loaded, or is stale."""
    if not STORE.durable:
        return
    last = st.session_state.get("last_sync")
    if not force and last is not None:
        if (real_now() - last).total_seconds() < RESYNC_AFTER_SECONDS:
            return
    data, err = STORE.load(USER_ID)
    st.session_state.store_error = err
    if data is not None:
        apply_loaded(data)
    else:
        st.session_state.last_sync = real_now()

# ─── SESSION STATE ──────────────────────────────────────────────────────────
st.session_state.setdefault("activities", [])
st.session_state.setdefault("active", None)
st.session_state.setdefault("confirm", None)
st.session_state.setdefault("editing_active", False)
st.session_state.setdefault("editing_idx", None)
st.session_state.setdefault("edit_token", "0")
st.session_state.setdefault("edit_flash", None)
st.session_state.setdefault("show_manual", False)
st.session_state.setdefault("coach_msgs", {})
st.session_state.setdefault("last_sync", None)
st.session_state.setdefault("last_saved", None)
st.session_state.setdefault("store_error", None)

# First contact with storage happens before anything renders, so a fresh
# browser on a fresh device immediately sees the running timer.
pull()

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
[data-testid="stHeader"]  { background: transparent !important; }
[data-testid="stSidebar"] { background: #111 !important; }
section.main > div        { padding-top: 1.5rem; }
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
input[type="text"], textarea, [data-baseweb="select"] > div,
[data-baseweb="input"] input {
    background-color: #1a1a1a !important;
    color: #e8dcc8 !important;
    border-color: #333 !important;
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
[data-testid="metric-container"] {
    background: #161616;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 12px 16px !important;
}

/* ── Buttons ──────────────────────────────────────────────────────────────
   1. DESCENDANT selectors, not direct-child. A button with help= gets wrapped
      in an extra tooltip div, so `.stButton > button` misses it and the button
      falls back to the default white style.
   2. The label sits in a nested <p>/<span>, so colour must be forced on
      descendants too, or glyph-only buttons render pale.
   3. Avoid colour-emoji glyphs in labels: they are painted by the font and
      ignore CSS colour entirely.                                            */
.stButton button,
.stDownloadButton button,
[data-testid="stTooltipHoverTarget"] button,
button[data-testid="stBaseButton-secondary"],
button[data-testid="baseButton-secondary"] {
    background: #161616 !important;
    background-color: #161616 !important;
    color: #f5c518 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 6px !important;
    font-family: 'Barlow', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px;
    transition: all .2s ease;
}
.stButton button *,
.stDownloadButton button *,
[data-testid="stTooltipHoverTarget"] button * {
    color: #f5c518 !important;
    fill: #f5c518 !important;
}
.stButton button:hover,
.stDownloadButton button:hover,
[data-testid="stTooltipHoverTarget"] button:hover {
    border-color: #f5c518 !important;
    box-shadow: 0 0 10px rgba(245,197,24,0.25) !important;
    background-color: #1c1c1c !important;
}
.stButton button:hover *,
.stDownloadButton button:hover *,
[data-testid="stTooltipHoverTarget"] button:hover * { color: #f5c518 !important; }
.stButton button:focus,
.stButton button:active,
.stButton button:focus:not(:active),
[data-testid="stTooltipHoverTarget"] button:focus,
[data-testid="stTooltipHoverTarget"] button:active {
    background-color: #161616 !important;
    color: #f5c518 !important;
    border-color: #f5c518 !important;
    box-shadow: none !important;
}
.stButton button:focus *,
.stButton button:active *,
[data-testid="stTooltipHoverTarget"] button:focus * { color: #f5c518 !important; }

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
.edit-panel-title {
    font-family: 'Bebas Neue', sans-serif; color: #f5c518;
    letter-spacing: 2px; font-size: 1.05rem; margin: 10px 0 2px 0;
}
.edit-panel-sub {
    color: #8a8170; font-size: 0.85rem; margin-bottom: 6px;
    font-family: 'Barlow', sans-serif;
}
.section-note {
    color: #6f6a60; font-size: 0.8rem; font-family: 'Barlow', sans-serif;
    margin: 2px 0 8px 0;
}
.store-bar {
    display: flex; justify-content: space-between; align-items: center;
    background: #141414; border: 1px solid #262626; border-radius: 8px;
    padding: 7px 14px; margin: 4px 0 10px 0;
    font-family: 'Share Tech Mono', monospace; font-size: 0.75rem; color: #6f6a60;
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
RELABEL_MSG = [
    "Updated. Plans change, and an accurate log is the honest one.",
    "Renamed. What matters is that the record matches the real work.",
    "Adjusted. Blocked on one thing, useful on another, and now it's logged properly.",
    "Saved. Good tracking is tracking what actually happened.",
]

def coach_msg(key: str, pool) -> str:
    """Pick a line once per event and keep it, so refreshes don't reshuffle it."""
    store = st.session_state.setdefault("coach_msgs", {})
    if key not in store:
        store[key] = random.choice(pool)
    return store[key]

def refresh_coach(*keys):
    store = st.session_state.setdefault("coach_msgs", {})
    for k in keys:
        store.pop(k, None)

# ─── TIMER MODEL ────────────────────────────────────────────────────────────
# active = {
#   label, description,
#   created_at   : when this block was first started (used for the log's start)
#   started_at   : when the CURRENT running stretch began, or None while paused
#   accumulated  : seconds banked by previous stretches
#   running      : bool
# }
# Elapsed is always accumulated + (now - started_at). Nothing decays if the app
# is closed, because started_at is an absolute wall-clock time in storage.

def active_elapsed() -> float:
    a = st.session_state.active
    if not a:
        return 0.0
    secs = float(a.get("accumulated", 0.0))
    if a.get("running") and a.get("started_at"):
        secs += (real_now() - a["started_at"]).total_seconds()
    return max(secs, 0.0)

def sort_activities():
    st.session_state.activities.sort(key=lambda a: (a.get("date", ""), a.get("start", "")))

def start_activity(label: str, description: str):
    now = real_now()
    st.session_state.active = {
        "label": label,
        "description": description.strip(),
        "accumulated": 0.0,
        "running": True,
        "started_at": now,
        "created_at": now,
    }
    refresh_coach("timer_start")
    persist()

def pause_activity():
    a = st.session_state.active
    if a and a.get("running") and a.get("started_at"):
        a["accumulated"] = float(a.get("accumulated", 0.0)) + \
            (real_now() - a["started_at"]).total_seconds()
        a["running"] = False
        a["started_at"] = None
        persist()

def resume_activity():
    a = st.session_state.active
    if a and not a.get("running"):
        a["started_at"] = real_now()
        a["running"] = True
        persist()

def register_activity():
    a = st.session_state.active
    if not a:
        return
    duration = active_elapsed()
    start_dt = a.get("created_at") or real_now()
    end_dt = real_now()
    st.session_state.activities.append({
        "date": start_dt.strftime("%Y-%m-%d"),
        "label": a["label"],
        "description": a["description"],
        "start": start_dt.strftime("%H:%M"),
        "end": end_dt.strftime("%H:%M"),
        "duration_seconds": int(duration),
    })
    sort_activities()
    st.session_state.active = None
    refresh_coach("register", "timer_start")
    persist()

def discard_activity():
    st.session_state.active = None
    refresh_coach("timer_start")
    persist()

def add_manual_entry(day, label, description, start_txt, end_txt, duration_seconds):
    st.session_state.activities.append({
        "date": day,
        "label": label,
        "description": description.strip(),
        "start": start_txt,
        "end": end_txt,
        "duration_seconds": int(duration_seconds),
    })
    sort_activities()
    refresh_coach("register")
    persist()

def delete_entry(idx: int):
    if 0 <= idx < len(st.session_state.activities):
        st.session_state.activities.pop(idx)
        persist()

def clear_log():
    st.session_state.activities = []
    persist()

def reset_everything():
    st.session_state.activities = []
    st.session_state.active = None
    st.session_state.coach_msgs = {}
    persist()

# ─── EDIT HELPERS ───────────────────────────────────────────────────────────
def open_editor(target):
    """target is either 'active' or an integer log index."""
    st.session_state.editing_active = (target == "active")
    st.session_state.editing_idx = target if isinstance(target, int) else None
    # A fresh token gives the edit widgets fresh keys, so they load current
    # values rather than whatever was typed last time an editor was open.
    st.session_state.edit_token = real_now().strftime("%H%M%S%f")
    st.session_state.edit_flash = None

def close_editors():
    st.session_state.editing_active = False
    st.session_state.editing_idx = None

def update_active_meta(label: str, description: str):
    a = st.session_state.active
    if a:
        a["label"] = label
        a["description"] = description.strip()
        persist()

def update_entry(idx, label, description, day, start_txt, end_txt, duration_seconds):
    if 0 <= idx < len(st.session_state.activities):
        st.session_state.activities[idx].update({
            "label": label,
            "description": description.strip(),
            "date": day,
            "start": start_txt,
            "end": end_txt,
            "duration_seconds": int(duration_seconds),
        })
        sort_activities()
        persist()

def type_picker(current_label: str, key_prefix: str):
    """Selectbox plus custom field, pre-filled from the current label."""
    is_custom = current_label not in LABELS
    base = "Other" if is_custom else current_label
    c1, c2 = st.columns([1, 2])
    with c1:
        sel = st.selectbox("Type", LABELS, index=LABELS.index(base),
                           key=f"{key_prefix}_label")
    with c2:
        custom = ""
        if sel == "Other":
            custom = text_input("Custom type",
                                value=current_label if is_custom else "",
                                key=f"{key_prefix}_custom",
                                placeholder="e.g. Code review")
    return sel, custom.strip()

def resolve_label(sel: str, custom: str) -> str:
    return custom if (sel == "Other" and custom) else sel

# ─── TRACKED VS PRESENCE HELPERS ────────────────────────────────────────────
def tracked_today_seconds() -> float:
    day = today_str()
    total = sum(a["duration_seconds"] for a in st.session_state.activities
                if a.get("date") == day)
    a = st.session_state.active
    if a and a.get("created_at") and a["created_at"].strftime("%Y-%m-%d") == day:
        total += active_elapsed()
    return float(total)

def suggest_entry_time():
    """Earliest tracked start today, as HH:MM, or None."""
    day = today_str()
    starts = [a["start"] for a in st.session_state.activities if a.get("date") == day]
    a = st.session_state.active
    if a and a.get("created_at") and a["created_at"].strftime("%Y-%m-%d") == day:
        starts.append(a["created_at"].strftime("%H:%M"))
    return min(starts) if starts else None

# ─── UI COMPONENTS ──────────────────────────────────────────────────────────
def live_stamp(now: datetime):
    st.markdown(
        f'<div class="live-badge"><span class="live-dot"></span>'
        f'LIVE &nbsp;&middot;&nbsp; {now.strftime("%H:%M:%S")}</div>',
        unsafe_allow_html=True,
    )

def progress_bar(pct: float, label: str, color: str = None):
    p = min(max(pct, 0), 1)
    c = color or pct_color(p)
    st.markdown(f"""
<div style="margin:12px 0 4px 0">
  <div style="background:#222;border-radius:6px;overflow:hidden;height:16px">
    <div style="width:{p*100:.1f}%;background:{c};height:100%;
    border-radius:6px;transition:width .4s ease;box-shadow:0 0 8px {c}88"></div>
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

def note(text: str):
    st.markdown(f"<div class='section-note'>{text}</div>", unsafe_allow_html=True)

# ─── STORAGE BAR ────────────────────────────────────────────────────────────
def render_storage_bar():
    saved = st.session_state.get("last_saved")
    saved_txt = saved.strftime("%H:%M:%S") if saved else "not yet"
    dot = "#2ecc71" if STORE.durable else "#e67e22"
    st.markdown(
        f"<div class='store-bar'><span>"
        f"<span style='color:{dot}'>&#9679;</span>&nbsp; {STORE.label.upper()}"
        f"{'' if USER_ID == 'default' else ' &middot; ' + USER_ID}</span>"
        f"<span>saved {saved_txt}</span></div>",
        unsafe_allow_html=True,
    )

    if st.session_state.get("store_error"):
        st.error(f"Storage problem: {st.session_state.store_error}  "
                 f"Your work is still on screen. Download the CSV before closing.")

    if not STORE.durable:
        st.warning("No durable storage configured, so this tab is the only copy. "
                   "See the setup note below to switch on cross-device sync.")

    with st.expander("Sync, storage, and reset"):
        st.markdown(f"**{STORE.label}.** {STORE.detail}")
        c1, c2 = st.columns(2)
        with c1:
            if button("⟳  Sync from storage now", use_container_width=True, key="sync_now"):
                pull(force=True)
                rerun_app()
        with c2:
            if button("⇪  Force save now", use_container_width=True, key="save_now"):
                if persist():
                    st.success("Saved.")
                rerun_app()

        note("Open this same URL on any device to continue. A running timer keeps "
             "counting the whole time, because only its start time is stored.")

        if STORE.key != "gist":
            st.markdown(
                "To survive container recycles and device switches, create a secret "
                "gist and a token with gist scope, then add:\n\n"
                "```toml\n[storage]\ngithub_token = \"github_pat_...\"\n"
                "gist_id = \"your-gist-id\"\n```"
            )

        st.markdown("---")
        note("Nothing in this app resets on its own. This is the only button that "
             "wipes the running timer and the whole log.")
        if button("↺  Reset everything and start fresh", key="reset_all"):
            close_editors()
            st.session_state.confirm = "reset"
            rerun_app()

    if st.session_state.confirm == "reset":
        st.warning("Reset the running timer AND every registered block? "
                   "Download a copy first if you need it.")
        r1, r2 = st.columns(2)
        with r1:
            if button("Yes, reset everything", use_container_width=True, key="conf_reset_yes"):
                reset_everything()
                st.session_state.confirm = None
                rerun_app()
        with r2:
            if button("Cancel", use_container_width=True, key="conf_reset_no"):
                st.session_state.confirm = None
                rerun_app()

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
    for day in sorted(by_date):
        entries = by_date[day]
        lines.append(f"Date: {day}")
        totals = {}
        day_total = 0
        for a in entries:
            totals[a["label"]] = totals.get(a["label"], 0) + a["duration_seconds"]
            day_total += a["duration_seconds"]
        for label in sorted(totals):
            lines.append(f"  {label}: {fmt_hm(totals[label])}")
        lines.append(f"  Total tracked: {fmt_hm(day_total)}")
        lines.append("")
        lines.append("  Entries:")
        for a in entries:
            desc = f" ({a['description']})" if a["description"] else ""
            lines.append(f"    {a['start']} to {a['end']}  "
                         f"{a['label']}{desc}: {fmt_hm(a['duration_seconds'])}")
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

def send_backup_email():
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
            build_csv_bytes(), maintype="text", subtype="csv",
            filename=f"workday_{real_now().strftime('%Y%m%d_%H%M')}.csv",
        )
        with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as server:
            server.starttls()
            server.login(cfg["sender"], cfg["password"])
            server.send_message(msg)
        return True, f"Backup sent to {cfg['recipient']}."
    except Exception as e:
        return False, f"Email failed: {e}"

# ─── LIVE CLOCK CARD ────────────────────────────────────────────────────────
def live_activity_card():
    """Only the ticking card, so an auto-refresh touches nothing else."""
    a = st.session_state.active
    if not a:
        return
    elapsed = active_elapsed()
    running = a.get("running")
    status_color = "#2ecc71" if running else "#e67e22"
    status_text = "RUNNING" if running else "PAUSED"
    since = a.get("created_at")
    since_txt = f"since {since.strftime('%a %H:%M')}" if since else ""
    st.markdown(f"""
<div style="background:#161616;border:1px solid {status_color}55;border-radius:10px;
padding:18px;margin:6px 0 12px 0">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div style="color:#f5c518;font-family:'Bebas Neue',sans-serif;font-size:1.4rem;
    letter-spacing:2px">{a['label']}</div>
    <div style="color:{status_color};font-family:'Share Tech Mono',monospace;
    font-size:0.8rem;letter-spacing:2px">{status_text}</div>
  </div>
  <div style="color:#8a8170;font-size:0.9rem;margin-top:2px">
  {a['description'] or 'No description'}</div>
  <div class="big-clock" style="margin-top:10px">{fmt_clock(elapsed)}</div>
  <div style="color:#5f5a52;font-size:0.72rem;text-align:center;
  font-family:'Share Tech Mono',monospace">{since_txt}</div>
</div>""", unsafe_allow_html=True)

# ─── ACTIVITY TIMER SECTION ─────────────────────────────────────────────────
def render_timer():
    st.markdown("### ⏱️ Activity Timer")
    a = st.session_state.active

    # ── No active timer: start a new one ──
    if not a:
        coach_says(coach_msg("timer_start", TIMER_START_MSG))
        c1, c2 = st.columns([1, 2])
        with c1:
            label = st.selectbox("Label", LABELS, key="new_label")
        with c2:
            custom = ""
            if label == "Other":
                custom = text_input("Custom label", key="new_custom",
                                    placeholder="e.g. Code review")
        desc = text_input("Description (optional, but always available)",
                          key="new_desc", placeholder="What are you working on?")
        final_label = custom.strip() if (label == "Other" and custom.strip()) else label
        if button("▶  Start timer", use_container_width=True):
            if label == "Other" and not custom.strip() and not desc.strip():
                st.warning("Add a custom label or a description so this block is identifiable.")
            else:
                start_activity(final_label, desc)
                rerun_app()
        note("Started the wrong thing? Any block can be re-typed and renamed later, "
             "while it runs or after it's registered.")
        return

    # ── Active timer present ──
    running = a.get("running")
    if running and HAS_FRAGMENT:
        live_card_auto()          # refreshes itself once a second
    else:
        live_activity_card()

    elapsed = active_elapsed()

    if running and elapsed > STALE_TIMER_SECONDS:
        st.warning(f"This block has been running for {fmt_hm(elapsed)}. If you left it "
                   f"going overnight, register it and fix the end time, or discard it.")

    if running and not HAS_FRAGMENT:
        if button("⟳  Refresh clock", key="manual_tick"):
            rerun_app()
        note("This Streamlit version has no auto-refreshing fragments, so the clock "
             "updates when you refresh. The time itself is computed from the stored "
             "start timestamp, so nothing is lost in between.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if running:
            if button("⏸  Pause", use_container_width=True):
                pause_activity()
                rerun_app()
        else:
            if button("▶  Resume", use_container_width=True):
                resume_activity()
                rerun_app()
    with c2:
        if button("Edit", use_container_width=True,
                  help="Change the type or title of this running block"):
            open_editor("active")
            rerun_app()
    with c3:
        if button("Register", use_container_width=True):
            close_editors()
            st.session_state.confirm = "register"
            rerun_app()
    with c4:
        if button("Discard", use_container_width=True):
            close_editors()
            st.session_state.confirm = "discard"
            rerun_app()

    # ── Inline editor for the live block ──
    if st.session_state.editing_active:
        token = st.session_state.edit_token
        st.markdown('<div class="edit-panel-title">EDIT THIS BLOCK</div>'
                    '<div class="edit-panel-sub">Ended up doing something else? '
                    'Re-type and rename it. The elapsed time stays exactly as it is.</div>',
                    unsafe_allow_html=True)
        sel, custom = type_picker(a["label"], f"activeedit_{token}")
        new_desc = text_input("Title / description", value=a.get("description", ""),
                              key=f"activeedit_{token}_desc",
                              placeholder="What are you actually working on?")
        new_label = resolve_label(sel, custom)

        e1, e2 = st.columns(2)
        with e1:
            if button("Save changes", use_container_width=True,
                      key=f"activeedit_{token}_save"):
                if sel == "Other" and not custom and not new_desc.strip():
                    st.warning("Add a custom type or a title so this block stays identifiable.")
                else:
                    update_active_meta(new_label, new_desc)
                    close_editors()
                    st.session_state.edit_flash = random.choice(RELABEL_MSG)
                    rerun_app()
        with e2:
            if button("Cancel", use_container_width=True,
                      key=f"activeedit_{token}_cancel"):
                close_editors()
                rerun_app()

    if st.session_state.edit_flash:
        coach_says(st.session_state.edit_flash)
        st.session_state.edit_flash = None

    # ── Confirmations ──
    if st.session_state.confirm == "register":
        st.warning(f"Register this task?  **{a['label']}** at **{fmt_hm(elapsed)}**.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if button("Yes, register it", use_container_width=True, key="conf_reg_yes"):
                register_activity()
                st.session_state.confirm = None
                rerun_app()
        with cc2:
            if button("Cancel", use_container_width=True, key="conf_reg_no"):
                st.session_state.confirm = None
                rerun_app()

    if st.session_state.confirm == "discard":
        st.warning("Discard this timer without registering it? This cannot be undone.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if button("Yes, discard", use_container_width=True, key="conf_dis_yes"):
                discard_activity()
                st.session_state.confirm = None
                rerun_app()
        with cc2:
            if button("Keep it", use_container_width=True, key="conf_dis_no"):
                st.session_state.confirm = None
                rerun_app()

    note("Switched tasks mid-block? Hit Edit to re-type and rename it. To split the time "
         "instead, register this one and start the next.")

# ─── RETROACTIVE ENTRY ──────────────────────────────────────────────────────
def render_manual_entry():
    if not st.session_state.show_manual:
        if button("＋  Log a past block", use_container_width=True, key="open_manual"):
            st.session_state.show_manual = True
            rerun_app()
        note("Forgot to hit start? Add the block by hand with its real start and end times.")
        return

    st.markdown('<div class="edit-panel-title">LOG A PAST BLOCK</div>'
                '<div class="edit-panel-sub">For work that happened without the timer '
                'running. Duration is calculated from start and end.</div>',
                unsafe_allow_html=True)

    d1, d2, d3 = st.columns([2, 1, 1])
    with d1:
        day_raw = text_input("Date", value=today_str(), key="man_date",
                             placeholder="YYYY-MM-DD")
    with d2:
        start_raw = text_input("Start", key="man_start", placeholder="09:15")
    with d3:
        end_raw = text_input("End", key="man_end", placeholder="10:00")

    sel, custom = type_picker(LABELS[0], "man")
    desc = text_input("Title / description", key="man_desc",
                      placeholder="What was this block?")
    label = resolve_label(sel, custom)

    day = parse_date(day_raw)
    start_dt = parse_time(start_raw)
    end_dt = parse_time(end_raw)
    if start_dt and end_dt and span_seconds(start_dt, end_dt) > 0:
        note(f"Duration: <span style='color:#f5c518'>"
             f"{fmt_hm(span_seconds(start_dt, end_dt))}</span>")

    m1, m2 = st.columns(2)
    with m1:
        if button("Add to log", use_container_width=True, key="man_save"):
            if not day:
                st.warning("Couldn't read the date. Use `YYYY-MM-DD` or `DD.MM.YYYY`.")
            elif not start_dt or not end_dt:
                st.warning("Start and end are required. Try `09:15` or `9:15 AM`.")
            elif span_seconds(start_dt, end_dt) <= 0:
                st.warning("End time must be after start time. A block crossing midnight "
                           "needs to be logged as two entries.")
            elif sel == "Other" and not custom and not desc.strip():
                st.warning("Add a custom type or a title so this entry is identifiable.")
            else:
                add_manual_entry(day.strftime("%Y-%m-%d"), label, desc,
                                 start_dt.strftime("%H:%M"), end_dt.strftime("%H:%M"),
                                 span_seconds(start_dt, end_dt))
                st.session_state.show_manual = False
                st.session_state.edit_flash = "Past block added. Fewer lost hours, a truer record."
                rerun_app()
    with m2:
        if button("Cancel", use_container_width=True, key="man_cancel"):
            st.session_state.show_manual = False
            rerun_app()

# ─── REGISTERED LOG SECTION ─────────────────────────────────────────────────
def render_log():
    acts = st.session_state.activities
    st.markdown("### 📋 Registered Activities")

    if st.session_state.edit_flash:
        coach_says(st.session_state.edit_flash)
        st.session_state.edit_flash = None

    if not acts:
        st.markdown("<div style='color:#666;font-style:italic;padding:6px 0'>"
                    "Nothing registered yet. Start a timer above, and your blocks land here."
                    "</div>", unsafe_allow_html=True)
        render_manual_entry()
        return

    coach_says(coach_msg("register", REGISTER_MSG))

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
    result_card(f"⏱️ Total tracked: <strong>{fmt_hm(grand)}</strong> across "
                f"<strong>{len(acts)}</strong> registered "
                f"{'block' if len(acts) == 1 else 'blocks'}.", "#2ecc71")

    for i, a in enumerate(acts):
        desc = f" &middot; {a['description']}" if a["description"] else ""
        r1, r2, r3 = st.columns([6, 1, 1])
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
            if button("Edit", key=f"edit_{i}", help="Edit type, title, or times"):
                open_editor(i)
                rerun_app()
        with r3:
            if button("✕", key=f"del_{i}", help="Delete this entry"):
                delete_entry(i)
                close_editors()
                rerun_app()

        # ── Inline editor for this saved entry ──
        if st.session_state.editing_idx == i:
            token = st.session_state.edit_token
            st.markdown('<div class="edit-panel-title">EDIT ENTRY</div>'
                        '<div class="edit-panel-sub">Type, title, and times are all '
                        'editable. Duration recalculates from start and end.</div>',
                        unsafe_allow_html=True)
            sel, custom = type_picker(a["label"], f"logedit_{i}_{token}")
            new_desc = text_input("Title / description", value=a.get("description", ""),
                                  key=f"logedit_{i}_{token}_desc",
                                  placeholder="What was this block really about?")
            t1, t2, t3 = st.columns([2, 1, 1])
            with t1:
                new_day_raw = text_input("Date", value=a["date"],
                                         key=f"logedit_{i}_{token}_date",
                                         placeholder="YYYY-MM-DD")
            with t2:
                new_start = text_input("Start", value=a["start"],
                                       key=f"logedit_{i}_{token}_start")
            with t3:
                new_end = text_input("End", value=a["end"],
                                     key=f"logedit_{i}_{token}_end")

            new_label = resolve_label(sel, custom)
            new_day = parse_date(new_day_raw)
            s_dt, e_dt = parse_time(new_start), parse_time(new_end)
            if s_dt and e_dt and span_seconds(s_dt, e_dt) > 0:
                note(f"New duration: <span style='color:#f5c518'>"
                     f"{fmt_hm(span_seconds(s_dt, e_dt))}</span> "
                     f"(was {fmt_hm(a['duration_seconds'])})")

            e1, e2 = st.columns(2)
            with e1:
                if button("Save changes", use_container_width=True,
                          key=f"logedit_{i}_{token}_save"):
                    if not new_day:
                        st.warning("Couldn't read the date. Use `YYYY-MM-DD`.")
                    elif not s_dt or not e_dt:
                        st.warning("Couldn't read the times. Try `09:15` or `9:15 AM`.")
                    elif span_seconds(s_dt, e_dt) <= 0:
                        st.warning("End time must be after start time.")
                    elif sel == "Other" and not custom and not new_desc.strip():
                        st.warning("Add a custom type or a title so this entry stays identifiable.")
                    else:
                        update_entry(i, new_label, new_desc,
                                     new_day.strftime("%Y-%m-%d"),
                                     s_dt.strftime("%H:%M"), e_dt.strftime("%H:%M"),
                                     span_seconds(s_dt, e_dt))
                        close_editors()
                        st.session_state.edit_flash = random.choice(RELABEL_MSG)
                        rerun_app()
            with e2:
                if button("Cancel", use_container_width=True,
                          key=f"logedit_{i}_{token}_cancel"):
                    close_editors()
                    rerun_app()
            st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown("")
    render_manual_entry()
    st.markdown("---")

    summary = build_summary_text()
    st.markdown("#### 📤 Copy, Download, or Email")
    st.caption("Select all in the box below to copy your hours, or use the buttons.")
    st.text_area("Copyable summary", summary, height=200, key="copy_area",
                 label_visibility="collapsed")

    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button("⬇  CSV", data=build_csv_bytes(),
                           file_name=f"workday_{real_now().strftime('%Y%m%d_%H%M')}.csv",
                           mime="text/csv", use_container_width=True)
    with d2:
        st.download_button("⬇  TXT", data=summary.encode("utf-8"),
                           file_name=f"workday_{real_now().strftime('%Y%m%d_%H%M')}.txt",
                           mime="text/plain", use_container_width=True)
    with d3:
        if button("✉  Email backup", use_container_width=True, key="email_backup"):
            ok, info = send_backup_email()
            (st.success if ok else st.warning)(info)

    if not email_configured():
        with st.expander("How to enable email backup"):
            st.markdown(
                "Add these secrets to the app (Streamlit Cloud: **Manage app → Settings → "
                "Secrets**; locally: `.streamlit/secrets.toml`):\n\n"
                "```toml\n"
                "[email]\n"
                "sender = \"you@gmail.com\"\n"
                "password = \"your-app-password\"\n"
                "smtp_server = \"smtp.gmail.com\"\n"
                "smtp_port = 587\n"
                "recipient = \"you@example.com\"\n"
                "```\n\n"
                "For Gmail, generate an App Password rather than using your normal one."
            )

    st.markdown("")
    if button("🧹  Clear all registered activities", key="clear_all"):
        close_editors()
        st.session_state.confirm = "clear"
        rerun_app()

    if st.session_state.confirm == "clear":
        st.warning("Clear the entire log? The running timer is untouched. "
                   "Download a copy first if you need it.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if button("Yes, clear the log", use_container_width=True, key="conf_clr_yes"):
                clear_log()
                st.session_state.confirm = None
                rerun_app()
        with cc2:
            if button("Keep my log", use_container_width=True, key="conf_clr_no"):
                st.session_state.confirm = None
                rerun_app()

# ─── RECONCILIATION: PRESENCE VS TRACKED ────────────────────────────────────
def render_reconciliation(presence_seconds: float):
    tracked = tracked_today_seconds()
    if tracked <= 0:
        note("Nothing tracked today yet. Once you register blocks, this section compares "
             "them against your presence time.")
        return

    presence = max(presence_seconds, 0.0)
    gap = presence - tracked
    coverage = tracked / presence if presence > 0 else 0
    bar_color = ("#2ecc71" if abs(gap) <= RECONCILE_TOLERANCE
                 else ("#e67e22" if gap > 0 else "#f5c518"))

    st.markdown("### 🔍 Presence vs Tracked (today)")
    progress_bar(min(coverage, 1.0),
                 f"{min(coverage,1)*100:.0f}% of your presence time is accounted for in blocks",
                 bar_color)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Presence", fmt_hm(presence))
    with c2:
        st.metric("Tracked", fmt_hm(tracked))
    with c3:
        if gap > RECONCILE_TOLERANCE:
            st.metric("Unaccounted", fmt_hm(gap))
        elif gap < -RECONCILE_TOLERANCE:
            st.metric("Over-tracked", fmt_hm(-gap))
        else:
            st.metric("Difference", fmt_hm(abs(gap)))

    if gap > RECONCILE_TOLERANCE:
        result_card(f"<strong>{fmt_hm(gap)}</strong> of your day isn't in any block yet. "
                    f"That's the part you'd otherwise reconstruct from memory at month end. "
                    f"Use <em>Log a past block</em> above to fill it in while you still "
                    f"remember.", "#e67e22")
    elif gap < -RECONCILE_TOLERANCE:
        result_card(f"You've tracked <strong>{fmt_hm(-gap)}</strong> more than your presence "
                    f"time. Check for overlapping blocks, a timer left running, or an entry "
                    f"time that needs correcting.", "#f5c518")
    else:
        result_card("✅ Blocks and presence time line up. This day is timesheet-ready.",
                    "#2ecc71")

# ─── CALCULATOR ─────────────────────────────────────────────────────────────
def get_now() -> datetime:
    """Naive 'today at 1900-01-01' clock, so it can be compared with parsed times."""
    n = real_now()
    return n.replace(tzinfo=None, year=1900, month=1, day=1)

def run_calculator(entry, start_lunch, end_lunch, leave, now):
    presence = 0.0

    if leave:
        lunch_dur = (end_lunch - start_lunch) if (start_lunch and end_lunch) else timedelta(0)
        worked = leave - entry - lunch_dur
        deficit = WORKDAY - worked
        pct = worked / WORKDAY
        presence = worked.total_seconds()

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
            result_card(f"✅ Full day done. You worked <strong>{fmt_td(worked)}</strong>."
                        f"{extra}", "#2ecc71")
            coach_says(coach_msg("calc_final", FINAL_MSG))
        else:
            result_card(f"You worked <strong>{fmt_td(worked)}</strong> of 8h 00m, "
                        f"<strong style='color:#e67e22'>{fmt_td(deficit)} to go</strong>. "
                        f"No pressure, balance it tomorrow.", "#e67e22")
            coach_says(coach_msg("calc_short", SHORT_MSG))

    elif end_lunch and start_lunch:
        pre_lunch = start_lunch - entry
        lunch_dur = end_lunch - start_lunch
        worked_after = max(now - end_lunch, timedelta(0))
        total_worked = pre_lunch + worked_after
        remaining = max(WORKDAY - total_worked, timedelta(0))
        predicted_leave = end_lunch + (WORKDAY - pre_lunch)
        pct = total_worked / WORKDAY
        presence = total_worked.total_seconds()

        st.markdown("### 🍽️ Back from Lunch")
        live_stamp(now)
        coach_says(coach_msg("calc_afterlunch", AFTER_LUNCH_MSG))
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
        presence = worked_so_far.total_seconds()

        st.markdown("### 🌿 Lunch Break")
        live_stamp(now)
        coach_says(coach_msg("calc_lunch", LUNCH_START_MSG))
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
            st.markdown("<div style='color:#777;font-size:0.8rem;text-align:center'>"
                        "Leave at ↑</div>", unsafe_allow_html=True)
        with c2:
            time_badge("1-hour lunch", leave_60)
            st.markdown("<div style='color:#777;font-size:0.8rem;text-align:center'>"
                        "Leave at ↑</div>", unsafe_allow_html=True)

    else:
        worked_now = max(now - entry, timedelta(0))
        remaining_now = max(WORKDAY - worked_now, timedelta(0))
        overtime_now = max(worked_now - WORKDAY, timedelta(0))
        pct_now = worked_now / WORKDAY
        leave_30 = entry + WORKDAY + timedelta(minutes=30)
        leave_60 = entry + WORKDAY + timedelta(hours=1)
        presence = worked_now.total_seconds()

        st.markdown("### 🕐 Day in Progress")
        live_stamp(now)
        coach_says(coach_msg("calc_entry", ENTRY_MSG))
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
            st.markdown("<div style='color:#777;font-size:0.8rem;text-align:center'>"
                        "Leave at ↑</div>", unsafe_allow_html=True)
        with c2:
            time_badge("1-hour lunch", leave_60)
            st.markdown("<div style='color:#777;font-size:0.8rem;text-align:center'>"
                        "Leave at ↑</div>", unsafe_allow_html=True)

    st.markdown("---")
    render_reconciliation(presence)

def calculator_body(entry, start_lunch, end_lunch, leave):
    run_calculator(entry, start_lunch, end_lunch, leave, get_now())

# ─── FRAGMENTS ARE BUILT ONCE, NOT PER RERUN ────────────────────────────────
# Re-applying the decorator on every script run would register a new fragment
# (and a new auto-refresh schedule) each time, which compounds into a refresh
# storm that looks like an app stuck loading.
if HAS_FRAGMENT:
    live_card_auto = _FRAG(run_every="1s")(live_activity_card)
    calculator_auto = _FRAG(run_every="30s")(calculator_body)
else:
    live_card_auto = live_activity_card
    calculator_auto = calculator_body

def render_calculator():
    st.markdown("### 🧮 Workday Calculator")

    # Apply a queued value before the widget exists. Assigning to a widget key
    # after its widget has rendered would raise.
    if st.session_state.get("_pending_entry") is not None:
        st.session_state.calc_entry = st.session_state.pop("_pending_entry")

    suggestion = suggest_entry_time()
    if "calc_entry" not in st.session_state:
        st.session_state.calc_entry = suggestion or ""

    col_a, col_b = st.columns(2)
    with col_a:
        entry_raw = text_input("🕐 Entry time", key="calc_entry",
                               placeholder="08:30  /  8:30 AM  /  08:30:00")
        end_lunch_raw = text_input("🍽️ Lunch end (optional)", key="calc_lunch_end",
                                   placeholder="13:00")
    with col_b:
        start_lunch_raw = text_input("🌿 Lunch start (optional)", key="calc_lunch_start",
                                     placeholder="12:15")
        leave_raw = text_input("🚪 Actual leave (optional)", key="calc_leave",
                               placeholder="17:45")

    if suggestion and (entry_raw or "").strip() != suggestion:
        s1, _ = st.columns([2, 3])
        with s1:
            if button(f"Use first tracked block ({suggestion})",
                      use_container_width=True, key="use_suggested_entry"):
                st.session_state["_pending_entry"] = suggestion
                rerun_app()

    entry = parse_time(entry_raw)
    start_lunch = parse_time(start_lunch_raw)
    end_lunch = parse_time(end_lunch_raw)
    leave = parse_time(leave_raw)

    bad = [lbl for lbl, raw, val in [
        ("Entry", entry_raw, entry),
        ("Lunch start", start_lunch_raw, start_lunch),
        ("Lunch end", end_lunch_raw, end_lunch),
        ("Leave", leave_raw, leave),
    ] if raw and raw.strip() and val is None]

    if bad:
        st.error(f"Couldn't read: **{', '.join(bad)}**. "
                 f"Try formats like `08:30`, `8:30`, `08:30:00`, or `8:30 AM`.")
    elif not entry:
        st.markdown("<div style='text-align:center;padding:20px 0;color:#555;"
                    "font-family:Bebas Neue,sans-serif;font-size:1.2rem;letter-spacing:2px'>"
                    "Drop your entry time above and we'll map out your finish line."
                    "</div>", unsafe_allow_html=True)
    else:
        if (not leave) and HAS_FRAGMENT:
            calculator_auto(entry, start_lunch, end_lunch, leave)
        else:
            calculator_body(entry, start_lunch, end_lunch, leave)
            if not leave:
                if button("⟳  Refresh totals", key="calc_tick"):
                    rerun_app()

# ─── PAGE ───────────────────────────────────────────────────────────────────
st.markdown("<h1>⏱️ WORKDAY TRACKER</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;color:#8a8170;font-style:italic;font-size:0.95rem;"
            "font-family:Barlow,sans-serif;margin-top:0'>"
            "Track your focus, capture your hours, finish strong.</p>",
            unsafe_allow_html=True)

render_storage_bar()
st.markdown("---")
render_timer()
render_log()
st.markdown("---")
render_calculator()
