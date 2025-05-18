import logging
from aiogram import Bot, Dispatcher, executor, types
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from flask import Flask

# Загрузка конфигурации
API_TOKEN = os.getenv('API_TOKEN')
SPREADSHEET_NAME = 'Business Tracker'

# Настройка Google Sheets
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

# Создаем credentials из переменных окружения
creds_dict = {
    "type": os.getenv('GS_TYPE'),
    "project_id": os.getenv('GS_PROJECT_ID'),
    "private_key_id": os.getenv('GS_PRIVATE_KEY_ID'),
    "private_key": os.getenv('GS_PRIVATE_KEY').replace('\\n', '\n'),
    "client_email": os.getenv('GS_CLIENT_EMAIL'),
    "client_id": os.getenv('GS_CLIENT_ID'),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv('GS_CLIENT_EMAIL').replace('@', '%40')}"
}

# Инициализация Google Sheets
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
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
    from threading import Thread
    from flask import Flask
    
    # Проверка обязательных переменных
    required_vars = ['API_TOKEN', 'GS_TYPE', 'GS_PROJECT_ID', 'GS_PRIVATE_KEY_ID', 
                   'GS_PRIVATE_KEY', 'GS_CLIENT_EMAIL', 'GS_CLIENT_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logging.error(f"Отсутствуют обязательные переменные: {', '.join(missing_vars)}")
        exit(1)

    # Создаем минимальный Flask-сервер
    app = Flask(__name__)

    @app.route('/')
    def health_check():
        return "Telegram Bot is running", 200

    # Запускаем бота в отдельном потоке
    Thread(target=lambda: executor.start_polling(dp, skip_updates=True)).start()
    
    # Запускаем Flask на порту 8080 (для Timeweb)
    app.run(host='0.0.0.0', port=8080)

