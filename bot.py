import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)
import requests

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── تنظیمات ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")          # توکن ربات تلگرام
CALLINOO_TOKEN = os.environ.get("CALLINOO_TOKEN", "YOUR_CALLINOO_TOKEN_HERE") # توکن API کالینو
BASE_URL = "https://api.ozvinoo.xyz/web"

# ─── State های ConversationHandler ───────────────────────
SELECT_SERVICE, SELECT_COUNTRY, WAITING_CODE = range(3)

# ─── API کالینو ──────────────────────────────────────────
class CallinooAPI:
    def __init__(self, token: str):
        self.token = token
        self.base = f"{BASE_URL}/{token}"

    def get_balance(self) -> dict:
        r = requests.post(f"{self.base}/get-balance", timeout=10)
        r.raise_for_status()
        return r.json()

    def get_services(self) -> dict:
        r = requests.post(f"{self.base}/applications", timeout=10)
        r.raise_for_status()
        return r.json()

    def get_prices(self, service_id: int) -> list:
        r = requests.post(f"{self.base}/get-prices/{service_id}", timeout=10)
        r.raise_for_status()
        return r.json()

    def get_number(self, service_id: int, country: str) -> dict:
        url = f"{self.base}/getNumber/{service_id}/{country}"
        r = requests.post(url, timeout=15)
        r.raise_for_status()
        return r.json()

    def get_code(self, request_id: int) -> dict:
        r = requests.post(f"{self.base}/getCode/{request_id}", timeout=10)
        r.raise_for_status()
        return r.json()


api = CallinooAPI(CALLINOO_TOKEN)


