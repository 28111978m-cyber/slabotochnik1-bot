import os, json, time, subprocess, requests

TOKEN = os.environ["BOT_TOKEN"]
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

USERS_FILE = "users.json"
SENT_FILE = "sent_vacancies.json"
OFFSET_FILE = "offset.txt"

DEFAULT_KEYWORDS = ["слаботочник", "слаботочных систем", "СКУД", "видеонаблюдение", "ОПС", "слаботочка"]

# ============ ХЕЛПЕРЫ ============
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def git_commit():
    try:
        subprocess.run(["git", "add", "-A"], capture_output=True)
        diff = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True)
        if diff.returncode != 0:
            subprocess.run(["git", "commit", "-m", "auto state [skip ci]"], capture_output=True)
            subprocess.run(["git", "push"], capture_output=True)
    except Exception as e:
        print(f"git error: {e}")

def send_message(chat_id, text):
    for i in range(0, len(text), 4000):
        try:
            requests.post(f"{BASE_URL}/sendMessage", data={
                "chat_id": chat_id,
                "text": text[i:i+4000],
                "disable_web_page_preview": True,
            }, timeout=30)
        except Exception as e:
            print(f"send error: {e}")

# ============ ЛОГИКА ВАКАНСИЙ ============
def fetch_vacancies(keyword, city):
    url = "http://opendata.trudvsem.ru/api/v1/vacancies"
    params = {"text": keyword, "limit": 100}
    try:
        r = requests.get(url, params=params, timeout=30)
        items = r.json().get("results", {}).get("vacancies", [])
    except Exception as e:
        print(f"fetch error: {e}")
        return []

    kw_lower = keyword.lower()
    city_lower = city.lower()
    result = []
    for item in items:
        v = item.get("vacancy", {})
        name = v.get("job-name", "").lower()
        # фильтр: ключевое слово ДОЛЖНО быть в названии вакансии
        if kw_lower not in name:
            continue
        region = v.get("region", {}).get("name", "").lower()
        addresses = v.get("addresses", {}).get("address", [])
        locations = " ".join(a.get("location", "") for a in addresses).lower()
        # фильтр: город должен совпасть с регионом или адресом
        if city_lower not in region and city_lower not in locations:
            continue
        result.append(v)
    return result

def format_vacancy(v):
    name = v.get("job-name", "")
    company = v.get("company", {}).get("name", "")
    region = v.get("region", {}).get("name", "")
    salary = v.get("salary", "не указана")
    schedule = v.get("schedule", "")
    link = v.get("vac_url", "")
    text = f"🔧 {name}\n🏢 {company}\n📍 {region}\n💰 {salary}"
    if schedule:
        text += f"\n🕒 {schedule}"
    text += f"\n🔗 {link}"
    return text

def send_vacancies_to_user(chat_id, user, sent):
    cities = user.get("cities", [])
    if not cities:
        return 0
    keywords = user.get("keywords", DEFAULT_KEYWORDS)
    user_sent = set(sent.get(chat_id, []))
    found = []
    seen = set()
    for city in cities:
        for kw in keywords:
            for v in fetch_vacancies(kw, city):
                vid = v.get("id")
                if vid and vid not in user_sent and vid not in seen:
                    found.append((v, city))
                    seen.add(vid)
    if not found:
        return 0

    by_city = {}
    for v, city in found:
        by_city.setdefault(city, []).append(v)

    for city, vacs in by_city.items():
        header = f"🆕 {city}: {len(vacs)} новых вакансий\n\n"
        body = "\n\n➖➖➖\n\n".join(format_vacancy(v) for v in vacs)
        send_message(chat_id, header + body)
        for v in vacs:
            user_sent.add(v.get("id"))
    sent[chat_id] = list(user_sent)
    return len(found)

