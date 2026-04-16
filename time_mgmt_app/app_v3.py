import streamlit as st
from datetime import datetime, timedelta
import random
 
st.set_page_config(
    page_title="⚗️ Jesse's Workday Calculator",
    page_icon="⚗️",
    layout="centered",
)
 
# ─── THEME ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Share+Tech+Mono&family=Barlow:ital,wght@0,400;0,600;1,400&display=swap');
 
/* ── Base ── */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background-color: #0e0e0e !important;
    color: #e8dcc8 !important;
}
[data-testid="stHeader"]            { background: transparent !important; }
[data-testid="stSidebar"]           { background: #111 !important; }
section.main > div                  { padding-top: 1.5rem; }
 
/* ── Typography ── */
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
 
/* ── Inputs ── */
input[type="text"] {
    background-color: #1a1a1a !important;
    color: #e8dcc8 !important;
    border: 1px solid #333 !important;
    border-radius: 4px !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 1.05rem !important;
    caret-color: #f5c518;
}
input[type="text"]:focus {
    border-color: #f5c518 !important;
    box-shadow: 0 0 0 2px rgba(245,197,24,0.15) !important;
}
label {
    color: #aaa !important;
    font-size: 0.85rem !important;
    letter-spacing: 1px;
    text-transform: uppercase;
}
[data-testid="stTextInput"] { margin-bottom: 0.3rem; }
 
/* ── Metrics ── */
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
 
/* ── Divider ── */
hr {
    border: none !important;
    border-top: 1px solid #2a2a2a !important;
    margin: 1.2rem 0 !important;
}
 
/* ── Errors ── */
[data-testid="stAlert"] {
    background: #1e0a0a !important;
    border-left: 4px solid #e74c3c !important;
    color: #e8dcc8 !important;
}
</style>
""", unsafe_allow_html=True)
 
# ─── MESSAGES ───────────────────────────────────────────────────────────────
 
ENTRY_MSG = [
    "Yo, you're finally here? Clock's ticking, don't act like you're staying longer than you have to, bitch. 💪",
    "Look who decided to show up. Time to grind — but trust me, we'll get you outta here real quick. 🏃",
    "Science, bitch. And by science I mean calculating your escape route. ⚗️",
    "Oh, you clocked in? Cool. Let's make sure you don't stick around here like a loser, bro. 😎",
    "You think this place deserves more of your time? Nah. Let's figure out when you can ghost this joint. 🚪",
    "Alright, you're here. Big whoop. Let's plan your escape before they suck your soul out. 💀",
    "Another day in this dump. Let's calculate how fast you can break outta here. 💸",
    "What's up, champ? Don't worry — we'll figure out when you can get the hell outta here. 🕛",
    "Yo, you clocked in. Cool. But don't get cozy, homie. This ain't your crib. 🕓",
]
 
LUNCH_START_MSG = [
    "Lunch already? Don't eat like a pig, fool. You still got work to pretend to do. 🍔",
    "Yo, it's lunch! Eat fast — don't act like you're on some gourmet vacation. Get back, pronto. 🌮",
    "Oh, lunch break? Better not take too long, or they'll think you're MIA, you slacker. ⏳",
    "Time for chow, huh? Don't overdo it — they're not paying you for a 3-course meal, dawg. 🍕",
    "Lunch time? Make it quick, fool. Ain't nobody got time for a midday nap afterward. 😴",
    "Bro, keep it light — I don't wanna hear you whining about feeling bloated on the back half. 🥪",
    "Grab a bite, but if you think you're chilling here all afternoon, you're dead wrong. 🍱",
]
 
AFTER_LUNCH_MSG = [
    "Lunch is over, my dude. Time to get back to the grind. No more slacking! 🕛",
    "Lunch break's done, champ. Clock's still ticking. Let's finish strong. 🍽️",
    "Hope you enjoyed that. Time to get back and pretend to work again. 😜",
    "Alright, enough slacking. Lunch is history. Let's finish this day without face-planting. 💤",
    "Lunch break is over, homie. Back to the grind like a true hustler. 💼",
    "No more chillin'. Lunch is history and the clock is still running. ⏳",
]
 
FINAL_MSG = [
    "Yo, you're done! Go home, sit your ass down, and chill, my dude. 🏡",
    "That's it, champ. You put in the time — now go grab a drink and forget this place exists. 🍻",
    "You survived. Now go home and pretend this day never happened. 😏",
    "What the hell are you still doing here? You're not earning extra brownie points — GTFO! 🏆",
    "And that's a wrap, bro. Now go binge something dumb on Netflix. 📺",
    "You done, superhero? Go home and do absolutely nothing. You've earned it, kinda. 🦸",
    "Yo, the day's over. Go disappear. This place ain't worth thinking about. 🌃",
    "Eight hours in the books. Science, bitch! Now go be a human being for once. ⚗️",
]
 
SHORT_MSG = [
    "Yo, you bounced early? That's straight-up weak, bro. Make it up tomorrow or face the music. 😬",
    "Cutting it short? Your boss is gonna notice, homie. That deficit don't just disappear. 🚨",
    "Look at you, leaving before your time. Real slick. Now cover that gap before it bites you. ⚠️",
    "Bro, you're short on hours. That's not how this works — that's not how ANY of this works. 🙄",
    "Short hours, big problems. Tomorrow you're making this right, capisce? 😤",
    "Yo, the clock don't lie and neither do I. You owe some time, fool. Pay up. ⏰",
    "Jesse Pinkman would be disappointed. Mr. White would be pissed. Make it right. 🧫",
]
 
# ─── HELPERS ────────────────────────────────────────────────────────────────
 
def parse_time(raw: str):
    """Accept many formats: 8:30, 08:30, 08:30:00, 8:30 AM, 8.30, etc."""
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
    if p >= 1.0: return "#2ecc71"
    if p >= 0.6: return "#f5c518"
    return "#e74c3c"
 
 
# ─── UI COMPONENTS ──────────────────────────────────────────────────────────
 
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
  <div style="color:#555;font-size:0.8rem;margin-top:4px;font-family:'Share Tech Mono',monospace">
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
 
 
def jesse_says(msg: str):
    st.markdown(f"""
<div style="border-left:3px solid #333;padding:8px 16px;margin:14px 0 6px 0;
color:#888;font-style:italic;font-family:'Barlow',sans-serif;font-size:0.95rem">
🎙️ &nbsp;{msg}
</div>""", unsafe_allow_html=True)
 
 
def time_badge(label: str, t: datetime, color: str = "#f5c518"):
    st.markdown(f"""
<div style="display:inline-block;background:#1a1a1a;border:1px solid {color};
border-radius:6px;padding:8px 16px;margin:4px 6px 4px 0;text-align:center;min-width:160px">
  <div style="color:#666;font-size:0.7rem;letter-spacing:1px;text-transform:uppercase;
  font-family:'Barlow',sans-serif">{label}</div>
  <div style="color:{color};font-family:'Bebas Neue',sans-serif;font-size:1.6rem;
  letter-spacing:2px">{t.strftime('%H:%M')}</div>
</div>""", unsafe_allow_html=True)
 
 
# ─── CALCULATOR LOGIC ───────────────────────────────────────────────────────
 
WORKDAY = timedelta(hours=8)
 
 
def run(entry, start_lunch, end_lunch, leave):
 
    # ══ STATE 4 — Leave time provided ═══════════════════════════════════════
    if leave:
        lunch_dur = (end_lunch - start_lunch) if (start_lunch and end_lunch) else timedelta(0)
        worked = leave - entry - lunch_dur
        deficit = WORKDAY - worked
        pct = worked / WORKDAY
 
        st.markdown("### 📊 Day Summary")
        progress_bar(pct, f"{min(pct,1)*100:.1f}% of 8-hour workday completed")
 
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("⏱️ Hours Worked", fmt_td(max(worked, timedelta(0))))
        with c2:
            st.metric("🍽️ Lunch", fmt_td(lunch_dur) if lunch_dur.total_seconds() > 0 else "—")
        with c3:
            if deficit.total_seconds() > 0:
                st.metric("⚠️ Deficit", fmt_td(deficit))
            else:
                st.metric("✅ Surplus", fmt_td(-deficit))
 
        st.markdown("")
 
        if worked >= WORKDAY:
            result_card(
                f"✅ Full day done — you worked <strong>{fmt_td(worked)}</strong>. "
                f"{'Banked <strong>' + fmt_td(-deficit) + '</strong> extra. Not bad.' if deficit.total_seconds() < 0 else 'Right on the money.'}",
                "#2ecc71"
            )
            jesse_says(random.choice(FINAL_MSG))
        else:
            result_card(
                f"⚠️ Only worked <strong>{fmt_td(worked)}</strong> out of 8h 00m — "
                f"you're <strong style='color:#e74c3c'>{fmt_td(deficit)} short</strong>. "
                f"Make it up tomorrow, homie.",
                "#e74c3c"
            )
            jesse_says(random.choice(SHORT_MSG))
 
    # ══ STATE 3 — Back from lunch ════════════════════════════════════════════
    elif end_lunch and start_lunch:
        pre_lunch = start_lunch - entry
        lunch_dur = end_lunch - start_lunch
        remaining = WORKDAY - pre_lunch
        predicted_leave = end_lunch + remaining
        pct = pre_lunch / WORKDAY
 
        st.markdown("### 🍽️ Back from Lunch")
        jesse_says(random.choice(AFTER_LUNCH_MSG))
        progress_bar(pct, f"{pct*100:.1f}% done before lunch — {fmt_td(remaining)} still to go")
 
        c1, c2 = st.columns(2)
        with c1:
            st.metric("⏱️ Worked (pre-lunch)", fmt_td(pre_lunch))
        with c2:
            st.metric("⏳ Remaining", fmt_td(remaining))
 
        st.markdown("")
        result_card(
            f"🍽️ Lunch was <strong>{fmt_td(lunch_dur)}</strong>. "
            f"Target leave: "
        )
        time_badge("Leave at", predicted_leave)
 
    # ══ STATE 2 — At lunch ═══════════════════════════════════════════════════
    elif start_lunch:
        worked_so_far = start_lunch - entry
        remaining_after_lunch = WORKDAY - worked_so_far
        leave_30 = start_lunch + remaining_after_lunch + timedelta(minutes=30)
        leave_60 = start_lunch + remaining_after_lunch + timedelta(hours=1)
        pct = worked_so_far / WORKDAY
 
        st.markdown("### 🌮 Lunch Break")
        jesse_says(random.choice(LUNCH_START_MSG))
        progress_bar(pct, f"{pct*100:.1f}% of workday done — eating on company time now")
 
        st.metric("⏱️ Worked so far", fmt_td(worked_so_far))
        st.markdown("")
 
        result_card("Depending on your lunch:")
        c1, c2 = st.columns(2)
        with c1:
            time_badge("30-min lunch", leave_30)
            st.markdown("<div style='color:#666;font-size:0.8rem;text-align:center'>Leave at ↑</div>", unsafe_allow_html=True)
        with c2:
            time_badge("1-hour lunch", leave_60)
            st.markdown("<div style='color:#666;font-size:0.8rem;text-align:center'>Leave at ↑</div>", unsafe_allow_html=True)
 
    # ══ STATE 1 — Entry only ════════════════════════════════════════════════
    else:
        leave_30 = entry + WORKDAY + timedelta(minutes=30)
        leave_60 = entry + WORKDAY + timedelta(hours=1)
 
        st.markdown("### 🕐 Day Started")
        jesse_says(random.choice(ENTRY_MSG))
        progress_bar(0, "0% — just clocked in. Long road ahead, homie.")
 
        result_card("Depending on your lunch:")
        c1, c2 = st.columns(2)
        with c1:
            time_badge("30-min lunch", leave_30)
            st.markdown("<div style='color:#666;font-size:0.8rem;text-align:center'>Leave at ↑</div>", unsafe_allow_html=True)
        with c2:
            time_badge("1-hour lunch", leave_60)
            st.markdown("<div style='color:#666;font-size:0.8rem;text-align:center'>Leave at ↑</div>", unsafe_allow_html=True)
 
 
# ─── PIXEL ART ──────────────────────────────────────────────────────────────
 
# Each row must be exactly 16 characters wide. '.' = transparent.
WALTER_ROWS = [
    "....KKKKKKKK....",  # hat top
    "...KKKKKKKKKK...",  # hat
    "..KKKKKKKKKKKK..",  # hat brim
    "....SSSSSSSS....",  # forehead (bald)
    "...SSSSSSSSSS...",  # face
    "...SGWEESWEGS...",  # glasses: G=frame W=white E=pupil
    "...SGGGGGGGGS...",  # glasses bottom bar
    "...SSSSSSSSSS...",  # mid face
    "....SSSDSSSSS...",  # nose
    "....SDDDDDSS....",  # mustache / mouth
    "....SDDDDDSS....",  # goatee
    ".....SSSSSS.....",  # chin
    ".....SSSS.......",  # neck
    "....YYYYYYYY....",  # collar
    "...YYYYYYYYYY...",  # shoulders
    "...YYYYYYYYYY...",  # body
    "...YYYYYYYYYY...",
    "...YYYYYYYYYY...",
    "...YYYYYYYYYY...",
    "....YY....YY....",  # legs
    "....YY....YY....",
    "....KK....KK....",  # boots
]
 
JESSE_ROWS = [
    "....BBBBBBBB....",  # hair top
    "...BBBBBBBBBB...",  # hair
    "..BBSSSSSSSSBB..",  # hair sides + face
    "..BSSSSSSSSSB...",  # face
    "...SSSSSSSSSS...",  # face
    "...SWESSSWESS...",  # eyes: W=white E=pupil
    "...SSSSSSSSSS...",  # face
    "....SSSDSSSSS...",  # nose
    "....SSDDDSSSS...",  # mouth
    "....SSSSSSSS....",  # chin
    ".....SSSSSS.....",  # lower chin
    ".....SSSS.......",  # neck
    "...RRRRRRRRRR...",  # hoodie collar
    "..RRRRRRRRRRRR..",  # hoodie
    "..RRRRRRRRRRRR..",
    "..RRRRRRRRRRRR..",
    "..RRRRRRRRRRRR..",
    "..RRRRRRRRRRRR..",
    "..RRRRRRRRRRRR..",
    "...NN......NN...",  # jeans
    "...NN......NN...",
    "...KK......KK...",  # boots
]
 
WALTER_PALETTE = {
    'K': '#1c1c1c',   # hat / boots
    'S': '#f0b87a',   # skin
    'G': '#aaaaaa',   # glasses frame
    'W': '#eeeeee',   # eye white
    'E': '#2a1505',   # pupil
    'D': '#8a7a5a',   # goatee / shadow
    'Y': '#f5c518',   # hazmat yellow
}
 
JESSE_PALETTE = {
    'B': '#3d2010',   # hair
    'S': '#f0b87a',   # skin
    'W': '#eeeeee',   # eye white
    'E': '#2a1505',   # pupil
    'D': '#c07050',   # mouth
    'R': '#b82020',   # red hoodie
    'N': '#1a2d52',   # jeans
    'K': '#111111',   # boots
}
 
 
def make_pixel_svg(rows, palette, px=11):
    rects = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in palette:
                c = palette[ch]
                rects.append(
                    f'<rect x="{x*px}" y="{y*px}" '
                    f'width="{px}" height="{px}" fill="{c}"/>'
                )
    w = max(len(r) for r in rows) * px
    h = len(rows) * px
    inner = "".join(rects)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w}" height="{h}" shape-rendering="crispEdges">'
        f'{inner}</svg>'
    )
 
 
# ─── PAGE ───────────────────────────────────────────────────────────────────
 
st.markdown("<h1>⚗️ JESSE'S WORKDAY<br>CALCULATOR ⚗️</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;color:#555;font-style:italic;font-size:0.95rem;"
    "font-family:Barlow,sans-serif;margin-top:0'>Yeah, science! ...of getting outta work on time, bitch.</p>",
    unsafe_allow_html=True
)
 
# Pixel art duo
_w_svg = make_pixel_svg(WALTER_ROWS, WALTER_PALETTE, px=11)
_j_svg = make_pixel_svg(JESSE_ROWS,  JESSE_PALETTE,  px=11)
st.markdown(f"""
<div style="display:flex;justify-content:center;align-items:flex-end;
            gap:32px;margin:18px 0 6px 0">
  <div style="text-align:center">
    {_w_svg}
    <div style="color:#555;font-size:0.7rem;letter-spacing:2px;margin-top:5px;
    font-family:'Share Tech Mono',monospace">MR. WHITE</div>
  </div>
  <div style="text-align:center">
    {_j_svg}
    <div style="color:#555;font-size:0.7rem;letter-spacing:2px;margin-top:5px;
    font-family:'Share Tech Mono',monospace">JESSE</div>
  </div>
</div>
""", unsafe_allow_html=True)
 
st.markdown("---")
 
# Inputs in a 2-column grid
col_a, col_b = st.columns(2)
with col_a:
    entry_raw      = st.text_input("🕐 Entry time",              placeholder="08:30  /  8:30 AM  /  08:30:00")
    end_lunch_raw  = st.text_input("🍽️ Lunch end (optional)",    placeholder="13:00")
with col_b:
    start_lunch_raw = st.text_input("🌮 Lunch start (optional)", placeholder="12:15")
    leave_raw       = st.text_input("🚪 Actual leave (optional)", placeholder="17:45")
 
st.markdown("---")
 
# Parse & validate
entry       = parse_time(entry_raw)
start_lunch = parse_time(start_lunch_raw)
end_lunch   = parse_time(end_lunch_raw)
leave       = parse_time(leave_raw)
 
bad = [(lbl, raw) for lbl, raw, val in [
    ("Entry",       entry_raw,       entry),
    ("Lunch start", start_lunch_raw, start_lunch),
    ("Lunch end",   end_lunch_raw,   end_lunch),
    ("Leave",       leave_raw,       leave),
] if raw and raw.strip() and val is None]
 
if bad:
    fields = ", ".join(f[0] for f in bad)
    st.error(f"⚠️ Couldn't read: **{fields}**. "
             f"Try formats like `08:30`, `8:30`, `08:30:00`, or `8:30 AM`.")
elif not entry:
    st.markdown(
        "<div style='text-align:center;padding:28px 0;color:#444;"
        "font-family:Bebas Neue,sans-serif;font-size:1.3rem;letter-spacing:2px'>"
        "👆 YO — DROP YOUR ENTRY TIME UP THERE AND LET'S FIGURE OUT YOUR ESCAPE PLAN."
        "</div>",
        unsafe_allow_html=True
    )
else:
    run(entry, start_lunch, end_lunch, leave)
