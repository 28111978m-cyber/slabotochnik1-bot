import asyncio
import logging
import json
import os
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web
import urllib.parse

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
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

# --- ИСТОЧНИК 1: HH.RU (через HTML) ---
def search_hh(city, query="слаботочник"):
    safe_query = urllib.parse.quote(f"{query} {city}")
    url = f"https://hh.ru/search/vacancy?text={safe_query}&items_on_page=3"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, 'html.parser')
        script_tag = soup.find('template', {'id': 'HH-Lux-InitialState'})
        if not script_tag: 
            return []
        data = json.loads(script_tag.text)
        vacancies = data.get('vacancySearchResult', {}).get('vacancies', [])
        results = []
        for v in vacancies[:3]:
            results.append({
                "source": "hh.ru",
                "name": v.get('name', 'Без названия'),
                "employer": v.get('company', {}).get('visibleName', 'Неизвестно'),
                "salary": v.get('compensation', {}).get('description', 'З/п не указана'),
                "url": v.get('links', {}).get('desktop', '')
            })
        return results
    except Exception as e:
        logging.error(f"Ошибка HH: {e}")
        return []

# --- ИСТОЧНИК 2: РАБОТА В РОССИИ (trudvsem.ru) ---
def search_trudvsem(city, query="слаботочник"):
    url = "http://opendata.trudvsem.ru/api/v1/vacancies"
    # В Trudvsem поиск по региону работает через текстовый поиск
    params = {"text": f"{query} {city}", "limit": 3}
    try:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        vacancies = data.get('results', {}).get('vacancies', [])
        results = []
        for v in vacancies[:3]:
            vac = v.get('vacancy', {})
            salary_min = vac.get('salary_min', 0)
            salary_max = vac.get('salary_max', 0)
            salary_text = f"от {salary_min} до {salary_max} руб." if salary_min or salary_max else "З/п не указана"
            results.append({
                "source": "trudvsem.ru",
                "name": vac.get('job-name', 'Без названия'),
                "employer": vac.get('company', {}).get('name', 'Неизвестно'),
                "salary": salary_text,
                "url": vac.get('vac_url', '')
            })
        return results
    except Exception as e:
        logging.error(f"Ошибка Trudvsem: {e}")
        return []

# --- ОБЩАЯ ФУНКЦИЯ ПОИСКА (Синхронная) ---
def search_all_sources_sync(city):
    all_vacancies = []
    all_vacancies.extend(search_hh(city))
    all_vacancies.extend(search_trudvsem(city))
    return all_vacancies

# --- КОМАНДЫ БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для поиска вакансий по слаботочке.\n\n"
        "📍 Добавьте город, где ищете работу:\n"
        "/city Москва\n\n"
        "📃 Команды:\n"
        "/mycities — мои города\n"
        "/rmcity Москва — удалить город"
    )

@dp.message(Command("city"))
async def cmd_city(message: types.Message):
    user_id = str(message.from_user.id)
    args = message.text.replace("/city", "").strip()
    if not args:
        await message.answer("Напишите город после команды. Пример: /city Москва")
        return

    cities = [c.strip() for c in args.split(",")]
    data = load_data()
    if user_id not in data: data[user_id] = []
    for city in cities:
        if city not in data[user_id]: data[user_id].append(city)
    save_data(data)
    
    await message.answer(f"✅ Сохранено: {', '.join(data[user_id])}\n\nИщу вакансии, подождите пару секунд...")
    
    for city in cities:
        # Запускаем синхронный парсинг в отдельном потоке, чтобы не блокировать бота
        vacancies = await asyncio.to_thread(search_all_sources_sync, city)
        
        if not vacancies:
            await message.answer(f"По городу {city} пока ничего не найдено.")
            continue
        
        for v in vacancies:
            text = (f"💼 <b>{v['name']}</b>\n"
                    f"🏢 {v['employer']}\n"
                    f"💰 {v['salary']}\n"
                    f"🔗 <a href='{v['url']}'>Открыть вакансию</a>\n"
                    f"📌 <i>Источник: {v['source']}</i>")
            await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

@dp.message(Command("mycities"))
async def cmd_mycities(message: types.Message):
    user_id = str(message.from_user.id)
    cities = load_data().get(user_id, [])
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

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle(request): return web.Response(text="Bot is running!")
async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
