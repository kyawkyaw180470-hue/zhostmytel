import aiohttp
import urllib.parse

BASE_URL = "https://apis.mytel.com.mm"
GAME_BASE_URL = "https://pubapi-mygov2.mtgmm.co/v1/engine"

async def get_game_token(access_token, phone, uuid):
    """
    Cloudflare Worker အတွက် aiohttp ကို သုံးပြီး Game Token ဆွဲထုတ်ခြင်း
    """
    url = f"{GAME_BASE_URL}/web/bootstrap.html?uuid={uuid}&mcapp=myid"
    msisdn = "+95" + phone[1:]
    
    headers = {
        "access-token": access_token,
        "phone-number": msisdn,
        "avatar": "default",
        "fullname": phone,
        "Accept": "text/html,application/json",
        "User-Agent": "MyID/1.0.300 (Android)"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # allow_redirects=False က အရေးကြီးပါတယ်။ 302 ကို ဖမ်းဖို့ပါ။
            async with session.get(url, headers=headers, allow_redirects=False, timeout=15) as res:
                if res.status in [301, 302, 307]:
                    redirect_url = res.headers.get('Location')
                    if redirect_url:
                        parsed_url = urllib.parse.urlparse(redirect_url)
                        query_params = urllib.parse.parse_qs(parsed_url.query)
                        return query_params.get('token', [None])[0]
    except Exception as e:
        print(f"Error getting game token: {e}")
        
    return None

async def game_start(game_token):
    url = f"{GAME_BASE_URL}/game/start"
    headers = {"Authorization": f"Bearer {game_token}", "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as res:
                return await res.json()
    except Exception as e:
        return {"error": str(e)}

async def game_reward(game_token, slot_index):
    url = f"{GAME_BASE_URL}/game/reward?slot_index={slot_index}"
    headers = {"Authorization": f"Bearer {game_token}", "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as res:
                return await res.json()
    except Exception as e:
        return {"error": str(e)}

async def game_stop(game_token):
    url = f"{GAME_BASE_URL}/game/stop"
    headers = {"Authorization": f"Bearer {game_token}", "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as res:
                return await res.json()
    except Exception as e:
        return {"error": str(e)}

async def get_reward_history(game_token):
    url = f"{GAME_BASE_URL}/game/reward/history?limit=5"
    headers = {"Authorization": f"Bearer {game_token}", "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as res:
                return await res.json()
    except Exception as e:
        return {"error": str(e)}