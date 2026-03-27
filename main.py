# Created By @Lohit_69
import time
from datetime import datetime
import pytz
import os
import json
import threading
import requests
import traceback
import phonenumbers
from phonenumbers import geocoder
from datetime import datetime
import telebot
from telebot import types
from io import BytesIO
from playwright.sync_api import sync_playwright
from queue import Queue
task_queue = Queue()

# ================ CONFIGURATION ================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

PANEL_USER = os.getenv("PANEL_USER")
PANEL_PASS = os.getenv("PANEL_PASS")

LOGIN_URL = "https://www.orangecarrier.com/login"
LOGOUT_URL = "https://www.orangecarrier.com/logout"
AUDIO_BASE_URL = "https://www.orangecarrier.com/live/calls/sound"

MY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

LOHIT_BRANDING = "◈ <b><i>AHNAF TAHMID LOHIT</i></b> ◈"

bot = telebot.TeleBot(BOT_TOKEN)
session = requests.Session()
session.headers.update({"User-Agent": MY_USER_AGENT})

IS_SCRAPPING = False
TOTAL_CAPTURED = 0
SESSION_STATUS = "🔴 Offline"
HUD_MESSAGE_ID = None
CMD_LOGIN_REQUESTED = False
CMD_LOGOUT_REQUESTED = False
CMD_REFRESH_REQUESTED = False

# ✅ ADDED: Threading Lock for safe concurrency
lock = threading.Lock()
active_calls = {} 
processed_uuids = set()
LAST_EVENT_TIME = time.time()
POPUP_DONE = False
pending_messages = {}

PLAYWRIGHT_INST = None
BROWSER = None
CONTEXT = None
PAGE = None

