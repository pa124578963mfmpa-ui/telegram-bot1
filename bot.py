import os
import time
import sqlite3
import requests
import telebot

from telebot import types
from datetime import datetime, timedelta, timezone


# ==================================================
# CONFIG
# ==================================================

BOT_TOKEN = os.getenv("8694861903:AAGBIHoi93DyXamIDqbRdDgZcVld-qnGZ2U")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8566520902"))

PANEL_URL = os.getenv(
    "PANEL_URL",
    "https://eghpas.edgecorex.ir"
)

PANEL_USERNAME = os.getenv("sg_8973931042_yv4cul")
PANEL_PASSWORD = os.getenv("k6ffPc9UBfdH9&js")


# ==================================================
# PRICES
# ==================================================

PRICES = {
    "20_30": 200000,
    "30_30": 300000,
    "50_30": 500000,

    "20_60": 250000,
    "30_60": 350000,
    "50_60": 600000
}


# ==================================================
# BOT
# ==================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = telebot.TeleBot(BOT_TOKEN)

session = requests.Session()

access_token = None

orders = {}

DB = "bot_database.db"


# ==================================================
# DATABASE
# ==================================================

def db():
    return sqlite3.connect(DB)


def create_database():

    conn = db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0,
            test_used INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            type TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            panel_username TEXT,
            gb REAL,
            hours REAL,
            subscription_url TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


create_database()


# ==================================================
# USERS
# ==================================================

def add_user(user_id, username):

    conn = db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO users
        (user_id, username, balance, test_used)
        VALUES (?, ?, 0, 0)
    """, (user_id, username))

    cursor.execute("""
        UPDATE users
        SET username=?
        WHERE user_id=?
    """, (username, user_id))

    conn.commit()
    conn.close()


def get_balance(user_id):

    conn = db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (user_id,)
    )

    row = cursor.fetchone()

    conn.close()

    return row[0] if row else 0


def change_balance(user_id, amount, transaction_type):

    conn = db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET balance = balance + ?
        WHERE user_id=?
    """, (amount, user_id))

    cursor.execute("""
        INSERT INTO transactions
        (user_id, amount, type, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        amount,
        transaction_type,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


# ==================================================
# FREE TEST
# ==================================================

def has_used_test(user_id):

    conn = db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT test_used FROM users WHERE user_id=?",
        (user_id,)
    )

    row = cursor.fetchone()

    conn.close()

    return bool(row and row[0] == 1)


def mark_test_used(user_id):

    conn = db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET test_used=1
        WHERE user_id=?
    """, (user_id,))

    conn.commit()
    conn.close()


# ==================================================
# SERVICES DATABASE
# ==================================================