# ─── Helper ───────────────────────────────────────────────
def format_price(p: int) -> str:
    """تبدیل قیمت به فرمت فارسی با جداکننده هزارگان"""
    return f"{p:,} تومان"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📲 خرید شماره مجازی", callback_data="buy")],
        [InlineKeyboardButton("💰 موجودی حساب", callback_data="balance")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ─── هندلرها ──────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 سلام {user.first_name} عزیز!\n\n"
        "🔷 به ربات شماره مجازی کالینو خوش آمدید.\n"
        "از منوی زیر گزینه مورد نظر را انتخاب کنید:"
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── موجودی ────────────────────────────────────────────
    if data == "balance":
        try:
            result = api.get_balance()
            balance = result.get("balance", 0)
            await query.edit_message_text(
                f"💰 موجودی حساب شما:\n\n"
                f"*{format_price(balance)}*\n\n"
                "برای بازگشت /start بزنید.",
                parse_mode="Markdown"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ خطا در دریافت موجودی:\n{e}")
        return ConversationHandler.END

    # ── خرید شماره: نمایش سرویس‌ها ───────────────────────
    if data == "buy":
        try:
            services_raw = api.get_services()
            keyboard = []
            for key, svc in services_raw.items():
                btn = InlineKeyboardButton(
                    f"📱 {svc['title']}",
                    callback_data=f"svc_{svc['id']}_{svc['code']}"
                )
                keyboard.append([btn])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back")])
            await query.edit_message_text(
                "📋 سرویس مورد نظر را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return SELECT_SERVICE
        except Exception as e:
            await query.edit_message_text(f"❌ خطا در دریافت سرویس‌ها:\n{e}")
            return ConversationHandler.END

    # ── انتخاب سرویس → نمایش کشورها ──────────────────────
    if data.startswith("svc_"):
        parts = data.split("_")
        service_id = int(parts[1])
        context.user_data["service_id"] = service_id
        context.user_data["service_code"] = parts[2]

        try:
            prices = api.get_prices(service_id)
            # فیلتر کشورهای موجود
            available = [p for p in prices if "✅" in p.get("count", "")]
            if not available:
                await query.edit_message_text(
                    "❌ در حال حاضر هیچ کشوری موجود نیست.\n"
                    "برای بازگشت /start بزنید."
                )
                return ConversationHandler.END

            keyboard = []
            for item in available[:20]:  # حداکثر ۲۰ کشور
                country_name = item["country"]
                price = format_price(item["price"])
                btn = InlineKeyboardButton(
                    f"{country_name}  |  {price}",
                    callback_data=f"country_{item['range']}_{item['price']}"
                )
                keyboard.append([btn])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="buy")])

            await query.edit_message_text(
                "🌍 کشور مورد نظر را انتخاب کنید:\n"
                "_(فقط کشورهای موجود نمایش داده می‌شوند)_",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return SELECT_COUNTRY
        except Exception as e:
            await query.edit_message_text(f"❌ خطا در دریافت قیمت‌ها:\n{e}")
            return ConversationHandler.END

    # ── انتخاب کشور → دریافت شماره ───────────────────────
    if data.startswith("country_"):
        parts = data.split("_")
        country_code = parts[1]
        price = int(parts[2])
        service_id = context.user_data.get("service_id")

        await query.edit_message_text(
            f"⏳ در حال دریافت شماره مجازی...\n"
            f"قیمت: *{format_price(price)}*",
            parse_mode="Markdown"
        )

        try:
            result = api.get_number(service_id, country_code)
        except requests.HTTPError as e:
            if e.response.status_code == 402:
                await query.edit_message_text(
                    "❌ موجودی کافی نیست!\n"
                    "لطفاً حساب کالینو خود را شارژ کنید.\n\n"
                    "برای بازگشت /start بزنید."
                )
            else:
                await query.edit_message_text(f"❌ خطا در دریافت شماره:\n{e}")
            return ConversationHandler.END
        except Exception as e:
            await query.edit_message_text(f"❌ خطا:\n{e}")
            return ConversationHandler.END

        number = result.get("number", "نامشخص")
        request_id = result.get("request_id")
        country = result.get("countery", "نامشخص")
        quality = result.get("quality", "")

        context.user_data["request_id"] = request_id
        context.user_data["number"] = number

        keyboard = [[
            InlineKeyboardButton("📩 دریافت کد تأیید", callback_data=f"getcode_{request_id}")
        ]]

        await query.edit_message_text(
            f"✅ شماره مجازی شما آماده است!\n\n"
            f"📞 شماره: `{number}`\n"
            f"🌍 کشور: {country}\n"
            f"💰 قیمت: {format_price(price)}\n"
            f"🆔 شناسه درخواست: `{request_id}`\n\n"
            f"{quality}\n\n"
            "پس از ارسال کد توسط سرویس، دکمه زیر را بزنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return WAITING_CODE

    # ── دریافت کد تأیید ───────────────────────────────────
    if data.startswith("getcode_"):
        request_id = int(data.split("_")[1])
        await query.answer("⏳ در حال دریافت کد...", show_alert=False)

        try:
            result = api.get_code(request_id)
            code = result.get("code")

            if not code:
                keyboard = [[
                    InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"getcode_{request_id}")
                ]]
                await query.edit_message_text(
                    f"⏳ کد هنوز دریافت نشده است.\n\n"
                    f"📞 شماره: `{result.get('number', context.user_data.get('number', ''))}`\n"
                    f"🆔 شناسه: `{request_id}`\n\n"
                    "چند لحظه دیگر دوباره امتحان کنید:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(
                    f"🎉 کد تأیید دریافت شد!\n\n"
                    f"📞 شماره: `{result.get('number', '')}`\n"
                    f"🔐 کد: *`{code}`*\n\n"
                    "موفق باشید! برای خرید مجدد /start بزنید.",
                    parse_mode="Markdown"
                )
        except Exception as e:
            await query.edit_message_text(f"❌ خطا در دریافت کد:\n{e}")
        return ConversationHandler.END

    # ── بازگشت ────────────────────────────────────────────
    if data == "back":
        await query.edit_message_text(
            "از منوی زیر گزینه مورد نظر را انتخاب کنید:",
            reply_markup=main_menu_keyboard()
        )
        return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ عملیات لغو شد.\n"
        "برای شروع مجدد /start بزنید."
    )
    return ConversationHandler.END


# ─── اجرای ربات ──────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(button_handler)
        ],
        states={
            SELECT_SERVICE: [CallbackQueryHandler(button_handler)],
            SELECT_COUNTRY: [CallbackQueryHandler(button_handler)],
            WAITING_CODE:   [CallbackQueryHandler(button_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )

    app.add_handler(conv_handler)

    logger.info("✅ ربات در حال اجراست...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