# ================ LOGGING HELPERS ================
def log_terminal(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

def smart_log(text, duration=5):
    try:
        msg = bot.send_message(ADMIN_ID, f"📢 <b>Log:</b> {text}", parse_mode="HTML")
        threading.Timer(duration, lambda: bot.delete_message(ADMIN_ID, msg.message_id) if msg else None).start()
    except Exception:
        log_terminal("⚠️ WORKER ERROR:")
        log_terminal(traceback.format_exc())
        time.sleep(5)

# ================ HELPER FUNCTIONS ================
def get_flag_emoji(country_code):
    if not country_code or not isinstance(country_code, str): return "🌍"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_country_info(phone):
    try:
        phone_str = str(phone).lstrip('+')
        parsed_number = phonenumbers.parse("+" + phone_str)
        country_name = geocoder.description_for_number(parsed_number, "en")
        region_code = phonenumbers.region_code_for_number(parsed_number)
        return (country_name or "International"), get_flag_emoji(region_code)
    except: return "International"

# ✅ ADDED: Country Smart Detect
def get_country_smart(did, termination=""):
    try:
        country_name, flag = get_country_info(did)
        if country_name == "International" and termination:
            country_name = termination.split()[0]
        return country_name, flag
    except:
        return "International"

def build_audio_caption(did, country_name, flag):
    bd_time = datetime.now(pytz.timezone("Asia/Dhaka"))

    return (
        f"📢 <b>New Telegram Voice {flag} Received</b> 🔔\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        
        f"🌍 <b>Country :</b> {country_name} {flag}\n"
        f"☎️ <b>Number  :</b> <code>{did}</code>\n"
        f"⏰ <b>Date & Time :</b> <code>{bd_time.strftime('%Y-%m-%d')} » {bd_time.strftime('%I:%M:%S %p')}</code>\n\n"
        
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ <b><i>DEVELOPED BY</i></b> » <a href='https://t.me/Lohit_69'><i>[ Lohit_69 ] 🔥</i></a>"
    )
def extract_calls(calls_raw):
    result = []
    for item in calls_raw:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result


# ===== PENDING MESSAGE SYSTEM (ADD HERE) =====

def send_pending_call(did):
    delete_pending(did)

    text = (
        "📡 <b>New Incoming Call Detected</b>\n\n"
        f"📞 Number : <code>{did}</code>\n"
        f"⏳ Please wait for the call to end..."
    )

    try:
        msg = bot.send_message(GROUP_CHAT_ID, text, parse_mode="HTML")
        pending_messages[did] = msg.message_id
    except:
        pass


def delete_pending(did):
    try:
        if did in pending_messages:
            bot.delete_message(GROUP_CHAT_ID, pending_messages[did])
            pending_messages.pop(did, None)
    except:
        pass


# ================ AUDIO FETCH ================
# ✅ FIXED & INTEGRATED: Audio Fetch + Send (Retry Safe + Play Click)
def handle_call_trigger(did, uuid, duration, termination):
    global TOTAL_CAPTURED, CONTEXT
    
    headers = {
        "Referer": "https://www.orangecarrier.com/live/calls",
        "User-Agent": MY_USER_AGENT,
        "Accept": "*/*"
    }

    # 🔴 Step 1: Click Play Safely with Lock
# ⏳ Small wait to ensure backend audio ready
    time.sleep(2)
    log_terminal(f"🎙️ Fetching audio for Call: {did} (UUID: {uuid})")
    
    if CONTEXT:
        try:
            for cookie in CONTEXT.cookies():
                session.cookies.set(cookie['name'], cookie['value'])
        except:
            pass
            
    url = f"{AUDIO_BASE_URL}?did={did}&uuid={uuid}"

    for i in range(3):
        try:
            response = session.get(url, headers=headers, timeout=21)
            
            if response.status_code == 200 and "audio" in response.headers.get("Content-Type", ""):
                if "audio" not in response.headers.get("Content-Type", ""):
                    continue
                country_name, flag = get_country_smart(did, termination)
                
                caption = build_audio_caption(did, country_name, flag)
                
                audio_file = BytesIO(response.content)
                audio_file.name = "call.ogg"
                audio_file.seek(0)

                try:
                    bot.send_voice(GROUP_CHAT_ID, audio_file, caption=caption, parse_mode="HTML")
                    delete_pending(did)
                    TOTAL_CAPTURED += 1
                    log_terminal(f"✅ Voice sent successfully for {did}")
                    
                    with lock:
                        active_calls.pop(uuid, None)
                    return
                except Exception as e:
                    log_terminal(f"TG VOICE ERROR → {e}")
                    
        except Exception as e:
            log_terminal(f"FETCH ERROR → {e}")
            
        time.sleep(1.5)

    # ❌ Failed after retries
    log_terminal(f"❌ Audio Fetch Fail after retries")
    country_name, _ = get_country_smart(did, termination)
    send_fail_message(did, duration, country_name)
    with lock:
        active_calls.pop(uuid, None)

# ================ ✅ TOP LEVEL WS HANDLER ================
def handle_ws(ws):
    log_terminal(f"🌐 WS FOUND → {ws.url}")

    if "socket.io" in ws.url:
        log_terminal("✅ TARGET WS CONNECTED")

        def debug_frame(payload):
            try:
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8", errors="ignore")

                log_terminal(f"📦 WS DATA → {payload[:200]}")
            except:
                pass

            handle_socket_frame(payload)

        ws.on("framereceived", debug_frame)
        
# ================ ✅ FINAL SOCKET HANDLER ================
# ✅ FIXED: Main WS Handler logic implemented
def handle_socket_frame(payload):
    global active_calls, processed_uuids, LAST_EVENT_TIME
    if not IS_SCRAPPING: return

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="ignore")

    try:
        if not payload.startswith("42"): return

        try:
            json_part = payload[2:]
            end = json_part.rfind("]")
            if end != -1: json_part = json_part[:end+1]
            data = json.loads(json_part)
        except: return

        LAST_EVENT_TIME = time.time()
        
        if not isinstance(data, list) or len(data) < 2: return
        
        event = data[0]
        if event != "call": return
        
        content = data[1]
        calls_data = content.get("calls", {})

        calls_list = extract_calls(calls_data.get("calls", []))
        ended_calls = calls_data.get("end", [])

        # 🔴 Handle active calls
        for c in calls_list:
            did = c.get("dest")
            uuid = c.get("uuid")
            duration = int(c.get("duration", 0))
            termination = c.get("termination", "")

            if not did or not uuid: continue

            with lock:
                if uuid not in active_calls and uuid not in processed_uuids:
                    active_calls[uuid] = {
                        "did": did,
                        "termination": termination,
                        "tried": set()
                    }
                    log_terminal(f"🆕 CALL DETECTED → {did} ({duration}s)")
                    try: 
                        send_pending_call(did)
                    except Exception as e: 
                        log_terminal(f"TG SEND ERROR → {e}")

            call_obj = active_calls.get(uuid)
            if not call_obj: continue

            # 🔥 18-21 sec retry logic
            TRIGGER_SECONDS = [18, 19, 20, 21]

            for sec in TRIGGER_SECONDS:

                # 🔴 STRICT MATCH for 18
                if sec == 18:
                    if duration != 18:
                        continue
                else:
                    if duration < sec:
                        continue

                with lock:
                    if uuid in processed_uuids:
                        break

                    if sec in call_obj["tried"]:
                        continue

                    call_obj["tried"].add(sec)
                    processed_uuids.add(uuid)

                # 🎯 LOGIC
                if sec == 18:
                    log_terminal(f"🎯 MAIN TRIGGER → {did} ({duration}s)")
                else:
                    log_terminal(f"⚠️ FALLBACK TRIGGER → {did} ({duration}s @ {sec})")

                task_queue.put((did, uuid, duration, termination))

                break

        # 🔴 Handle ended calls (fail before 18s)
        for c in ended_calls:
            did = c.get("dest")
            uuid = c.get("uuid")
            duration = int(c.get("duration", 0))

            with lock:
                if uuid in active_calls and duration < 18:
                    country_name, _ = get_country_smart(did)
                    send_fail_message(did, duration, f"Ended Early ({country_name})")
                    active_calls.pop(uuid, None)

        with lock:
            if len(processed_uuids) > 1000: processed_uuids.clear()
            if len(active_calls) > 1000: active_calls.clear()

    except Exception as e:
        log_terminal(f"SOCKET ERROR → {e}")

