import os
import json
import shutil
import re
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import SessionPasswordNeeded

# ==================== ЗАГРУЗКА .ENV ====================
load_dotenv()

# ==================== КОНФИГ ИЗ .ENV ====================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ==================== ПУТИ ====================
SESSIONS_DIR = "sessions"
TEMP_DIR = "temp"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# ==================== БОТ ====================
app = Client(
    "session_adder_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Хранилище
user_data = {}
auth_data = {}

# ==================== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ====================

def load_users():
    if os.path.exists("users.json"):
        with open("users.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"users": []}

def save_users(data):
    with open("users.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user(user_id):
    data = load_users()
    for user in data["users"]:
        if user["user_id"] == user_id:
            return user
    return None

def create_user(user_id, username=None):
    data = load_users()
    for user in data["users"]:
        if user["user_id"] == user_id:
            return user
    new_user = {
        "user_id": user_id,
        "username": username or str(user_id),
        "is_admin": user_id == ADMIN_ID,
        "subscription_end": None,
        "sessions": [],
        "reports_sent": 0,
        "created_at": datetime.now().isoformat()
    }
    data["users"].append(new_user)
    save_users(data)
    return new_user

def has_subscription(user_id):
    user = get_user(user_id)
    if not user:
        return False
    if user.get("is_admin"):
        return True
    subscription_end = user.get("subscription_end")
    if not subscription_end:
        return False
    try:
        end_date = datetime.fromisoformat(subscription_end)
        return datetime.now() < end_date
    except:
        return False

def get_subscription_info(user_id):
    user = get_user(user_id)
    if not user:
        return "❌ Не найден"
    if user.get("is_admin"):
        return "👑 Админ (бессрочно)"
    subscription_end = user.get("subscription_end")
    if not subscription_end:
        return "❌ Нет подписки"
    try:
        end_date = datetime.fromisoformat(subscription_end)
        if datetime.now() < end_date:
            days_left = (end_date - datetime.now()).days
            hours_left = (end_date - datetime.now()).seconds // 3600
            return f"✅ {days_left}д {hours_left}ч"
        else:
            return "❌ Истекла"
    except:
        return "❌ Ошибка"

def add_subscription(user_id, days=1):
    data = load_users()
    for user in data["users"]:
        if user["user_id"] == user_id:
            if user.get("subscription_end"):
                try:
                    current_end = datetime.fromisoformat(user["subscription_end"])
                    new_end = max(current_end, datetime.now()) + timedelta(days=days)
                except:
                    new_end = datetime.now() + timedelta(days=days)
            else:
                new_end = datetime.now() + timedelta(days=days)
            user["subscription_end"] = new_end.isoformat()
            save_users(data)
            return True
    return False

def get_user_sessions(user_id):
    user = get_user(user_id)
    if not user:
        return []
    return user.get("sessions", [])

def add_user_session(user_id, session_name, phone):
    data = load_users()
    for user in data["users"]:
        if user["user_id"] == user_id:
            for s in user["sessions"]:
                if s["session_name"] == session_name:
                    return False
            user["sessions"].append({
                "session_name": session_name,
                "phone": phone,
                "added_at": datetime.now().isoformat(),
                "reports_sent": 0
            })
            save_users(data)
            return True
    return False

def increment_report_count(user_id, session_name):
    data = load_users()
    for user in data["users"]:
        if user["user_id"] == user_id:
            user["reports_sent"] = user.get("reports_sent", 0) + 1
            for s in user["sessions"]:
                if s["session_name"] == session_name:
                    s["reports_sent"] = s.get("reports_sent", 0) + 1
                    break
            save_users(data)
            return True
    return False

def session_name_for_phone(phone):
    phone_clean = re.sub(r'[^0-9]', '', phone)
    return f"snoser_{phone_clean}"

# ==================== КЛАВИАТУРЫ ====================

def get_main_keyboard(user_id=None):
    keyboard = [
        [InlineKeyboardButton("📱 По номеру", callback_data="add_by_phone")],
        [InlineKeyboardButton("📁 Загрузить файл", callback_data="upload_file")],
        [InlineKeyboardButton("📋 Мои сессии", callback_data="my_sessions")],
        [InlineKeyboardButton("🚀 Атака", callback_data="start_attack")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("👤 Выдать подписку", callback_data="admin_give_sub")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main")]
    ])

def get_sub_keyboard(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 1 день", callback_data=f"sub_1_{user_id}"),
         InlineKeyboardButton("📅 3 дня", callback_data=f"sub_3_{user_id}")],
        [InlineKeyboardButton("📅 7 дней", callback_data=f"sub_7_{user_id}"),
         InlineKeyboardButton("📅 30 дней", callback_data=f"sub_30_{user_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")]
    ])

def get_sessions_keyboard(user_id, page=0):
    sessions = get_user_sessions(user_id)
    if not sessions:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 По номеру", callback_data="add_by_phone")],
            [InlineKeyboardButton("📁 Загрузить файл", callback_data="upload_file")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main")]
        ])
    start_idx = page * 5
    end_idx = min(start_idx + 5, len(sessions))
    keyboard = []
    for i in range(start_idx, end_idx):
        s = sessions[i]
        keyboard.append([
            InlineKeyboardButton(
                f"📱 {s['phone']} ({s.get('reports_sent', 0)})",
                callback_data=f"select_session_{i}"
            )
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"sessions_page_{page-1}"))
    if end_idx < len(sessions):
        nav.append(InlineKeyboardButton("➡️", callback_data=f"sessions_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="main")])
    return InlineKeyboardMarkup(keyboard)

def get_attack_keyboard(idx):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ Выбрать время", callback_data=f"attack_time_{idx}")],
        [InlineKeyboardButton("⚡ Начать сейчас", callback_data=f"attack_now_{idx}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="my_sessions")]
    ])

# ==================== КОМАНДЫ ====================

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    create_user(user_id, message.from_user.username)
    
    if not has_subscription(user_id) and user_id != ADMIN_ID:
        await message.reply("🔐 Нет подписки!")
        return
    
    await message.reply(
        f"🤖 **Главное меню**\n\n"
        f"👤 {get_subscription_info(user_id)}\n"
        f"📱 Сессий: {len(get_user_sessions(user_id))}",
        reply_markup=get_main_keyboard(user_id)
    )

# ==================== ОБРАБОТКА ФАЙЛОВ (ТВОЙ КОД) ====================

@app.on_message(filters.document)
async def handle_session_file(client, message):
    user_id = message.from_user.id
    doc = message.document
    file_name = doc.file_name.lower()

    path = await message.download(file_name=os.path.join(TEMP_DIR, f"{user_id}_{doc.file_name}"))

    user_data[user_id] = {
        "file_path": path,
        "file_name": doc.file_name,
    }

    await message.reply(
        f"✅ Файл **{doc.file_name}** получен.\n\n"
        f"Напиши `/add` чтобы добавить сессию."
    )

@app.on_message(filters.command("add"))
async def add_session(client, message):
    user_id = message.from_user.id

    if user_id not in user_data:
        await message.reply("Сначала отправь файл сессии.")
        return

    data = user_data[user_id]
    file_path = data["file_path"]
    file_name = data["file_name"].lower()

    status = await message.reply("⏳ Обрабатываю сессию...")

    try:
        session_name = f"user_{user_id}_{int(time.time())}"
        session_path = os.path.join(SESSIONS_DIR, session_name)

        # ========== ОБРАБОТКА РАЗНЫХ ФОРМАТОВ ==========

        # 1. .session
        if file_name.endswith(".session"):
            shutil.copy(file_path, session_path + ".session")
            final_session = session_path

            phone_match = re.search(r'(\+?\d{10,15})', doc.file_name)
            phone = phone_match.group(0) if phone_match else session_name
            
            if add_user_session(user_id, session_name, phone):
                await status.edit(f"✅ Сессия добавлена!\n📱 {phone}")
            else:
                await status.edit(f"⚠️ Сессия уже существует!")

        # 2. .zip
        elif file_name.endswith((".zip", ".rar", ".7z")):
            extract_dir = os.path.join(TEMP_DIR, f"extract_{user_id}_{int(time.time())}")
            os.makedirs(extract_dir, exist_ok=True)
            shutil.unpack_archive(file_path, extract_dir)

            found = False
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    if f.endswith('.session'):
                        session_name = f.replace('.session', '')
                        session_path = os.path.join(SESSIONS_DIR, f)
                        shutil.copy2(os.path.join(root, f), session_path)
                        
                        phone_match = re.search(r'(\+?\d{10,15})', session_name)
                        phone = phone_match.group(0) if phone_match else session_name
                        
                        if add_user_session(user_id, session_name, phone):
                            found = True
                            await status.edit(f"✅ Добавлена сессия: {phone}")
                        break
                if found:
                    break

            if not found:
                tdata_path = None
                for root, dirs, files in os.walk(extract_dir):
                    if "tdata" in dirs:
                        tdata_path = os.path.join(root, "tdata")
                        break
                    if os.path.basename(root).lower() == "tdata":
                        tdata_path = root
                        break

                if tdata_path:
                    try:
                        temp_client = Client(
                            f"tdata_{user_id}_{int(time.time())}",
                            api_id=API_ID,
                            api_hash=API_HASH,
                            workdir=SESSIONS_DIR
                        )
                        await temp_client.start()
                        me = await temp_client.get_me()
                        phone = me.phone_number
                        session_name = session_name_for_phone(phone)
                        await temp_client.stop()

                        old_session = os.path.join(SESSIONS_DIR, f"{temp_client.name}.session")
                        new_session = os.path.join(SESSIONS_DIR, f"{session_name}.session")
                        if os.path.exists(old_session):
                            shutil.move(old_session, new_session)

                        if add_user_session(user_id, session_name, phone):
                            await status.edit(f"✅ Конвертирован tdata: {phone}")
                        else:
                            await status.edit(f"⚠️ Сессия {session_name} уже существует!")
                    except Exception as e:
                        await status.edit(f"❌ Ошибка tdata: {e}")

            shutil.rmtree(extract_dir, ignore_errors=True)

        # 3. .txt
        elif file_name.endswith(".txt"):
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.read().strip().split('\n')
            
            added = 0
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2:
                        phone = parts[0].strip()
                        password = parts[1].strip()
                        session_name = session_name_for_phone(phone)
                        try:
                            temp_client = Client(
                                session_name,
                                api_id=API_ID,
                                api_hash=API_HASH,
                                workdir=SESSIONS_DIR
                            )
                            await temp_client.start()
                            await temp_client.stop()
                            
                            if add_user_session(user_id, session_name, phone):
                                added += 1
                        except Exception as e:
                            continue
                
                elif re.match(r'^\+?\d{10,15}$', line):
                    phone = line
                    session_name = session_name_for_phone(phone)
                    session_path = os.path.join(SESSIONS_DIR, f"{session_name}.session")
                    
                    if os.path.exists(session_path):
                        if add_user_session(user_id, session_name, phone):
                            added += 1
            
            if added > 0:
                await status.edit(f"✅ Добавлено {added} сессий из .txt")
            else:
                await status.edit("❌ Не найдено сессий в .txt")

        else:
            await status.edit("❌ Неизвестный формат!")

    except Exception as e:
        await status.edit(f"❌ Ошибка: {e}")

    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        if user_id in user_data:
            del user_data[user_id]

# ==================== ОБРАБОТЧИК КНОПОК ====================

@app.on_callback_query()
async def button_handler(client, callback):
    user_id = callback.from_user.id
    data = callback.data
    
    if data == "main":
        await callback.message.edit_text(
            "🤖 **Главное меню**",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    # ===== АДМИН =====
    if data == "admin_panel":
        if user_id != ADMIN_ID:
            await callback.answer("❌ Доступ запрещен!", show_alert=True)
            return
        await callback.message.edit_text("👑 **Админ-панель**", reply_markup=get_admin_keyboard())
        return
    
    if data == "admin_users":
        if user_id != ADMIN_ID:
            return
        users = load_users()
        text = "📋 **Пользователи:**\n\n"
        for u in users["users"]:
            text += f"👤 {u['username']} ({u['user_id']})\n"
            text += f"   Подписка: {get_subscription_info(u['user_id'])}\n"
            text += f"   Сессий: {len(u.get('sessions', []))}\n"
            text += f"   Жалоб: {u.get('reports_sent', 0)}\n\n"
        await callback.message.edit_text(
            text[:4000],
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")]])
        )
        return
    
    if data == "admin_give_sub":
        if user_id != ADMIN_ID:
            return
        await callback.message.edit_text(
            "👤 **Выдача подписки**\n\nОтправь ID пользователя:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")]])
        )
        user_data[user_id] = {"step": "waiting_sub"}
        return
    
    if data.startswith("sub_"):
        if user_id != ADMIN_ID:
            return
        parts = data.split("_")
        days = int(parts[1])
        target_user = int(parts[2])
        if add_subscription(target_user, days):
            await callback.message.edit_text(f"✅ Подписка на {days} дней выдана!", reply_markup=get_admin_keyboard())
        else:
            await callback.message.edit_text("❌ Пользователь не найден!", reply_markup=get_admin_keyboard())
        return
    
    if data == "admin_stats":
        if user_id != ADMIN_ID:
            return
        users = load_users()
        total = len(users["users"])
        total_reports = sum(u.get("reports_sent", 0) for u in users["users"])
        total_sessions = sum(len(u.get("sessions", [])) for u in users["users"])
        await callback.message.edit_text(
            f"📊 **Статистика бота**\n\n"
            f"👥 Пользователей: {total}\n"
            f"📱 Сессий всего: {total_sessions}\n"
            f"📤 Жалоб всего: {total_reports}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")]])
        )
        return
    
    # ===== МОИ СЕССИИ =====
    if data == "my_sessions":
        await callback.message.edit_text("📋 **Мои сессии**", reply_markup=get_sessions_keyboard(user_id))
        return
    
    if data.startswith("sessions_page_"):
        page = int(data.split("_")[2])
        await callback.message.edit_text("📋 **Мои сессии**", reply_markup=get_sessions_keyboard(user_id, page))
        return
    
    if data.startswith("select_session_"):
        idx = int(data.split("_")[2])
        sessions = get_user_sessions(user_id)
        if idx >= len(sessions):
            return
        session = sessions[idx]
        await callback.message.edit_text(
            f"📱 **Сессия:** {session['phone']}\n"
            f"📤 Жалоб: {session.get('reports_sent', 0)}\n"
            f"📅 Добавлена: {session['added_at'][:10]}",
            reply_markup=get_attack_keyboard(idx)
        )
        return
    
    # ===== АТАКА =====
    if data == "start_attack":
        sessions = get_user_sessions(user_id)
        if not sessions:
            await callback.message.edit_text("❌ Нет сессий!", reply_markup=get_main_keyboard(user_id))
            return
        await callback.message.edit_text("📎 Отправь ссылку: `t.me/username`")
        user_data[user_id] = {"step": "waiting_link"}
        return
    
    if data == "add_by_phone":
        await callback.message.edit_text("📱 Отправь номер: `+79991234567`")
        user_data[user_id] = {"step": "waiting_phone"}
        return
    
    if data == "upload_file":
        await callback.message.edit_text(
            "📁 **Отправь файл:**\n\n"
            "• `.session`\n"
            "• `.zip` с `.session`\n"
            "• `.zip` с `tdata`\n"
            "• `.txt` с номерами"
        )
        user_data[user_id] = {"step": "waiting_file"}
        return
    
    if data == "stats":
        user = get_user(user_id)
        sessions = get_user_sessions(user_id)
        text = (
            f"📊 **Твоя статистика**\n\n"
            f"👤 {user['username']}\n"
            f"📅 {get_subscription_info(user_id)}\n"
            f"📱 Сессий: {len(sessions)}\n"
            f"📤 Жалоб: {user.get('reports_sent', 0)}"
        )
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main")]])
        )
        return