def save_service(
    user_id,
    panel_username,
    gb,
    hours,
    subscription_url
):

    conn = db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO services
        (
            user_id,
            panel_username,
            gb,
            hours,
            subscription_url,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        panel_username,
        gb,
        hours,
        subscription_url,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def get_services(user_id):

    conn = db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            panel_username,
            gb,
            hours,
            subscription_url,
            created_at
        FROM services
        WHERE user_id=?
        ORDER BY id DESC
    """, (user_id,))

    rows = cursor.fetchall()

    conn.close()

    return rows


# ==================================================
# PASARGUARD LOGIN
# ==================================================

def panel_login():

    global access_token

    if not PANEL_USERNAME or not PANEL_PASSWORD:
        print("Panel username/password not configured")
        return False

    try:

        url = (
            PANEL_URL.rstrip("/")
            + "/api/admin/token"
        )

        data = {
            "username": PANEL_USERNAME,
            "password": PANEL_PASSWORD,
            "grant_type": "password"
        }

        response = session.post(
            url,
            data=data,
            timeout=20
        )

        if response.status_code != 200:

            print(
                "PANEL LOGIN ERROR:",
                response.status_code,
                response.text
            )

            return False

        result = response.json()

        access_token = result.get(
            "access_token"
        )

        if not access_token:
            return False

        session.headers.update({
            "Authorization":
            "Bearer " + access_token
        })

        print("PASARGUARD CONNECTED")

        return True

    except Exception as e:

        print(
            "PANEL ERROR:",
            e
        )

        return False


# ==================================================
# PANEL GET
# ==================================================

def panel_get(url, params=None):

    if not access_token:

        if not panel_login():
            return None

    try:

        response = session.get(
            url,
            params=params,
            timeout=20
        )

        if response.status_code == 401:

            if not panel_login():
                return None

            response = session.get(
                url,
                params=params,
                timeout=20
            )

        return response

    except Exception as e:

        print(
            "GET ERROR:",
            e
        )

        return None


# ==================================================
# GET PANEL USER
# ==================================================

def get_panel_user(username):

    url = (
        PANEL_URL.rstrip("/")
        + "/api/user/"
        + username
    )

    response = panel_get(url)

    if response is None:
        return None

    if response.status_code != 200:
        return None

    try:
        return response.json()

    except Exception:
        return None


# ==================================================
# GET PANEL USERS
# ==================================================

def get_panel_users():

    url = (
        PANEL_URL.rstrip("/")
        + "/api/users"
    )

    response = panel_get(
        url,
        params={
            "load_sub": "true"
        }
    )

    if response is None:
        return None

    if response.status_code != 200:

        print(response.text)

        return None

    try:
        return response.json()

    except Exception:
        return None


# ==================================================
# CREATE PANEL USER
# ==================================================

def create_panel_user(
    username,
    gb,
    hours
):

    if not access_token:

        if not panel_login():
            return None

    url = (
        PANEL_URL.rstrip("/")
        + "/api/user"
    )

    expire = (
        datetime.now(timezone.utc)
        + timedelta(hours=hours)
    )

    data = {

        "username": username,

        "status": "active",

        "expire":
            expire.replace(
                microsecond=0
            ).isoformat(),

        "data_limit":
            int(
                gb
                * 1024
                * 1024
                * 1024
            ),

        "data_limit_reset_strategy":
            "no_reset",

        "proxy_settings": {},

        "hwid_limit": None
    }

    try:

        response = session.post(
            url,
            json=data,
            timeout=20
        )

        if response.status_code == 401:

            if not panel_login():
                return None

            response = session.post(
                url,
                json=data,
                timeout=20
            )

        if response.status_code not in [200, 201]:

            print(
                "CREATE ERROR:",
                response.status_code,
                response.text
            )

            return None

        return response.json()

    except Exception as e:

        print(
            "CREATE ERROR:",
            e
        )

        return None


# ==================================================
# MAIN MENU
# ==================================================

def main_menu(user_id):

    keyboard = types.InlineKeyboardMarkup(
        row_width=2
    )

    keyboard.add(

        types.InlineKeyboardButton(
            "🛒 خرید سرویس",
            callback_data="buy"
        ),

        types.InlineKeyboardButton(
            "📦 سرویس‌های من",
            callback_data="myservices"
        )
    )

    keyboard.add(

        types.InlineKeyboardButton(
            "🎁 تست رایگان",
            callback_data="free_test"
        ),

        types.InlineKeyboardButton(
            "💰 کیف پول",
            callback_data="wallet"
        )
    )

    keyboard.add(

        types.InlineKeyboardButton(
            "📚 آموزش اتصال",
            callback_data="tutorials"
        ),

        types.InlineKeyboardButton(
            "💬 پشتیبانی",
            callback_data="support"
        )
    )

    if user_id == ADMIN_ID:

        keyboard.add(
            types.InlineKeyboardButton(
                "⚙️ مدیریت",
                callback_data="admin"
            )
        )

    return keyboard


# ==================================================
# START
# ==================================================

@bot.message_handler(commands=["start"])
def start(message):

    user_id = message.from_user.id

    add_user(
        user_id,
        message.from_user.username
        or message.from_user.first_name
    )

    bot.send_message(

        message.chat.id,

        "🤖 به ربات فروش خوش آمدید!\n\n"

        "⚡ خرید سریع سرویس\n"
        "🎁 تست رایگان ۱۰۰ مگابایت / ۲ ساعت\n"
        "💰 کیف پول\n"
        "📚 آموزش اتصال\n"
        "💬 پشتیبانی",

        reply_markup=main_menu(user_id)
    )


# ==================================================
# CALLBACK
# ==================================================

@bot.callback_query_handler(
    func=lambda call: True
)
def callback(call):

    user_id = call.from_user.id
    data = call.data

    bot.answer_callback_query(call.id)


    # ==================================================
    # BUY
    # ==================================================

    if data == "buy":

        keyboard = types.InlineKeyboardMarkup(
            row_width=1
        )

        keyboard.add(

            types.InlineKeyboardButton(
                "📦 ۲۰ گیگ",
                callback_data="gb_20"
            ),

            types.InlineKeyboardButton(
                "📦 ۳۰ گیگ",
                callback_data="gb_30"
            ),

            types.InlineKeyboardButton(
                "📦 ۵۰ گیگ",
                callback_data="gb_50"
            )
        )

        bot.send_message(
            user_id,
            "📦 حجم سرویس را انتخاب کنید:",
            reply_markup=keyboard
        )


    # ==================================================
    # GB
    # ==================================================

    elif data.startswith("gb_"):

        gb = int(data.split("_")[1])

        keyboard = types.InlineKeyboardMarkup(
            row_width=1
        )

        keyboard.add(

            types.InlineKeyboardButton(
                "⏳ ۳۰ روزه",
                callback_data=f"plan_{gb}_30"
            ),

            types.InlineKeyboardButton(
                "⏳ ۶۰ روزه",
                callback_data=f"plan_{gb}_60"
            )
        )

        bot.send_message(

            user_id,

            f"📦 حجم انتخابی: {gb} GB\n\n"
            "⏳ مدت را انتخاب کنید:",

            reply_markup=keyboard
        )


    # ==================================================
    # PLAN
    # ==================================================

    elif data.startswith("plan_"):

        parts = data.split("_")

        gb = int(parts[1])
        days = int(parts[2])

        key = f"{gb}_{days}"

        price = PRICES.get(key)

        if price is None:
            return

        orders[user_id] = {

            "gb": gb,
            "days": days,
            "price": price,
            "status": "waiting_payment"
        }

        keyboard = types.InlineKeyboardMarkup(
            row_width=1
        )

        keyboard.add(

            types.InlineKeyboardButton(
                "💳 پرداخت با کیف پول",
                callback_data="pay_wallet"
            ),

            types.InlineKeyboardButton(
                "➕ شارژ کیف پول",
                callback_data="charge"
            )
        )

        bot.send_message(

            user_id,

            "🧾 سفارش شما\n\n"

            f"📦 حجم: {gb} GB\n"
            f"⏳ مدت: {days} روز\n"
            f"💰 مبلغ: {price:,} تومان\n\n"

            f"💳 موجودی کیف پول: "
            f"{get_balance(user_id):,} تومان",

            reply_markup=keyboard
        )


    # ==================================================
    # PAY
    # ==================================================

    elif data == "pay_wallet":

        order = orders.get(user_id)

        if not order:

            bot.send_message(
                user_id,
                "❌ سفارش پیدا نشد."
            )

            return

        balance = get_balance(user_id)
        price = order["price"]

        if balance < price:

            bot.send_message(

                user_id,

                "❌ موجودی کافی نیست.\n\n"

                f"💰 موجودی: {balance:,} تومان\n"
                f"🧾 مبلغ: {price:,} تومان\n"
                f"📉 کمبود: {price-balance:,} تومان"
            )

            return

        username = (
            "user_"
            + str(user_id)
            + "_"
            + str(int(time.time()))
        )

        result = create_panel_user(

            username,
            order["gb"],
            order["days"] * 24
        )

        if not result:

            bot.send_message(

                user_id,

                "⚠️ ساخت سرویس انجام نشد.\n"
                "مبلغی از کیف پول کم نشد."
            )

            return

        change_balance(
            user_id,
            -price,
            "purchase"
        )

        subscription = result.get(
            "subscription_url",
            "-"
        )

        save_service(

            user_id,
            username,
            order["gb"],
            order["days"] * 24,
            subscription
        )

        bot.send_message(

            user_id,

            "🎉 خرید با موفقیت انجام شد!\n\n"

            f"📦 حجم: {order['gb']} GB\n"
            f"⏳ مدت: {order['days']} روز\n"
            f"👤 Username: {username}\n\n"

            "🔗 لینک اشتراک:\n"
            f"{subscription}\n\n"

            "📚 آموزش اتصال را از منوی ربات ببینید."
        )


    # ==================================================
    # FREE TEST
    # ==================================================

    elif data == "free_test":

        if has_used_test(user_id):

            bot.send_message(

                user_id,

                "❌ شما قبلاً تست رایگان خود را دریافت کرده‌اید.\n\n"
                "🎁 هر کاربر فقط یک بار می‌تواند تست رایگان بگیرد."
            )

            return

        bot.send_message(

            user_id,

            "⏳ در حال ساخت تست رایگان...\n\n"
            "📦 حجم: ۱۰۰ مگابایت\n"
            "⏱ مدت: ۲ ساعت"
        )

        username = (
            "test_"
            + str(user_id)
            + "_"
            + str(int(time.time()))
        )

        test_gb = 100 / 1024

        result = create_panel_user(
            username,
            test_gb,
            2
        )

        if not result:

            bot.send_message(

                user_id,

                "❌ ساخت تست انجام نشد.\n\n"
                "لطفاً اتصال پنل را بررسی کنید."
            )

            return

        mark_test_used(user_id)

        subscription = result.get(
            "subscription_url",
            "-"
        )

        save_service(

            user_id,
            username,
            test_gb,
            2,
            subscription
        )

        bot.send_message(

            user_id,

            "🎉 تست رایگان شما ساخته شد!\n\n"

            "📦 حجم: ۱۰۰ مگابایت\n"
            "⏱ مدت: ۲ ساعت\n"

            f"👤 Username: {username}\n\n"

            "🔗 لینک اشتراک
