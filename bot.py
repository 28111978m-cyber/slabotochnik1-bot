import asyncio
import logging
import json
import os
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiohttp import web

# --- НАСТРОЙКИ ---
# Вставьте сюда ваш токен от BotFather (в кавычках)
BOT_TOKEN = "9298754437:AAGQfOskEffH64fobg5v6kRAwi0XM0ic4bA"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- РАБОТА С ФАЙЛОМ (СОХРАНЕНИЕ ГОРОДОВ) ---
def load_data():
    if os.path.exists("users.json"):
        with open("users.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- ПАРСЕР ВАКАНСИЙ HH.RU ---
def search_vacancies(city):
    # Ищем по слову "слаботочник" + название города
    url = f"https://hh.ru/search/vacancy?text=слаботочник+{city}&items_on_page=5"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        script_tag = soup.find('template', {'id': 'HH-Lux-InitialState'})
        
        if not script_tag:
            return []
            
        data = json.loads(script_tag.text)
        vacancies = data.get('vacancySearchResult', {}).get('vacancies', [])
        return vacancies[:5] # Возвращаем 5 штук
        
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
        return []

# --- КОМАНДЫ БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для поиска вакансий по слаботочке.\n\n"
        "📍 Добавьте город, где ищете работу:\n"
        "/city Москва\n\n"
        "Или несколько через запятую:\n"
        "/city Москва, Новосибирск\n\n"
        "📃 Команды:\n"
        "/mycities — мои города\n"
        "/rmcity Москва — удалить город\n"
        "/help — помощь"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("Просто добавь города через /city и я начну искать вакансии.")

@dp.message(Command("city"))
async def cmd_city(message: types.Message):
    user_id = str(message.from_user.id)
    args = message.text.replace("/city", "").strip()
    
    if not args:
        await message.answer("Напишите город после команды. Пример: /city Москва")
        return

    cities = [c.strip() for c in args.split(",")]
    data = load_data()
    
    if user_id not in data:
        data[user_id] = []
        
    for city in cities:
        if city not in data[user_id]:
            data[user_id].append(city)
            
    save_data(data)
    await message.answer(f"✅ Сохранено. Ваши города: {', '.join(data[user_id])}\n\nИщу вакансии...")
    
    # Сразу запускаем поиск для добавленных городов
    for city in cities:
        vacancies = search_vacancies(city)
        if not vacancies:
            await message.answer(f"По городу {city} пока ничего не найдено.")
            continue
            
        for v in vacancies:
            name = v.get('name', 'Без названия')
            employer = v.get('company', {}).get('visibleName', 'Неизвестная компания')
            salary = v.get('compensation', {}).get('description', 'Зарплата не указана')
            link = v.get('links', {}).get('desktop', '')
            
            text = f"💼 {name}\n🏢 {employer}\n💰 {salary}\n🔗 {link}"
            await message.answer(text)

@dp.message(Command("mycities"))
async def cmd_mycities(message: types.Message):
    user_id = str(message.from_user.id)
    data = load_data()
    cities = data.get(user_id, [])
    
    if not cities:
        await message.answer("У вас пока нет городов. Добавьте: /city Москва")
    else:
        await message.answer(f"Ваши города: {', '.join(cities)}")

@dp.message(Command("rmcity"))
async def cmd_rmcity(message: types.Message):
    user_id = str(message.from_user.id)
    args = message.text.replace("/rmcity", "").strip()
    data = load_data()
    
    if user_id in data and args in data[user_id]:
        data[user_id].remove(args)
        save_data(data)
        await message.answer(f"Город {args} удален.")
    else:
        await message.answer("Такого города нет в вашем списке.")

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (ЧТОБЫ НЕ ЗАСЫПАЛ) ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")

# --- ЗАПУСК ---
async def main():
    # Запускаем веб-сервер в фоне
    await start_web_server()
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