# ============ КОМАНДЫ ============
def handle_update(update, users, sent):
    msg = update.get("message")
    if not msg:
        return
    chat_id = str(msg["chat"]["id"])
    text = (msg.get("text") or "").strip()
    if not text:
        return

    if text.startswith("/start"):
        users.setdefault(chat_id, {"cities": []})
        send_message(chat_id,
            "👋 Привет! Я бот для поиска вакансий по слаботочке.\n\n"
            "📍 Добавьте города, где ищете работу:\n"
            "/city Москва\n\n"
            "Можно несколько через запятую:\n"
            "/city Москва, Санкт-Петербург\n\n"
            "📋 Команды:\n"
            "/mycities — мои города\n"
            "/rmcity Москва — удалить город\n"
            "/help — помощь"
        )

    elif text.startswith("/city"):
        cities_str = text[len("/city"):].strip()
        if not cities_str:
            send_message(chat_id, "Напишите: /city Москва\nИли несколько: /city Москва, Казань")
            return
        users.setdefault(chat_id, {"cities": []})
        new_cities = [c.strip() for c in cities_str.split(",") if c.strip()]
        users[chat_id]["cities"] = list(dict.fromkeys(users[chat_id]["cities"] + new_cities))
        send_message(chat_id, f"✅ Сохранено. Ваши города: {', '.join(users[chat_id]['cities'])}\n\nИщу вакансии...")
        try:
            n = send_vacancies_to_user(chat_id, users[chat_id], sent)
            if n == 0:
                send_message(chat_id, "Пока новых вакансий нет. Пришлю, как только появятся.")
        except Exception as e:
            print(f"immediate send error: {e}")

    elif text.startswith("/rmcity"):
        city = text[len("/rmcity"):].strip()
        if chat_id in users and city in users[chat_id]["cities"]:
            users[chat_id]["cities"].remove(city)
            send_message(chat_id, f"✅ Удалён город: {city}")
        else:
            send_message(chat_id, "Такого города нет в вашем списке.")

    elif text.startswith("/mycities"):
        if chat_id in users and users[chat_id]["cities"]:
            send_message(chat_id, f"📍 Ваши города: {', '.join(users[chat_id]['cities'])}")
        else:
            send_message(chat_id, "У вас пока нет городов. Добавьте: /city Москва")

    elif text.startswith("/help"):
        send_message(chat_id,
            "Команды:\n"
            "/city Москва — добавить город\n"
            "/city Москва, Казань — несколько\n"
            "/rmcity Москва — удалить\n"
            "/mycities — список городов\n"
            "/help — помощь"
        )
    else:
        send_message(chat_id, "Не понимаю. Напишите /help.")

# ============ OFFSET ============
def load_offset():
    try:
        with open(OFFSET_FILE) as f:
            return int(f.read().strip())
    except:
        return 0

def save_offset(o):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(o))

# ============ ГЛАВНОЕ ============
def main():
    users = load_json(USERS_FILE, {})
    sent = load_json(SENT_FILE, {})
    if not isinstance(sent, dict):
        sent = {}

    print(f"Отправка вакансий {len(users)} пользователям...")
    for chat_id, user in users.items():
        try:
            n = send_vacancies_to_user(chat_id, user, sent)
            print(f"  {chat_id}: {n} вакансий")
        except Exception as e:
            print(f"  error {chat_id}: {e}")
    save_json(SENT_FILE, sent)
    git_commit()

    offset = load_offset()
    start_time = time.time()
    MAX_DURATION = 5.5 * 3600  # 5.5 часов
    last_commit = time.time()
    COMMIT_INTERVAL = 5 * 60

    print("Начинаю приём команд...")
    while time.time() - start_time < MAX_DURATION:
        try:
            r = requests.get(f"{BASE_URL}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=40)
            data = r.json()
            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    save_offset(offset)
                    try:
                        handle_update(update, users, sent)
                    except Exception as e:
                        print(f"handle error: {e}")
                if data.get("result"):
                    save_json(USERS_FILE, users)
                    save_json(SENT_FILE, sent)
        except Exception as e:
            print(f"poll error: {e}")
            time.sleep(5)

        if time.time() - last_commit > COMMIT_INTERVAL:
            git_commit()
            last_commit = time.time()

    save_json(USERS_FILE, users)
    save_json(SENT_FILE, sent)
    git_commit()
    print("Готово.")

if __name__ == "__main__":
    main()
    save_sent(sent)
    print(f"Отправлено вакансий: {len(found)}")

if __name__ == "__main__":
    main()
