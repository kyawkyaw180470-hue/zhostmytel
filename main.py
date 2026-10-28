import json
import asyncio
import aiohttp
import base64
from api_client import get_game_token, game_start, game_reward, game_stop, get_reward_history

# ယာယီ Memory သိမ်းဆည်းမှု (Cloudflare KV ကို နောက်မှ ချိတ်ပါမယ်)
user_data = {}

# ==========================================
# Helper Functions (Telegram API ခေါ်ရန်)
# ==========================================
async def tg_request(bot_token, method, payload):
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as res:
            return await res.json()

async def edit_msg(bot_token, chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    await tg_request(bot_token, "editMessageText", payload)

async def send_msg(bot_token, chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return await tg_request(bot_token, "sendMessage", payload)

# ==========================================
# Cloudflare Worker Entry Point
# ==========================================
async def on_fetch(request, env):
    if request.method != "POST":
        return await request.respond("Bot is running 24/7!", status=200)

    try:
        update = await request.json()
        bot_token = env.BOT_TOKEN  # Cloudflare မှာ BOT_TOKEN ထည့်ရမယ်

        # Webhook ကို ချက်ချင်း Response ပြန်မယ် (Timeout မဖြစ်အောင်)
        asyncio.create_task(process_update(update, bot_token, env))
        
        return await request.respond("OK", status=200)
    except Exception as e:
        return await request.respond(f"Error: {str(e)}", status=500)

async def process_update(update, bot_token, env):
    if "message" in update:
        await handle_message(update["message"], bot_token)
    elif "callback_query" in update:
        await handle_callback(update["callback_query"], bot_token)

# ==========================================
# Text Message Handler (Login ဝင်ခြင်း)
# ==========================================
async def handle_message(message, bot_token):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    message_id = message["message_id"]
    user_id = str(message["from"]["id"])

    # User ရိုက်လိုက်တဲ့ စာကို ချက်ချင်းဖျက်မယ် (လုံခြုံရေး)
    await tg_request(bot_token, "deleteMessage", {"chat_id": chat_id, "message_id": message_id})

    if user_id not in user_data:
        user_data[user_id] = {}

    # ၁။ ဖုန်းနံပါတ် စစ်ဆေးခြင်း
    if "phone" not in user_data[user_id]:
        if len(text) == 11 and text.startswith("09"):
            user_data[user_id]["phone"] = text
            msg = await send_msg(bot_token, chat_id, "⏳ Requesting OTP...")
            
            url = f"https://apis.mytel.com.mm/myid/authen/v1.0/login/method/otp/get-otp?phoneNumber={text}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={"accept-language": "my", "user-agent": "okhttp/4.12.0"}) as res:
                    res_data = await res.json()
                    if res_data.get("errorCode") == 200:
                        await edit_msg(bot_token, chat_id, msg["result"]["message_id"], "✅ OTP sent! Please enter the 6-digit code:")
                    else:
                        await edit_msg(bot_token, chat_id, msg["result"]["message_id"], f"❌ Error: {res_data.get('message')}")
                        del user_data[user_id]["phone"]
        else:
            await send_msg(bot_token, chat_id, "❌ Invalid phone number. Please send 09xxxxxxxxx.")
        return

    # ၂။ OTP စစ်ဆေးခြင်း
    if "access_token" not in user_data[user_id]:
        phone = user_data[user_id]["phone"]
        device_id = "48fb6af05fad838"
        msg = await send_msg(bot_token, chat_id, "⏳ Verifying OTP...")
        
        url = "https://apis.mytel.com.mm/myid/authen/v1.0/login/method/otp/validate-otp"
        body = {
            "appVersion": "2.0.16", "buildVersionApp": "300", "deviceId": device_id,
            "imei": device_id, "os": "ANDROID Redmi K30 5G", "osApp": "ANDROID",
            "password": text, "phoneNumber": phone, "version": "12"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers={"content-type": "application/json"}, json=body) as res:
                res_data = await res.json()
                if res_data.get("errorCode") == 200:
                    access_token = res_data["result"]["access_token"]
                    payload = access_token.split(".")[1]
                    payload += "=" * (-len(payload) % 4)
                    uuid = json.loads(base64.b64decode(payload)).get("sub", "")
                    
                    user_data[user_id]["access_token"] = access_token
                    user_data[user_id]["uuid"] = uuid
                    user_data[user_id]["mode"] = "safe" # Default Mode
                    
                    # Game Token ဆွဲမယ်
                    game_token = await get_game_token(access_token, phone, uuid)
                    user_data[user_id]["game_token"] = game_token
                    
                    await show_main_menu(bot_token, chat_id, msg["result"]["message_id"])
                else:
                    await edit_msg(bot_token, chat_id, msg["result"]["message_id"], f"❌ OTP Error: {res_data.get('message')}")

# ==========================================
# UI Menus
# ==========================================
async def show_main_menu(bot_token, chat_id, message_id=None):
    text = "🏠 <b>Main Menu</b>\nWelcome back! Please select a service."
    keyboard = {
        "inline_keyboard": [
            [{"text": "👤 Profile", "callback_data": "profile"}, {"text": "💰 Balance", "callback_data": "balance"}],
            [{"text": "🎮 MyID GO Game", "callback_data": "game_menu"}],
            [{"text": "🚪 Logout", "callback_data": "logout"}]
        ]
    }
    if message_id:
        await edit_msg(bot_token, chat_id, message_id, text, keyboard)
    else:
        await send_msg(bot_token, chat_id, text, keyboard)

async def show_game_menu(bot_token, chat_id, message_id, user_id):
    mode = user_data[user_id].get("mode", "safe")
    safe_btn = "✅ 🛡️ Safe Mode" if mode == "safe" else "🛡️ Safe Mode"
    fast_btn = "✅ ⚡ Fast Mode" if mode == "fast" else "⚡ Fast Mode"
    mode_text = "🛡️ Safe Mode (Normal)" if mode == "safe" else "⚡ Fast Mode (30s)"
    
    text = (
        f"🎮 <b>MyID GO (Jackfruit Collector)</b>\n\n"
        f"<b>Current Mode:</b> {mode_text}\n"
        f"Select a mode to play:"
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": safe_btn, "callback_data": "set_safe"}, {"text": fast_btn, "callback_data": "set_fast"}],
            [{"text": "▶️ Start Game", "callback_data": "play"}],
            [{"text": "🏆 Leaderboard", "callback_data": "rank"}],
            [{"text": "🔙 Main Menu", "callback_data": "main_menu"}]
        ]
    }
    await edit_msg(bot_token, chat_id, message_id, text, keyboard)

# ==========================================
# Callback Query Handler (Button နှိပ်ခြင်း)
# ==========================================
async def handle_callback(query, bot_token):
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]
    user_id = str(query["from"]["id"])
    data = query["data"]
    
    # Telegram ကို ချက်ချင်း Answer ပြန်မယ် (Loading လေးပျောက်သွားအောင်)
    await tg_request(bot_token, "answerCallbackQuery", {"callback_query_id": query["id"]})

    if user_id not in user_data or "access_token" not in user_data[user_id]:
        await edit_msg(bot_token, chat_id, message_id, "⚠️ Session Expired. Please send /start again.")
        return

    if data == "main_menu":
        await show_main_menu(bot_token, chat_id, message_id)
        
    elif data == "game_menu":
        await show_game_menu(bot_token, chat_id, message_id, user_id)

    elif data == "set_safe":
        user_data[user_id]["mode"] = "safe"
        await show_game_menu(bot_token, chat_id, message_id, user_id)

    elif data == "set_fast":
        user_data[user_id]["mode"] = "fast"
        await show_game_menu(bot_token, chat_id, message_id, user_id)

    elif data == "play":
        # ဂိမ်းကစားခြင်း Logic (Async Loop)
        mode = user_data[user_id].get("mode", "safe")
        await edit_msg(bot_token, chat_id, message_id, "🎮 <b>Starting Game...</b>")
        
        # နောက်ကွယ်ကနေ ဂိမ်းကစားမယ့် Function ကို ခေါ်မယ်
        asyncio.create_task(play_game_logic(bot_token, chat_id, message_id, user_id, mode))

    elif data == "stop_game":
        user_data[user_id]["is_playing"] = False
        await tg_request(bot_token, "answerCallbackQuery", {"callback_query_id": query["id"], "text": "Stopping game..."})

    elif data == "logout":
        if user_id in user_data:
            del user_data[user_id]
        await edit_msg(bot_token, chat_id, message_id, "✅ Logged out successfully. Send /start to login again.")

