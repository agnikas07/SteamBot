import requests
import os
import time


STEAM_API_KEY = os.getenv('STEAM_API_KEY')
STEAM_API_BASE_URL = "https://api.steampowered.com/"

LAST_STORE_API_CALL_TIME = 0
STORE_API_COOLDOWN = 0.25


def _wait_for_store_api_cooldown():
    global LAST_STORE_API_CALL_TIME
    time_since_last_call = time.time() - LAST_STORE_API_CALL_TIME
    if time_since_last_call < STORE_API_COOLDOWN:
        time.sleep(STORE_API_COOLDOWN - time_since_last_call)
    LAST_STORE_API_CALL_TIME = time.time()


def get_owned_games(steam_id):
    """
    Fetches the list of games owned by a given SteamID.
    Requires the Steam profile to be public.
    Returns a dictionary with game app IDs and names, or None on error/ private profile.
    """
    if not STEAM_API_KEY:
        print("Steam API key is not set.")
        return None
    
    url = f"{STEAM_API_BASE_URL}IPlayerService/GetOwnedGames/v1/"
    params = {
        'key': STEAM_API_KEY,
        'steamid': steam_id,
        'include_appinfo': 1,
        'format': 'json'
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if data and "response" in data and "games" in data["response"]:
            games_list = data["response"]["games"]
            owned_games = {game["appid"]: game["name"] for game in games_list}
            return owned_games
        else:
            print(f"Steam API: No games found or private profile for SteamID {steam_id}.")
            return {}
    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 401:
            print(f"Steam API Error for {steam_id}: Unauthorized. Check your API key.")
        elif response.status_code == 403:
            print(f"Steam API Error for {steam_id}: Forbidden. Profile might be private or API key restricted.")
        else:
            print(f"Steam API HTTP error for {steam_id}: {http_err}")
        return None
    except requests.exceptions.RequestException as req_err:
        print(f"Steam API Request error for {steam_id}: {req_err}")
        return None
    except ValueError as json_err:
        print(f"Steam API JSON decoding error for {steam_id}: {json_err}. Response: {response.text[:200]}...")
        return None
    

def get_game_details(appid):
    """
    Fetches basic details for a specific game from the Steam Store API.
    Used to get game names if only appids are aviailable or for more info.
    """
    _wait_for_store_api_cooldown()

    url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data and str(appid) in data and data[str(appid)]["success"]:
            return data[str(appid)]["data"]
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching game details for AppID {appid}: {e}")
        return None
    except ValueError as e:
        print(f"JSON decoding error for AppID {appid}: {e}")
        return None
    

def is_game_multiplayer(appid):
    """
    Checks if a game is categorized as multiplayer, co-op, or MMO.
    """
    details = get_game_details(appid)
    if not details:
        return False
    
    if "categories" in details:
        for category in details["categories"]:
            desc = category.get("description", "").lower()
            if "multiplayer" in desc or "multi-player" in desc or "co-op" in desc or "mmo" in desc:
                return True
    return False