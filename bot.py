import logging
from aiogram import Bot, Dispatcher, executor, types
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# 🔐 ЗАМЕНИ НА СВОЙ ТОКЕН БОТА
API_TOKEN = '7916249076:AAEPh6e9qscRGVlgrP0QwrEl-6wDAGPr-SY'

# Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

CREDS_FILE = 'gogolove-de9dd-f226a1cf849a.json'  # путь до файла сервисного аккаунта
SPREADSHEET_NAME = 'Business Tracker'

# 📆 Русский формат даты
MONTHS_RU = {
    1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая',
    6: 'июня', 7: 'июля', 8: 'августа', 9: 'сентября',
    10: 'октября', 11: 'ноября', 12: 'декабря'
}

def format_date_rus(date_obj):
    return f"{date_obj.day} {MONTHS_RU[date_obj.month]} {date_obj.year}"


# Инициализация Google Sheets
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
client = gspread.authorize(creds)
sheet = client.open(SPREADSHEET_NAME).worksheet("transactions")

# Инициализация бота
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

income_categories = ['Дрова', 'Уголь', 'Мусор', 'Сыпучие', 'Доставка', 'Перегной']
expense_categories = ['ГСМ', 'Запчасти', 'Работник-кольщик', 'Работник-пильщик', 'Работник-погрузка',
                      'Закуп березы', 'Закуп сосны', 'Реклама', 'Закуп угля', 'Другое']

user_state = {}  # временное хранилище выбора пользователя

# 👉 Стартовое меню
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📥 Доход", "📤 Расход", "📊 Отчёт")
    await message.answer("Привет! Выбери действие:", reply_markup=markup)


# 👉 Доход или расход
@dp.message_handler(lambda message: message.text in ["📥 Доход", "📤 Расход"])
async def choose_type(message: types.Message):
    msg_type = "доход" if message.text == "📥 Доход" else "расход"
    user_state[message.from_user.id] = {"type": msg_type}

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    cats = income_categories if msg_type == "доход" else expense_categories
    [markup.add(cat) for cat in cats]
    await message.answer(f"Выбери категорию {msg_type}а:", reply_markup=markup)


# 👉 Категория выбрана
@dp.message_handler(lambda message: message.text in income_categories + expense_categories)
async def ask_amount(message: types.Message):
    state = user_state.get(message.from_user.id, {})
    if not state:
        return await message.answer("Пожалуйста, сначала выбери 📥 Доход или 📤 Расход")
    state['category'] = message.text
    user_state[message.from_user.id] = state
    await message.answer("Введи сумму (только число):")


# 👉 Ввод суммы
@dp.message_handler(lambda message: message.text.isdigit())
async def save_transaction(message: types.Message):
    state = user_state.get(message.from_user.id, {})
    if not state or 'category' not in state:
        return await message.answer("Сначала выбери доход или расход и категорию.")

    amount = float(message.text)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tx_type = state['type']
    category = state['category']
    amortization = ""

    if tx_type == "доход":
        # автоматически добавим амортизацию как 10% расход
        amortization_value = round(amount * 0.10, 2)
        sheet.append_row([timestamp, "доход", category, amount, ""])
        sheet.append_row([timestamp, "расход", "Амортизация", amortization_value, "✅ из дохода"])
        msg = f"💰 Доход {category} на {amount}₽ добавлен\n📉 Амортизация: {amortization_value}₽"
    else:
        sheet.append_row([timestamp, "расход", category, amount, ""])
        msg = f"💸 Расход {category} на {amount}₽ добавлен"

    await message.answer(msg)
    user_state.pop(message.from_user.id, None)
    await send_welcome(message)


# 👉 Отчёты
@dp.message_handler(lambda message: message.text == "📊 Отчёт")
async def report_menu(message: types.Message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Сегодня", "Неделя", "Месяц", "Детальный", "Excel-файл", "🔙 Назад")
    await message.answer("Выбери тип отчёта:", reply_markup=markup)


# 👉 Назад
@dp.message_handler(lambda message: message.text == "🔙 Назад")
async def back_to_menu(message: types.Message):
    await send_welcome(message)


# 👉 Генерация отчётов
@dp.message_handler(lambda message: message.text in ["Сегодня", "Неделя", "Месяц", "Детальный", "Excel-файл"])
async def generate_report(message: types.Message):
    data = sheet.get_all_records()
    today = datetime.now().date()

    if message.text == "Сегодня":
        from_date = today
    elif message.text == "Неделя":
        from_date = today - timedelta(days=7)
    elif message.text == "Месяц":
        from_date = today - timedelta(days=30)
    else:
        from_date = None

    if message.text == "Excel-файл":
        file_path = "transactions_export.csv"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("Дата,Тип,Категория,Сумма,Комментарий\n")
            for row in data:
                f.write(f"{row['timestamp']},{row['type']},{row['category']},{row['amount']},{row.get('amortization','')}\n")
        await message.answer_document(open(file_path, 'rb'))
        os.remove(file_path)
        return

    # Фильтрация по дате
    filtered = []
    if from_date:
        for row in data:
            row_date = datetime.strptime(row['timestamp'], "%Y-%m-%d %H:%M:%S").date()
            if row_date >= from_date:
                filtered.append(row)
    else:
        filtered = data

    if message.text == "Детальный":
        incomes = {}
        expenses = {}
        for row in filtered:
            cat = row['category']
            amt = float(row['amount'])
            if row['type'] == 'доход':
                incomes[cat] = incomes.get(cat, 0) + amt
            else:
                expenses[cat] = expenses.get(cat, 0) + amt
        msg = "📊 *Детальный отчёт*\n\n"
        msg += "💰 Доходы:\n"
        for k, v in incomes.items():
            msg += f"• {k}: {v}₽\n"
        msg += "\n💸 Расходы:\n"
        for k, v in expenses.items():
            msg += f"• {k}: {v}₽\n"
        await message.answer(msg, parse_mode="Markdown")
        return

    # Краткий отчёт
    income_sum = sum(float(r['amount']) for r in filtered if r['type'] == 'доход')
    expense_sum = sum(float(r['amount']) for r in filtered if r['type'] == 'расход')
    profit = income_sum - expense_sum
    if from_date:
        period_start = format_date_rus(from_date)
    else:
        period_start = "начала"
    period_end = format_date_rus(today)

    msg = f"📆 Период: с {period_start} по {period_end}\n"

    msg += f"💰 Доходы: {income_sum}₽\n"
    msg += f"💸 Расходы: {expense_sum}₽\n"
    msg += f"📈 Прибыль: {profit}₽"
    await message.answer(msg)

# 👉 Запуск
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
