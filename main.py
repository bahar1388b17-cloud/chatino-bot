import sqlite3
import requests
import json
import time
import os
from dotenv import load_dotenv

# بارگذاری تنظیمات امنیتی
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "70337956:eC-y0UOWafAomeWG-gZLqjKgXGU22jIJxTM")
API_URL = f"https://bot.splus.ir/bot{TOKEN}/"

# مدیریت اتصال دیتابیس
def get_db():
    conn = sqlite3.connect("chatino_pro.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # جدول کاربران
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        step TEXT DEFAULT 'START',
        photo TEXT DEFAULT 'NoPhoto',
        name TEXT,
        gender TEXT,
        age INTEGER,
        province TEXT,
        city TEXT,
        coins INTEGER DEFAULT 5,
        is_vip INTEGER DEFAULT 0,
        reports INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0,
        inviter_id TEXT
    )
    """)

    # جدول چت‌های فعال
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS active_chats (
        user_a TEXT PRIMARY KEY,
        user_b TEXT
    )
    """)

    # جدول صف انتظار چت
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS queue (
        user_id TEXT PRIMARY KEY,
        gender_pref TEXT DEFAULT 'ANY',
        province_pref TEXT DEFAULT 'ANY',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # جدول بلاک‌های شخصی
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS personal_blocks (
        blocker_id TEXT,
        blocked_id TEXT,
        PRIMARY KEY (blocker_id, blocked_id)
    )
    """)
    conn.commit()
    conn.close()

init_db()

# متد ارسال پیام جامع
def send_message(to_user, text=None, keyboard=None, file_id=None, msg_type="text"):
    payload = {"to": to_user}
    if text:
        payload["body"] = text
    if keyboard:
        payload["keyboard"] = keyboard
    if file_id:
        payload["fileId"] = file_id
        payload["type"] = msg_type

    try:
        res = requests.post(API_URL + "sendMessage", json=payload, timeout=8)
        return res.json()
    except Exception as e:
        print(f"❌ خطا در ارسال پیام به {to_user}: {e}")
        return None

def get_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def get_partner(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_b FROM active_chats WHERE user_a = ? UNION SELECT user_a FROM active_chats WHERE user_b = ?", (user_id, user_id))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def is_personally_blocked(user1, user2):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM personal_blocks WHERE (blocker_id = ? AND blocked_id = ?) OR (blocker_id = ? AND blocked_id = ?)", (user1, user2, user2, user1))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def send_main_menu(user_id, text_prefix=""):
    msg = (text_prefix + ("\n\n" if text_prefix else "") + 
           "✨ **به منوی اصلی ربات چت ناشناس «چتینو» خوش آمدید!** ✨\n\n"
           "💬 یک بخش را برای شروع گفتگو انتخاب کنید:")
    keyboard = [
        ["🎲 چت ناشناس (رایگان)", "🏙 چت استانی (رایگان)"],
        ["👫 چت با دختر (VIP)", "👦 چت با پسر (VIP)"],
        ["💰 سکه رایگان و خرید شارژ", "👤 پروفایل من"],
        ["🛡 پشتیبانی و قوانین"]
    ]
    send_message(user_id, text=msg, keyboard=keyboard)

def handle_message(user_id, text, msg_type="text", file_id=None, start_param=None):
    user = get_user(user_id)
    conn = get_db()
    cursor = conn.cursor()

    # ۱. ثبت‌نام کاربر جدید
    if not user:
        inviter = start_param if start_param else None
        cursor.execute("INSERT INTO users (user_id, step, inviter_id) VALUES (?, 'WAITING_PHOTO', ?)", (user_id, inviter))
        conn.commit()
        conn.close()
        
        welcome_text = (
            "سلام دوست من! 🌸\n"
            "به بزرگ‌ترین جامعه چت ناشناس **«چتینو»** خوش آمدی! ✨\n\n"
            "📸 لطفاً یک **عکس پروفایل** برام بفرست یا دکمه «بعداً می‌گذارم» رو بزن:"
        )
        send_message(user_id, text=welcome_text, keyboard=[["بعداً می‌گذارم"]])
        return

    step = user["step"]
    coins = user["coins"]
    is_blocked = user["is_blocked"]

    # ۲. حساب مسدود شده
    if is_blocked:
        if text == "🔓 پرداخت جریمه و رفع مسدودی":
            if coins >= 10:
                cursor.execute("UPDATE users SET coins = coins - 10, is_blocked = 0, reports = 0 WHERE user_id = ?", (user_id,))
                conn.commit()
                conn.close()
                send_main_menu(user_id, "🎉 **حساب شما رفع مسدودی شد!** لطفاً قوانین را رعایت کنید.")
            else:
                conn.close()
                send_message(user_id, text=f"❌ موجودی سکه کافی نیست! نیاز به ۱۰ سکه دارید.\n💰 موجودی فعلی: {coins} سکه")
        else:
            conn.close()
            send_message(user_id, text="⛔ حساب شما به دلیل ۳ گزارش مسدود شده است.", keyboard=[["🔓 پرداخت جریمه و رفع مسدودی"], ["💰 سکه رایگان و خرید شارژ"]])
        return

    # ۳. طی مراحل ثبت‌نام (Onboarding)
    if step == 'WAITING_PHOTO':
        photo_val = file_id if msg_type == 'photo' else 'NoPhoto'
        cursor.execute("UPDATE users SET photo = ?, step = 'WAITING_NAME' WHERE user_id = ?", (photo_val, user_id))
        conn.commit()
        conn.close()
        send_message(user_id, text="✏️ عالیه! حالا **اسم یا نام مستعارت** رو برام بنویس:")
        return

    elif step == 'WAITING_NAME':
        cursor.execute("UPDATE users SET name = ?, step = 'WAITING_GENDER' WHERE user_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        send_message(user_id, text="👤 **جنسیت** خودت رو مشخص کن:", keyboard=[["دختر 👱‍♀️", "پسر 👦"]])
        return

    elif step == 'WAITING_GENDER':
        gender_val = "دختر" if "دختر" in text else "پسر"
        cursor.execute("UPDATE users SET gender = ?, step = 'WAITING_AGE' WHERE user_id = ?", (gender_val, user_id))
        conn.commit()
        conn.close()
        send_message(user_id, text="🎂 **چند سالته؟** (لطفاً عدد وارد کن):")
        return

    elif step == 'WAITING_AGE':
        age_num = int(text) if text and text.isdigit() else 18
        cursor.execute("UPDATE users SET age = ?, step = 'WAITING_PROVINCE' WHERE user_id = ?", (age_num, user_id))
        conn.commit()
        conn.close()
        prov_kb = [["تهران", "خراسان رضوی", "اصفهان"], ["فارس", "خوزستان", "آذربایجان شرقی"], ["سایر استان‌ها"]]
        send_message(user_id, text="📍 **استان** محل سکونتت رو انتخاب یا تایپ کن:", keyboard=prov_kb)
        return

    elif step == 'WAITING_PROVINCE':
        cursor.execute("UPDATE users SET province = ?, step = 'WAITING_CITY' WHERE user_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        send_message(user_id, text="🏡 نام **شهر** خودت رو بنویس:")
        return

    elif step == 'WAITING_CITY':
        inviter_id = user["inviter_id"]
        cursor.execute("UPDATE users SET city = ?, step = 'MAIN_MENU', coins = 5 WHERE user_id = ?", (text, user_id))
        if inviter_id:
            cursor.execute("UPDATE users SET coins = coins + 5 WHERE user_id = ?", (inviter_id,))
            send_message(inviter_id, text="🎉 یک کاربر با لینک شما عضو شد! ۵ سکه هدیه گرفتی.")
        conn.commit()
        conn.close()
        send_main_menu(user_id, "🎁 ثبت‌نام تکمیل شد! **۵ سکه رایگان** هدیه گرفتی! 🥳")
        return

    # ۴. منوی اصلی و مدیریت گفتگوها
    elif step == 'MAIN_MENU':
        partner_id = get_partner(user_id)

        # اگر کاربر در حال چت باشد
        if partner_id:
            if text == "🚫 پایان چت":
                cursor.execute("DELETE FROM active_chats WHERE user_a = ? OR user_b = ?", (user_id, user_id))
                conn.commit()
                conn.close()
                send_main_menu(user_id, "🔴 چت پایان یافت.")
                send_main_menu(partner_id, "🔴 هم‌صحبت شما چت را پایان داد.")
                return

            if text == "⛔ بلاک و گزارش تخلف":
                cursor.execute("INSERT OR IGNORE INTO personal_blocks VALUES (?, ?)", (user_id, partner_id))
                cursor.execute("UPDATE users SET reports = reports + 1 WHERE user_id = ?", (partner_id,))
                cursor.execute("SELECT reports FROM users WHERE user_id = ?", (partner_id,))
                rep_count = cursor.fetchone()[0]

                cursor.execute("DELETE FROM active_chats WHERE user_a = ? OR user_b = ?", (user_id, user_id))
                
                if rep_count >= 3:
                    cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (partner_id,))
                    send_message(partner_id, text="⛔ حساب شما به دلیل دریافت ۳ گزارش تخلف مسدود شد.")

                conn.commit()
                conn.close()
                send_main_menu(user_id, "⛔ کاربر بلاک و گزارش شد.")
                if rep_count < 3:
                    send_main_menu(partner_id, "⚠️ طرف مقابل شما را بلاک کرد و چت پایان یافت.")
                return

            # ارسال عکس در چت نیازمند ۱ سکه است
            if msg_type == 'photo':
                if coins < 1:
                    conn.close()
                    send_message(user_id, text="❌ برای ارسال عکس به ۱ سکه نیاز داری.")
                    return
                cursor.execute("UPDATE users SET coins = coins - 1 WHERE user_id = ?", (user_id,))
                conn.commit()

            conn.close()
            # بازنشر انواع پیام‌ها برای هم‌صحبت
            send_message(partner_id, text=text, file_id=file_id, msg_type=msg_type)
            return

        # انصراف از جستجو
        if text == "🚫 انصراف از جستجو":
            cursor.execute("DELETE FROM queue WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            send_main_menu(user_id, "❌ جستجو لغو شد.")
            return

        # شروع چت ناشناس
        if text in ["🎲 چت ناشناس (رایگان)", "🏙 چت استانی (رایگان)", "👫 چت با دختر (VIP)", "👦 چت با پسر (VIP)"]:
            
            # برسی سکه برای چت VIP
            req_gender = 'ANY'
            if "دختر" in text or "پسر" in text:
                if coins < 2:
                    conn.close()
                    send_message(user_id, text="❌ برای چت بر اساس جنسیت حداقل به ۲ سکه نیاز داری.")
                    return
                req_gender = "دختر" if "دختر" in text else "پسر"

            req_prov = user["province"] if "استانی" in text else 'ANY'

            # جستجو در صف
            query = "SELECT user_id FROM queue WHERE user_id != ?"
            params = [user_id]

            if req_gender != 'ANY':
                query += " AND user_id IN (SELECT user_id FROM users WHERE gender = ?)"
                params.append(req_gender)
            if req_prov != 'ANY':
                query += " AND user_id IN (SELECT user_id FROM users WHERE province = ?)"
                params.append(req_prov)

            cursor.execute(query, tuple(params))
            candidates = cursor.fetchall()

            found_partner = None
            for cand in candidates:
                c_id = cand["user_id"]
                if not is_personally_blocked(user_id, c_id):
                    found_partner = c_id
                    break

            if found_partner:
                cursor.execute("DELETE FROM queue WHERE user_id IN (?, ?)", (user_id, found_partner))
                cursor.execute("INSERT INTO active_chats VALUES (?, ?)", (user_id, found_partner))
                if req_gender != 'ANY':
                    cursor.execute("UPDATE users SET coins = coins - 2 WHERE user_id = ?", (user_id,))
                conn.commit()
                conn.close()

                chat_kb = [["🚫 پایان چت", "⛔ بلاک و گزارش تخلف"]]
                send_message(user_id, text="🎉 **به یک هم‌صحبت ناشناس متصل شدی!**", keyboard=chat_kb)
                send_message(found_partner, text="🎉 **به یک هم‌صحبت ناشناس متصل شدی!**", keyboard=chat_kb)
            else:
                cursor.execute("INSERT OR REPLACE INTO queue (user_id, gender_pref, province_pref) VALUES (?, ?, ?)", (user_id, req_gender, req_prov))
                conn.commit()
                conn.close()
                send_message(user_id, text="🔍 **در حال جستجوی هم‌صحبت...**", keyboard=[["🚫 انصراف از جستجو"]])
            return

        elif text == "💰 سکه رایگان و خرید شارژ":
            conn.close()
            ref_link = f"https://splus.ir/ChatinoBot?start={user_id}"
            shop_text = (
                f"🪙 **مدیریت سکه و شارژ حساب**\n\n"
                f"💎 موجودی فعلی: **{coins} سکه**\n\n"
                f"🎁 **دعوت از دوستان (۵ سکه رایگان):**\n`{ref_link}`\n\n"
                f"💳 **خرید سکه (کارت به کارت):**\n"
                f"شماره کارت: `6037-9979-0000-0000`\n"
                f"ارسال فیش به پشتیبانی: @Chatino_Support"
            )
            send_message(user_id, text=shop_text, keyboard=[["بازگشت به منوی اصلی"]])
            return

        elif text == "👤 پروفایل من":
            conn.close()
            profile_msg = (
                f"👤 **شناسنامه کاربری شما:**\n\n"
                f"🔹 **نام:** {user['name']}\n"
                f"🔹 **جنسیت:** {user['gender']}\n"
                f"🔹 **سن:** {user['age']} سال\n"
                f"🔹 **استان:** {user['province']} - {user['city']}\n"
                f"🪙 **موجودی سکه:** {coins}\n"
                f"🚨 **تعداد گزارش‌ها:** {user['reports']} از ۳"
            )
            send_message(user_id, text=profile_msg)
            return

        elif text == "🛡 پشتیبانی و قوانین":
            conn.close()
            rules = "📜 **قوانین چتینو:**\n\n۱. احترام متقابل الزامی است.\n۲. ارسال محتوای نامناسب مسدودی دارد.\n پشتیبانی: @Chatino_Support"
            send_message(user_id, text=rules)
            return

        elif text == "بازگشت به منوی اصلی":
            conn.close()
            send_main_menu(user_id)
            return
            
    conn.close()

# چرخه دریافت پیام‌ها
def start_bot():
    print("✅ ربات «چتینو» روشن و آماده پاسخگویی است...")
    last_update_id = 0
    while True:
        try:
            res = requests.get(API_URL + f"getUpdates?offset={last_update_id + 1}", timeout=12)
            if res.status_code == 200:
                data = res.json()
                updates = data.get("result", [])
                for update in updates:
                    last_update_id = update.get("update_id", last_update_id)
                    msg = update.get("message", {})
                    user_id = str(msg.get("from", {}).get("id", ""))
                    text = msg.get("text", "")
                    
                    msg_type = "text"
                    file_id = None
                    if "photo" in msg:
                        msg_type = "photo"
                        file_id = msg.get("photo", {}).get("fileId")
                    elif "voice" in msg or "audio" in msg:
                        msg_type = "voice"
                        file_id = msg.get("voice", {}).get("fileId")

                    start_param = None
                    if text.startswith("/start "):
                        start_param = text.split(" ")[1]

                    if user_id:
                        handle_message(user_id, text, msg_type=msg_type, file_id=file_id, start_param=start_param)
        except Exception as e:
            time.sleep(2)

if __name__ == "__main__":
    start_bot()