# ==========================================
# Game Loop Logic (Safe/Fast)
# ==========================================
async def play_game_logic(bot_token, chat_id, message_id, user_id, mode):
    game_token = user_data[user_id].get("game_token")
    if not game_token:
        await edit_msg(bot_token, chat_id, message_id, "❌ Game Token missing. Please login again.")
        return

    res_start = await game_start(game_token)
    if "CM_0024" in str(res_start):
        await edit_msg(bot_token, chat_id, message_id, "❌ No turns left to play.", reply_markup={"inline_keyboard":[[{"text":"🔙 Back", "callback_data":"game_menu"}]]})
        return

    user_data[user_id]["is_playing"] = True
    is_fast = (mode == "fast")
    mode_name = "Fast" if is_fast else "Safe"

    for level in range(1, 11):
        if not user_data[user_id].get("is_playing"):
            break # User က ရပ်လိုက်ရင် ထွက်မယ်

        # Progress Bar ပြမယ်
        progress = "🟩" * level + "⬜" * (10 - level)
        text = f"🎮 <b>Playing Game...</b>\n\nMode: {mode_name}\nLevel: {progress} ({level}/10)"
        
        keyboard = {"inline_keyboard": [[{"text": "🛑 Stop Game", "callback_data": "stop_game"}]]}
        await edit_msg(bot_token, chat_id, message_id, text, keyboard)

        # စောင့်ဆိုင်းချိန် (Fast = 3s, Safe = 8-26s)
        wait_time = 3 if is_fast else (8 + (level * 2))
        await asyncio.sleep(wait_time)

        # Reward ယူမယ့် Level တွေ
        if 4 <= level <= 8:
            for slot in range(1, 6):
                if not user_data[user_id].get("is_playing"): break
                await game_reward(game_token, slot)
                await asyncio.sleep(0.5)

    # ဂိမ်းပြီးဆုံးခြင်း (သို့) ရပ်လိုက်ခြင်း
    await game_stop(game_token)
    user_data[user_id]["is_playing"] = False
    
    history = await get_reward_history(game_token)
    reward_text = "🎉 <b>Game Finished!</b>\n\n<b>Rewards:</b>\n"
    try:
        rewards = history["data"]["data"]
        if rewards:
            for r in rewards[:3]:
                reward_text += f"• {r.get('value')} {r.get('reward_name')}\n"
        else:
            reward_text += "No rewards."
    except:
        reward_text += "Could not fetch rewards."

    keyboard = {"inline_keyboard": [
        [{"text": "🔁 Play Again", "callback_data": "game_menu"}],
        [{"text": "🔙 Main Menu", "callback_data": "main_menu"}]
    ]}
    await edit_msg(bot_token, chat_id, message_id, reward_text, keyboard)