# ==================== ОБРАБОТКА ТЕКСТА ====================

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Ожидание номера для подписки (админ)
    if user_data.get(user_id, {}).get("step") == "waiting_sub":
        if user_id != ADMIN_ID:
            return
        try:
            target_id = int(text)
            user = get_user(target_id)
            if user:
                await message.reply(
                    f"👤 Пользователь: {user['username']}\n"
                    f"📅 Статус: {get_subscription_info(target_id)}\n\n"
                    f"Выбери срок:",
                    reply_markup=get_sub_keyboard(target_id)
                )
                user_data[user_id]["step"] = None
            else:
                await message.reply("❌ Пользователь не найден!")
        except:
            await message.reply("❌ Введи числовой ID!")
        return
    
    # Ожидание номера для авторизации
    if user_data.get(user_id, {}).get("step") == "waiting_phone":
        if not re.match(r'^\+\d{10,15}$', text):
            await message.reply("❌ Неверный формат! Используй: +79991234567")
            return
        
        try:
            temp_client = Client(
                f"temp_{user_id}_{int(time.time())}",
                api_id=API_ID,
                api_hash=API_HASH,
                workdir=SESSIONS_DIR
            )
            await temp_client.connect()
            sent_code = await temp_client.send_code(text)
            
            auth_data[user_id] = {
                "client": temp_client,
                "phone": text,
                "phone_code_hash": sent_code.phone_code_hash
            }
            
            await message.reply(f"✅ Код отправлен на {text}\n\nОтправь код:")
            user_data[user_id]["step"] = "waiting_code"
        except Exception as e:
            await message.reply(f"❌ Ошибка: {e}")
            user_data[user_id]["step"] = None
        return
    
    # Ожидание кода
    if user_data.get(user_id, {}).get("step") == "waiting_code":
        if user_id not in auth_data:
            await message.reply("❌ Сессия не найдена!")
            user_data[user_id]["step"] = None
            return
        
        if not text or not text.isdigit():
            await message.reply("❌ Введи код цифрами!")
            return
        
        auth_info = auth_data[user_id]
        try:
            await auth_info["client"].sign_in(auth_info["phone"], text, auth_info["phone_code_hash"])
            session_name = session_name_for_phone(auth_info["phone"])
            await auth_info["client"].stop()
            
            if add_user_session(user_id, session_name, auth_info["phone"]):
                await message.reply(f"✅ Авторизация успешна!\n📞 {auth_info['phone']}")
            else:
                await message.reply(f"⚠️ Сессия уже существует!")
            
            del auth_data[user_id]
            user_data[user_id]["step"] = None
        except Exception as e:
            await message.reply(f"❌ Ошибка: {e}")
        return
    
    # Ожидание ссылки для атаки
    if user_data.get(user_id, {}).get("step") == "waiting_link":
        if text.startswith(('t.me/', 'https://t.me/')):
            await message.reply(f"📎 Ссылка сохранена: {text}\n\nВыбери сессию для отправки:", reply_markup=get_sessions_keyboard(user_id))
            user_data[user_id]["link"] = text
            user_data[user_id]["step"] = None
        else:
            await message.reply("❌ Неверный формат! Используй: t.me/username")
        return

# ==================== ЗАПУСК ====================

print("=" * 50)
print("🤖 БОТ ЗАПУЩЕН!")
print(f"🔐 API ID: {API_ID}")
print(f"👑 Админ: {ADMIN_ID}")
print("=" * 50)

app.run()