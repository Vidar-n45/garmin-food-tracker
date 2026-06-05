import streamlit as st
import pandas as pd
import json
import os
from datetime import date, timedelta
from garminconnect import Garmin

# ─── config ───────────────────────────────────────────────
DATA_FILE = "food_log.json"
TARGETS = {"cal": 1450, "prot": 110, "carb": 130, "fat": 50}

st.set_page_config(page_title="Health Tracker", page_icon="🏃", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500&display=swap');
html, body, [class*="css"], .stMarkdown, .stMetric, .stButton, input, select, textarea {
    font-family: 'Sarabun', sans-serif !important;
}
h1, h2, h3, h4 { font-weight: 500 !important; }
p, div, span, label { font-weight: 300 !important; }
.stMetric label { font-size: 13px !important; letter-spacing: .03em; }
</style>
""", unsafe_allow_html=True)

# ─── load / save food log ──────────────────────────────────
def load_log():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_log(log):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

# ─── garmin ───────────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_garmin(email, password, date_str):
    try:
        client = Garmin(email, password)
        client.login()
        steps_data  = client.get_steps_data(date_str)
        sleep_data  = client.get_sleep_data(date_str)
        hr_data     = client.get_heart_rates(date_str)
        bb_data     = client.get_body_battery(date_str)
        stats       = client.get_stats(date_str)
        activities  = client.get_activities_by_date(date_str, date_str)
        dto = sleep_data.get("dailySleepDTO") or {}
        return {
            "steps": stats.get("totalSteps") or 0,
            "tdee":  stats.get("totalKilocalories") or 0,
            "active_cal": stats.get("activeKilocalories") or 0,
            "resting_hr": stats.get("restingHeartRate") or 0,
            "stress_avg": stats.get("averageStressLevel") or 0,
            "body_battery": bb_data[-1]["charged"] if bb_data else 0,
            "sleep_duration": (dto.get("sleepTimeSeconds") or 0) // 60,
            "sleep_deep":  (dto.get("deepSleepSeconds") or 0) // 60,
            "sleep_rem":   (dto.get("remSleepSeconds") or 0) // 60,
            "sleep_light": (dto.get("lightSleepSeconds") or 0) // 60,
            "hrv":  dto.get("avgOvernightHrv") or 0,
            "spo2": dto.get("averageSpO2Value") or 0,
            "activities": [
                {
                    "name": a.get("activityName", ""),
                    "duration_min": round(a.get("duration", 0) / 60),
                    "calories": a.get("calories", 0),
                    "avg_hr": a.get("averageHR", 0),
                }
                for a in activities
            ],
        }
    except Exception as e:
        return {"error": str(e)}

# ─── nutrition lookup: local DB → Open Food Facts → fallback ──
import requests
import urllib.parse

FOOD_DB = {
    "ข้าวกล้อง": {"kcal": 1.11, "prot": 0.026, "carb": 0.23, "fat": 0.009},
    "ข้าวขาว":   {"kcal": 1.30, "prot": 0.027, "carb": 0.28, "fat": 0.003},
    "ไข่ต้ม":    {"kcal": 1.55, "prot": 0.125, "carb": 0.011,"fat": 0.107},
    "ไข่ดาว":    {"kcal": 1.96, "prot": 0.134, "carb": 0.001,"fat": 0.147},
    "อกไก่":     {"kcal": 1.65, "prot": 0.310, "carb": 0.0,  "fat": 0.036},
    "ปลาแซลมอน": {"kcal": 2.08, "prot": 0.200, "carb": 0.0,  "fat": 0.130},
    "บรอกโคลี":  {"kcal": 0.34, "prot": 0.028, "carb": 0.065,"fat": 0.004},
    "นัตโต้":    {"kcal": 2.12, "prot": 0.176, "carb": 0.141,"fat": 0.110},
    "กิมจิ":     {"kcal": 0.19, "prot": 0.015, "carb": 0.031,"fat": 0.006},
    "โยเกิร์ต":  {"kcal": 0.97, "prot": 0.090, "carb": 0.038,"fat": 0.050},
    "อัลมอนด์":  {"kcal": 5.79, "prot": 0.213, "carb": 0.216,"fat": 0.499},
    "กล้วย":     {"kcal": 0.89, "prot": 0.011, "carb": 0.229,"fat": 0.003},
    "แอปเปิ้ล":  {"kcal": 0.52, "prot": 0.003, "carb": 0.138,"fat": 0.002},
    "เต้าหู้":   {"kcal": 0.76, "prot": 0.081, "carb": 0.019,"fat": 0.046},
    "ผักสลัด":   {"kcal": 0.15, "prot": 0.013, "carb": 0.028,"fat": 0.002},
    # เครื่องดื่ม (ต่อ ml)
    "อเมริกาโน่":  {"kcal": 0.05, "prot": 0.001, "carb": 0.005,"fat": 0.0},
    "americano":   {"kcal": 0.05, "prot": 0.001, "carb": 0.005,"fat": 0.0},
    "coffee":      {"kcal": 0.05, "prot": 0.001, "carb": 0.005,"fat": 0.0},
    "espresso":    {"kcal": 0.09, "prot": 0.002, "carb": 0.008,"fat": 0.0},
    "กาแฟดำ":     {"kcal": 0.02, "prot": 0.001, "carb": 0.003,"fat": 0.0},
    "กาแฟนม":     {"kcal": 0.46, "prot": 0.015, "carb": 0.055,"fat": 0.018},
    "กาแฟเอสเย็น": {"kcal": 0.38, "prot": 0.010, "carb": 0.060,"fat": 0.010},
    "ลาเต้":      {"kcal": 0.54, "prot": 0.033, "carb": 0.055,"fat": 0.020},
    "นมสด":       {"kcal": 0.61, "prot": 0.032, "carb": 0.047,"fat": 0.033},
    "น้ำเปล่า":   {"kcal": 0.0,  "prot": 0.0,   "carb": 0.0,  "fat": 0.0},
}

@st.cache_data(ttl=86400)
def search_open_food_facts(name):
    """ค้นหาจาก Open Food Facts API — cache ไว้ 24 ชม."""
    try:
        query = urllib.parse.quote(name)
        url = f"https://world.openfoodfacts.org/cgi/search.pl?search_terms={query}&search_simple=1&action=process&json=1&page_size=5&fields=product_name,nutriments"
        r = requests.get(url, timeout=5)
        products = r.json().get("products", [])
        for p in products:
            n = p.get("nutriments", {})
            kcal = n.get("energy-kcal_100g") or n.get("energy_100g", 0)
            if kcal and float(kcal) > 0:
                return {
                    "kcal":  float(kcal) / 100,
                    "prot":  float(n.get("proteins_100g") or 0) / 100,
                    "carb":  float(n.get("carbohydrates_100g") or 0) / 100,
                    "fat":   float(n.get("fat_100g") or 0) / 100,
                    "source": p.get("product_name", name),
                }
    except Exception:
        pass
    return None

def lookup_nutrition(name, grams):
    # 1) local DB ก่อน
    name_lower = name.lower()
    for key, val in FOOD_DB.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return {
                "kcal": round(val["kcal"] * grams),
                "prot": round(val["prot"] * grams, 1),
                "carb": round(val["carb"] * grams, 1),
                "fat":  round(val["fat"]  * grams, 1),
                "source": "local DB",
            }
    # 2) Open Food Facts
    off = search_open_food_facts(name)
    if off:
        return {
            "kcal": round(off["kcal"] * grams),
            "prot": round(off["prot"] * grams, 1),
            "carb": round(off["carb"] * grams, 1),
            "fat":  round(off["fat"]  * grams, 1),
            "source": f"Open Food Facts: {off['source']}",
        }
    # 3) fallback
    return {
        "kcal": round(grams * 2), "prot": round(grams * 0.05, 1),
        "carb": round(grams * 0.15, 1), "fat": round(grams * 0.05, 1),
        "source": "ประมาณค่า",
    }

# ─── sidebar: settings ────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ ตั้งค่า")
    garmin_email    = st.text_input("Garmin email", type="default")
    garmin_password = st.text_input("Garmin password", type="password")
    st.markdown("---")
    st.markdown("**เป้าหมาย macro รายวัน**")
    TARGETS["cal"]  = st.number_input("แคลอรี่ (kcal)", value=1450, step=50)
    TARGETS["prot"] = st.number_input("โปรตีน (g)",     value=110,  step=5)
    TARGETS["carb"] = st.number_input("คาร์บ (g)",      value=130,  step=5)
    TARGETS["fat"]  = st.number_input("ไขมัน (g)",      value=50,   step=5)

# ─── date picker ──────────────────────────────────────────
col_d1, col_d2, col_d3 = st.columns([1, 2, 1])
with col_d1:
    if st.button("◀ วันก่อน"):
        if "selected_date" not in st.session_state:
            st.session_state.selected_date = date.today()
        st.session_state.selected_date -= timedelta(days=1)
with col_d2:
    selected = st.date_input("วันที่", value=st.session_state.get("selected_date", date.today()), label_visibility="collapsed")
    st.session_state.selected_date = selected
with col_d3:
    if st.button("วันถัดไป ▶"):
        st.session_state.selected_date = st.session_state.get("selected_date", date.today()) + timedelta(days=1)

date_str = str(st.session_state.get("selected_date", date.today()))

# ─── tabs ─────────────────────────────────────────────────
tab_food, tab_garmin, tab_analysis = st.tabs(["🍽️ บันทึกอาหาร", "⌚ Garmin data", "📊 วิเคราะห์"])

# ═══════════════════════════════════════════════════════════
# TAB 1 — FOOD LOG
# ═══════════════════════════════════════════════════════════
with tab_food:
    log = load_log()
    day_log = log.get(date_str, [])

    # totals
    total = {"kcal": 0, "prot": 0.0, "carb": 0.0, "fat": 0.0}
    for item in day_log:
        total["kcal"] += item["kcal"]
        total["prot"] += item["prot"]
        total["carb"] += item["carb"]
        total["fat"]  += item["fat"]

    # macro summary cards
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("แคลอรี่", f"{total['kcal']} kcal", f"เป้า {TARGETS['cal']} kcal")
    c2.metric("โปรตีน",  f"{total['prot']:.0f} g",  f"เป้า {TARGETS['prot']} g")
    c3.metric("คาร์บ",   f"{total['carb']:.0f} g",  f"เป้า {TARGETS['carb']} g")
    c4.metric("ไขมัน",   f"{total['fat']:.0f} g",   f"เป้า {TARGETS['fat']} g")

    # progress bars
    for label, key, color in [("แคลอรี่","cal","blue"),("โปรตีน","prot","green"),("คาร์บ","carb","orange"),("ไขมัน","fat","red")]:
        val = total["kcal"] if key == "cal" else total[key[:4] if key != "cal" else "kcal"]
        pct = min(1.0, val / TARGETS[key])
        st.progress(pct, text=f"{label}: {val:.0f} / {TARGETS[key]}")

    st.markdown("---")

    # add food form
    with st.form("add_food", clear_on_submit=True):
        st.markdown("#### เพิ่มรายการอาหาร")
        fc1, fc2, fc3 = st.columns([3, 1, 1])
        food_name  = fc1.text_input("ชื่ออาหาร", placeholder="เช่น อกไก่, ข้าวกล้อง, นัตโต้")
        food_grams = fc2.number_input("กรัม", min_value=1, max_value=2000, value=100)
        food_meal  = fc3.selectbox("มื้อ", ["เช้า", "กลางวัน", "เย็น", "ของว่าง"])
        submitted  = st.form_submit_button("➕ เพิ่ม", use_container_width=True)

    if submitted and food_name:
        macros = lookup_nutrition(food_name, food_grams)
        entry = {"name": food_name, "grams": food_grams, "meal": food_meal, **macros}
        day_log.append(entry)
        log[date_str] = day_log
        save_log(log)
        src = macros.pop("source", "")
        st.success(f"เพิ่ม {food_name} {food_grams}g — {macros['kcal']} kcal · P {macros['prot']}g · C {macros['carb']}g · F {macros['fat']}g  ({src})")
        st.rerun()

    # food list
    if day_log:
        st.markdown("#### รายการวันนี้")
        for i, item in enumerate(day_log):
            col_n, col_g, col_m, col_k, col_p, col_c, col_f, col_del = st.columns([3, 1, 1, 1, 1, 1, 1, 0.5])
            col_n.write(f"**{item['name']}**")
            col_g.write(f"{item['grams']}g")
            col_m.write(item['meal'])
            col_k.write(f"{item['kcal']} kcal")
            col_p.write(f"P {item['prot']}g")
            col_c.write(f"C {item['carb']}g")
            col_f.write(f"F {item['fat']}g")
            if col_del.button("🗑", key=f"del_{i}"):
                day_log.pop(i)
                log[date_str] = day_log
                save_log(log)
                st.rerun()
    else:
        st.info("ยังไม่มีรายการ — เพิ่มอาหารด้านบน")

    # energy balance
    if garmin_email:
        g = fetch_garmin(garmin_email, garmin_password, date_str)
        if "error" not in g:
            tdee = g["tdee"]
            diff = total["kcal"] - tdee
            st.markdown("---")
            st.markdown("#### Energy balance")
            b1, b2, b3 = st.columns(3)
            b1.metric("กินเข้า",           f"{total['kcal']} kcal")
            b2.metric("เผาผลาญ (Garmin)",  f"{tdee} kcal")
            b3.metric("Deficit / Surplus",  f"{diff:+} kcal", delta_color="inverse")

# ═══════════════════════════════════════════════════════════
# TAB 2 — GARMIN
# ═══════════════════════════════════════════════════════════
with tab_garmin:
    if not garmin_email:
        st.info("ใส่ Garmin email/password ในแถบซ้ายก่อนนะคะ")
    else:
        with st.spinner("กำลังดึงข้อมูลจาก Garmin..."):
            g = fetch_garmin(garmin_email, garmin_password, date_str)

        if "error" in g:
            st.error(f"เชื่อมต่อไม่ได้: {g['error']}")
        else:
            # steps & calories
            st.markdown("#### 👟 Steps & Calories")
            gc1, gc2, gc3, gc4 = st.columns(4)
            gc1.metric("Steps",       f"{g['steps']:,}")
            gc2.metric("TDEE",        f"{g['tdee']:,} kcal")
            gc3.metric("Active cal",  f"{g['active_cal']:,} kcal")
            gc4.metric("Resting HR",  f"{g['resting_hr']} bpm")

            st.markdown("---")

            # sleep
            st.markdown("#### 🌙 การนอน")
            sc1, sc2, sc3, sc4, sc5 = st.columns(5)
            total_sleep_h = g['sleep_duration'] // 60
            total_sleep_m = g['sleep_duration'] % 60
            sc1.metric("รวม",        f"{total_sleep_h}h {total_sleep_m}m")
            sc2.metric("Deep",       f"{g['sleep_deep']} min")
            sc3.metric("REM",        f"{g['sleep_rem']} min")
            sc4.metric("HRV",        f"{g['hrv']} ms")
            sc5.metric("SpO₂",       f"{g['spo2']}%")

            sleep_df = pd.DataFrame({
                "stage": ["Deep", "REM", "Light"],
                "minutes": [g['sleep_deep'], g['sleep_rem'], g['sleep_light']]
            })
            st.bar_chart(sleep_df.set_index("stage"))

            st.markdown("---")

            # body battery & stress
            st.markdown("#### ⚡ Body Battery & Stress")
            bb1, bb2 = st.columns(2)
            bb1.metric("Body Battery", f"{g['body_battery']} / 100")
            bb2.metric("Stress avg",   f"{g['stress_avg']}")

            st.markdown("---")

            # workouts
            st.markdown("#### 🏋️ Workouts")
            if g["activities"]:
                for act in g["activities"]:
                    ac1, ac2, ac3, ac4 = st.columns(4)
                    ac1.write(f"**{act['name']}**")
                    ac2.write(f"⏱ {act['duration_min']} min")
                    ac3.write(f"🔥 {act['calories']} kcal")
                    ac4.write(f"💓 avg {act['avg_hr']} bpm")
            else:
                st.info("ไม่มี workout วันนี้")

# ═══════════════════════════════════════════════════════════
# TAB 3 — ANALYSIS (7 days)
# ═══════════════════════════════════════════════════════════
with tab_analysis:
    log = load_log()
    days_back = 7
    rows = []
    for i in range(days_back - 1, -1, -1):
        d = str(date.today() - timedelta(days=i))
        entries = log.get(d, [])
        total_cal  = sum(e["kcal"] for e in entries)
        total_prot = sum(e["prot"] for e in entries)
        total_carb = sum(e["carb"] for e in entries)
        total_fat  = sum(e["fat"]  for e in entries)
        rows.append({"วันที่": d, "kcal": total_cal, "โปรตีน": total_prot,
                     "คาร์บ": total_carb, "ไขมัน": total_fat})

    df = pd.DataFrame(rows).set_index("วันที่")

    st.markdown("#### แคลอรี่ 7 วัน")
    st.bar_chart(df["kcal"])

    st.markdown("#### Macros 7 วัน")
    st.line_chart(df[["โปรตีน", "คาร์บ", "ไขมัน"]])

    st.markdown("#### ตารางข้อมูล")
    st.dataframe(df, use_container_width=True)

    # simple insights
    st.markdown("#### Insights")
    avg_cal  = df["kcal"].mean()
    avg_prot = df["โปรตีน"].mean()
    days_under_prot = (df["โปรตีน"] < TARGETS["prot"]).sum()

    if avg_cal < TARGETS["cal"] * 0.9:
        st.warning(f"⚠️ แคลอรี่เฉลี่ย 7 วัน ({avg_cal:.0f} kcal) ต่ำกว่าเป้าหมายมาก — ระวัง deficit เกิน")
    elif avg_cal > TARGETS["cal"] * 1.1:
        st.warning(f"⚠️ แคลอรี่เฉลี่ย 7 วัน ({avg_cal:.0f} kcal) เกินเป้าหมาย")
    else:
        st.success(f"✅ แคลอรี่เฉลี่ย 7 วัน ({avg_cal:.0f} kcal) อยู่ในเป้าหมาย")

    if days_under_prot >= 4:
        st.warning(f"⚠️ โปรตีนต่ำกว่าเป้า {days_under_prot} ใน 7 วัน — เฉลี่ย {avg_prot:.0f}g/วัน")
    else:
        st.success(f"✅ โปรตีนเฉลี่ย {avg_prot:.0f}g/วัน — ดีค่ะ")