# ================ POPUP HANDLER ================
def handle_account_popup(page):
    global POPUP_DONE
    if POPUP_DONE:
        return

    try:
        if page.locator("text=Account Code").count() > 0:
            log_terminal("⚠️ Popup Step 1 detected")
            page.locator("button:has-text('Next')").click()
            page.wait_for_timeout(500)

        if page.locator("text=generate a code").count() > 0:
            log_terminal("⚠️ Popup Step 2 detected")
            page.locator("button:has-text('Done')").click()
            page.wait_for_timeout(500)

        POPUP_DONE = True
        log_terminal("✅ Popup handled")

    except Exception as e:
        log_terminal(f"Popup skip → {e}")

# ================ ✅ STABLE BROWSER WORKER ================
def browser_worker():
    global SESSION_STATUS, BROWSER, CONTEXT, PAGE, PLAYWRIGHT_INST, IS_SCRAPPING
    global CMD_LOGIN_REQUESTED, CMD_LOGOUT_REQUESTED, CMD_REFRESH_REQUESTED
    global LAST_EVENT_TIME, TOTAL_CAPTURED
    
    log_terminal("🚀 Playwright Starting (Single Thread Mode)...")
    PLAYWRIGHT_INST = sync_playwright().start()

    while True:
        if not CMD_LOGIN_REQUESTED and not IS_SCRAPPING:
            time.sleep(1)
            continue
        try:
            if CMD_LOGOUT_REQUESTED:
                SESSION_STATUS = "🟡 Logging out..."
                update_active_hud()
                smart_log("Logging out of Panel...")

                try:
                    if PAGE:
                        PAGE.close()
                    if CONTEXT:
                        CONTEXT.close()
                    if BROWSER:
                        BROWSER.close()
                except:
                    pass

                # 🔥 FULL RESET
                PAGE = None
                CONTEXT = None
                BROWSER = None

                active_calls.clear()
                processed_uuids.clear()
                pending_messages.clear()

                IS_SCRAPPING = False
                CMD_LOGIN_REQUESTED = False
                CMD_LOGOUT_REQUESTED = False

                SESSION_STATUS = "🔴 Logged Out"
                smart_log("✅ Full Reset Done")
                update_active_hud()
                            
            if CMD_LOGIN_REQUESTED:
                SESSION_STATUS = "🟡 Logging in..."
                update_active_hud()
                smart_log("🔑 Logging into Orange Carrier...")

        # 🔥 LAUNCH BROWSER (STEALTH + RAILWAY SAFE)
            if CMD_LOGIN_REQUESTED:
                BROWSER = PLAYWRIGHT_INST.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--window-size=1280,720"
                    ]
                )

                if CONTEXT: CONTEXT.close()

        # 🔥 CONTEXT (REALISTIC ENVIRONMENT)
                CONTEXT = BROWSER.new_context(
                    user_agent=MY_USER_AGENT,
                    viewport={"width": 1280, "height": 720},
                    locale="en-US",
                    timezone_id="Asia/Dhaka"
                )

                PAGE = CONTEXT.new_page()

        # 🔥 STEALTH SCRIPT (ANTI-DETECTION)
                PAGE.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
                """)

                log_terminal("🔑 Navigating to Login...")
                PAGE.goto(LOGIN_URL)

                PAGE.type('input[name="email"]', PANEL_USER, delay=80)
                PAGE.wait_for_timeout(500)
                PAGE.fill('input[name="password"]', PANEL_PASS)

                PAGE.locator('#loginSubmit').click()
                PAGE.wait_for_load_state("domcontentloaded")

                # ✅ popup wait
                PAGE.wait_for_timeout(2000)
                handle_account_popup(PAGE)

                # ✅ then go live calls
                log_terminal("📡 Navigating to Live Calls...")
                PAGE.goto("https://www.orangecarrier.com/live/calls")

                # ✅ THEN attach WS
                try:
                    PAGE.remove_listener("websocket", handle_ws)
                except:
                    pass

                PAGE.on("websocket", handle_ws)

                log_terminal(f"🌐 AFTER LOGIN URL → {PAGE.url}")

                if "orangecarrier.com" in PAGE.url and "login" not in PAGE.url:
                    SESSION_STATUS = "🟢 Valid"
                    smart_log("✅ Login Success!")
                else:
                    SESSION_STATUS = "❌ Failed"
                    smart_log("❌ Login Failed. Check credentials.")

                CMD_LOGIN_REQUESTED = False
                update_active_hud()

            if SESSION_STATUS == "🟢 Valid" and PAGE is not None:
                try:
                    PAGE.bring_to_front()
                except:
                    pass

                # 🔄 SAFE REFRESH (ONLY WORKER THREAD)
                if CMD_REFRESH_REQUESTED:
                    try:
                        log_terminal("🔄 Performing Safe Refresh...")

                        if PAGE:
                            PAGE.reload(wait_until="domcontentloaded")

                            try:
                                PAGE.remove_listener("websocket", handle_ws)
                            except:
                                pass

                            PAGE.on("websocket", handle_ws)

                            smart_log("✅ Refresh Completed")

                    except Exception as e:
                        log_terminal(f"Refresh Error → {e}")
                        CMD_LOGIN_REQUESTED = True

                    CMD_REFRESH_REQUESTED = False

                # 🔥 ADD THIS BLOCK HERE (QUEUE PROCESSOR)
                while not task_queue.empty():
                    did, uuid, duration, termination = task_queue.get()
                    try:
                        handle_call_trigger(did, uuid, duration, termination)
                    except Exception as e:
                        log_terminal(f"TASK ERROR → {e}")


            if time.time() - LAST_EVENT_TIME > 300 and not active_calls:
                log_terminal("♻️ Safe reload (Idle)")
                try:
                    PAGE.reload(wait_until="domcontentloaded")

                    # 🔥 WS reattach after reload
                    try:
                        PAGE.remove_listener("websocket", handle_ws)
                    except:
                        pass

                    PAGE.on("websocket", handle_ws)

                    LAST_EVENT_TIME = time.time()
                    smart_log("♻️ Page Reloaded (Idle Keep-alive)")

                except Exception as e:
                    log_terminal(f"⚠️ Reload error: {e}")

                try: PAGE.evaluate("() => document.body.dispatchEvent(new Event('mousemove'))")
                except: pass
                time.sleep(2)
            else:
                time.sleep(2)

        except Exception as e:
            log_terminal(f"⚠️ Worker Error: {e}")
            time.sleep(10)

def send_fail_message(did, duration, country):
    text = (
        f"❌ <b>FAILED TO FETCH THE CALL</b> ❌\n\n"
        f"☎️ Number: <code>{did}</code>\n"
        f"🌍 Country: {country}\n"
        f"{LOHIT_BRANDING}"
    )

    delete_pending(did)

    try:
        bot.send_message(GROUP_CHAT_ID, text, parse_mode="HTML")
    except:
        pass
# ================ HUD & COMMANDS ================
def build_hud_text():
    status = "🟢 SCRAPING" if IS_SCRAPPING else "🔴 STOPPED"
    return (
    f"🎮 <b>ORANGE PANEL HUD</b>\n"
    f"━━━━━━━━━━━━━━━━━━━━\n"
    f"🛰 Status: <code>{status}</code>\n"
    f"📩 Total Fetched: <code>{TOTAL_CAPTURED}</code>\n"
    f"🔑 Session: <code>{SESSION_STATUS}</code>\n"
    f"━━━━━━━━━━━━━━━━━━━━\n\n"
    f"{LOHIT_BRANDING}"
)

def build_hud_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("▶️ START", callback_data="start_sc"),
               types.InlineKeyboardButton("⏸ STOP", callback_data="stop_sc"),
               types.InlineKeyboardButton("🔄 REFRESH", callback_data="refresh_sess"),
               types.InlineKeyboardButton("🚪 LOGOUT", callback_data="logout_panel"))
    return markup

def update_active_hud():
    if HUD_MESSAGE_ID:
        try: bot.edit_message_text(chat_id=ADMIN_ID, message_id=HUD_MESSAGE_ID, text=build_hud_text(), reply_markup=build_hud_markup(), parse_mode="HTML")
        except: pass

@bot.message_handler(commands=['start', 'hud'])
def send_hud(message):
    global HUD_MESSAGE_ID
    if message.from_user.id == ADMIN_ID:
        sent = bot.send_message(message.chat.id, build_hud_text(), reply_markup=build_hud_markup(), parse_mode="HTML")
        HUD_MESSAGE_ID = sent.message_id
        smart_log("HUD Started/Refreshed.")

@bot.callback_query_handler(func=lambda call: call.from_user.id == ADMIN_ID)
def handle_query(call):
    global IS_SCRAPPING, CMD_LOGIN_REQUESTED, CMD_LOGOUT_REQUESTED
    bot.answer_callback_query(call.id)
    if call.data == "start_sc":
        IS_SCRAPPING = True
        CMD_LOGIN_REQUESTED = True
        smart_log("🚀 Fresh Start Initiated")
    elif call.data == "stop_sc":
        IS_SCRAPPING = False
        smart_log("⏸ Scraping Stopped")
    elif call.data == "refresh_sess":
        global CMD_REFRESH_REQUESTED
        CMD_REFRESH_REQUESTED = True
        smart_log("🔄 Refresh Requested")
    elif call.data == "logout_panel":
        CMD_LOGOUT_REQUESTED = True
    update_active_hud()

# ================ MAIN ENTRY ================
if __name__ == "__main__":
    log_terminal("🤖 Bot Process Started...")
    threading.Thread(target=browser_worker, daemon=True).start()
    bot.infinity_polling()
