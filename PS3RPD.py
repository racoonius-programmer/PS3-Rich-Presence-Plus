# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "bs4",
#     "requests",
#     "pypresence",
# ]
# ///
import sys
import os
from pathlib import Path
from socket import socket, AF_INET, SOCK_DGRAM
import json
import re
from urllib.parse import quote
from time import sleep, time
import concurrent.futures
from bs4 import BeautifulSoup
import requests
from pypresence import Presence

try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except:
    pass

class SafeLogger(object):
    def __init__(self):
        self.file = open("debug_log.txt", "w", buffering=1, encoding="utf-8", errors="ignore")
        self.console = sys.stdout if sys.stdout is not None else None
    def write(self, message):
        try:
            self.file.write(message)
            self.file.flush()
        except:
            pass
        if self.console:
            try:
                self.console.write(message)
                self.console.flush()
            except:
                pass
    def flush(self):
        try:
            self.file.flush()
        except:
            pass

sys.stdout = SafeLogger()
sys.stderr = sys.stdout

print("--- PS3RPD: VERSIÓN HOT-RELOAD ---")

config_path = Path("ps3rpdconfig.json")
cache_path = Path("ps3rpd_cache.json")

default_config = {
    "ip": "",
    "client_id": 780389261870235650,
    "wait_seconds": 45,
    "show_temp": False,
    "show_xmb": False,
    "safe_webman_mode": True,
    "hibernate_seconds": 10,
    "steamgriddb_api_key": "",
    "prefer_square_covers": True,
    "manual_sgdb_map": {},
    "manual_grid_map": {}
}

default_cache = {
    "games": {}
}

headers = {
    "User-Agent": "Mozilla/5.0",
    "Connection": "close"
}

class PS3Manager:
    def __init__(self):
        self.config = default_config.copy()
        self.cache = default_cache.copy()
        self.rpc = None
        self.cover_cache = {}
        self.last_game_key = None
        self.load_config()
        self.load_cache()

    def load_config(self):
        if config_path.is_file():
            try:
                with config_path.open("r", encoding="utf-8") as f:
                    loaded_config = json.load(f)
                config_changed = False
                for key, val in default_config.items():
                    if key not in loaded_config:
                        loaded_config[key] = val
                        config_changed = True
                if not isinstance(loaded_config.get("manual_sgdb_map"), dict):
                    loaded_config["manual_sgdb_map"] = {}
                    config_changed = True
                if not isinstance(loaded_config.get("manual_grid_map"), dict):
                    loaded_config["manual_grid_map"] = {}
                    config_changed = True
                self.config = loaded_config
                if config_changed:
                    self.save_config()
                    print("Configuración actualizada con nuevas opciones.")
            except Exception:
                self.config = default_config.copy()
        else:
            self.config = default_config.copy()
            self.save_config()

    def save_config(self):
        try:
            with config_path.open("w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except:
            pass

    def load_cache(self):
        if cache_path.is_file():
            try:
                with cache_path.open("r", encoding="utf-8") as f:
                    loaded_cache = json.load(f)
                if isinstance(loaded_cache, dict) and isinstance(loaded_cache.get("games"), dict):
                    self.cache = loaded_cache
                    return
            except:
                pass
        self.cache = default_cache.copy()
        self.save_cache()

    def save_cache(self):
        try:
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=4, ensure_ascii=False)
        except:
            pass

    def normalize_game_name(self, name):
        name = (name or "").lower().strip()
        name = re.sub(r"\(.*?\)", "", name)
        name = re.sub(r"\s+", " ", name)
        return name.strip()

    def cache_game_result(self, game_name, sgdb_game_id=None, selected_url=None, source=None):
        if not game_name:
            return
        key = self.normalize_game_name(game_name)
        self.cache.setdefault("games", {})
        entry = self.cache["games"].get(key, {})
        if sgdb_game_id is not None:
            entry["sgdb_game_id"] = sgdb_game_id
        if selected_url is not None:
            entry["selected_url"] = selected_url
        if source is not None:
            entry["source"] = source
        self.cache["games"][key] = entry
        self.save_cache()

    def get_cache_entry(self, game_name):
        if not game_name:
            return {}
        return self.cache.get("games", {}).get(self.normalize_game_name(game_name), {}) or {}

    def extract_text_clean(self, text):
        text = re.sub(r"\s+", " ", text or "").strip()
        text = re.sub(r"\[.*?\]", "", text)
        text = re.sub(r"\s+v?\d{2}\.\d{2}$", "", text)
        text = re.sub(r"\s+\d\.\d{2}$", "", text)
        return text.strip()

    def get_manual_sgdb_override(self, game_name):
        manual = self.config.get("manual_sgdb_map", {})
        if not isinstance(manual, dict):
            return {}
        target = self.normalize_game_name(game_name)
        for key, entry in manual.items():
            if self.normalize_game_name(key) == target and isinstance(entry, dict):
                return entry
        return {}

    def get_manual_grid_override(self, game_name):
        manual = self.config.get("manual_grid_map", {})
        if not isinstance(manual, dict):
            return None
        target = self.normalize_game_name(game_name)
        for key, entry in manual.items():
            if self.normalize_game_name(key) != target or not isinstance(entry, dict):
                continue
            if entry.get("grid_url"):
                return entry["grid_url"]
            if entry.get("grid_id"):
                return f"https://cdn2.steamgriddb.com/grid/{entry['grid_id']}"
        return None

    def test_steamgriddb_key(self):
        api_key = str(self.config.get("steamgriddb_api_key", "")).strip()
        if not api_key:
            print("[SteamGridDB] No hay API key en la config.")
            return False
        print(f"[SteamGridDB] API key cargada: {api_key[:6]}...{api_key[-4:]}")
        sgdb_headers = {"User-Agent": "PS3RPD/1.0", "Authorization": f"Bearer {api_key}"}
        try:
            r = requests.get("https://www.steamgriddb.com/api/v2/search/autocomplete/God%20of%20War", headers=sgdb_headers, timeout=5)
            print(f"[SteamGridDB] Status HTTP: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"[SteamGridDB] OK. Resultados recibidos: {len(data.get('data', []))}")
                return True
            print(f"[SteamGridDB] Respuesta: {r.text[:200]}")
            return False
        except Exception as e:
            print(f"[SteamGridDB] Error al probar la API: {e}")
            return False

    def find_ps3(self):
        self.load_config()
        saved_ip = self.config.get("ip")
        if saved_ip and self.check_webman(saved_ip, timeout=3):
            return saved_ip
        print("Buscando PS3...")
        base_ip = self.get_local_network_base()
        if not base_ip:
            return None
        found_ip = None
        possible_ips = [f"{base_ip}{i}" for i in range(1, 255)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            future_to_ip = {executor.submit(self.check_webman, ip, 1): ip for ip in possible_ips}
            for future in concurrent.futures.as_completed(future_to_ip):
                ip = future_to_ip[future]
                try:
                    if future.result():
                        found_ip = ip
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                except:
                    pass
        if found_ip:
            self.config["ip"] = found_ip
            self.save_config()
            return found_ip
        return None

    def get_local_network_base(self):
        try:
            s = socket(AF_INET, SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            m = re.search(r"^(.*\.)", local_ip)
            return m.group(1) if m else None
        except:
            return None

    def check_webman(self, ip, timeout=2):
        if not ip:
            return False
        try:
            r = requests.get(f"http://{ip}", headers=headers, timeout=timeout)
            if r.status_code == 200:
                return "wMAN" in r.text or "webMAN" in r.text
        except:
            pass
        return False

    def connect_discord(self):
        if self.rpc:
            return True
        try:
            self.rpc = Presence(self.config["client_id"])
            self.rpc.connect()
            return True
        except:
            self.rpc = None
            return False

    def disconnect_discord(self):
        if self.rpc:
            try:
                self.rpc.clear()
            except:
                pass
            try:
                self.rpc.close()
            except:
                pass
            self.rpc = None

    def search_sgdb_game_id(self, game_name):
        api_key = str(self.config.get("steamgriddb_api_key", "")).strip()
        if not api_key or not game_name:
            return None

        cached = self.get_cache_entry(game_name).get("sgdb_game_id")
        if cached:
            return cached

        manual = self.get_manual_sgdb_override(game_name)
        if manual.get("game_id"):
            self.cache_game_result(game_name, sgdb_game_id=manual["game_id"], source="manual_sgdb_map")
            return manual["game_id"]

        sgdb_headers = {"User-Agent": "PS3RPD/1.0", "Authorization": f"Bearer {api_key}"}
        queries = [game_name]
        alt = re.sub(r"\s*\(.*?\)\s*", " ", game_name).strip()
        if alt and alt != game_name:
            queries.append(alt)

        for q in queries:
            try:
                encoded_q = quote(q, safe="")
                r = requests.get(f"https://www.steamgriddb.com/api/v2/search/autocomplete/{encoded_q}", headers=sgdb_headers, timeout=5)
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    if data:
                        game_id = data[0].get("id")
                        self.cache_game_result(game_name, sgdb_game_id=game_id, source="search_autocomplete")
                        return game_id
            except Exception:
                pass
        return None

    def get_best_square_grid(self, sgdb_game_id, game_name=None):
        api_key = str(self.config.get("steamgriddb_api_key", "")).strip()
        if not api_key or not sgdb_game_id:
            return None

        sgdb_headers = {
            "User-Agent": "PS3RPD/1.0",
            "Authorization": f"Bearer {api_key}"
        }

        candidates = []

        try:
            for dim in ("512x512", "1024x1024"):
                for page in range(0, 10):
                    r = requests.get(
                        f"https://www.steamgriddb.com/api/v2/grids/game/{sgdb_game_id}",
                        params={
                            "page": page,
                            "limit": 50,
                            "dimensions": dim
                        },
                        headers=sgdb_headers,
                        timeout=5
                    )
                    print(f"[COVER] grids/game/{sgdb_game_id} dim={dim} page={page} HTTP: {r.status_code}")

                    if r.status_code != 200:
                        break

                    payload = r.json()
                    data = payload.get("data", [])
                    if not data:
                        break

                    candidates.extend(data)

                    total = payload.get("total")
                    limit = payload.get("limit", 50)
                    if total is not None and (page + 1) * limit >= total:
                        break

            if not candidates:
                print("[COVER] No se encontraron grids cuadrados")
                return None

            candidates = sorted(
                candidates,
                key=lambda g: (
                    0 if g.get("width") == 512 else 1,
                    -(g.get("upvotes") or 0),
                    g.get("id") or 0
                )
            )

            chosen = candidates[0]
            print(
                f"[COVER] Grid cuadrado elegido: "
                f"id={chosen.get('id')} width={chosen.get('width')} height={chosen.get('height')} url={chosen.get('url')}"
            )
            return chosen.get("url")

        except Exception as e:
            print(f"[COVER] Error paginando grids: {e}")
            return None

    def get_first_icon(self, sgdb_game_id, game_name=None):
        api_key = str(self.config.get("steamgriddb_api_key", "")).strip()
        if not api_key or not sgdb_game_id:
            return None
        sgdb_headers = {"User-Agent": "PS3RPD/1.0", "Authorization": f"Bearer {api_key}"}
        try:
            r = requests.get(f"https://www.steamgriddb.com/api/v2/icons/game/{sgdb_game_id}", headers=sgdb_headers, timeout=5)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    data = sorted(data, key=lambda x: (0 if x.get("width") == 512 and x.get("height") == 512 else 1, 0 if x.get("width") == x.get("height") else 1))
                    for item in data:
                        url = item.get("url")
                        if url:
                            if game_name:
                                self.cache_game_result(game_name, selected_url=url, source="icon")
                            return url
        except Exception:
            pass
        return None

    def resolve_cover(self, title_id, game_name=None, sgdb_game_id=None):
        cache_key = f"{title_id}|{game_name}|{sgdb_game_id}"
        if cache_key in self.cover_cache:
            return self.cover_cache[cache_key]

        if not title_id or len(title_id) < 4:
            return "ps3_icon"

        if game_name:
            manual_grid_url = self.get_manual_grid_override(game_name)
            if manual_grid_url:
                self.cover_cache[cache_key] = manual_grid_url
                self.cache_game_result(game_name, selected_url=manual_grid_url, source="manual_grid_map")
                return manual_grid_url

        api_key = str(self.config.get("steamgriddb_api_key", "")).strip()
        prefer_square = self.config.get("prefer_square_covers", True)
        urls_to_try = []

        if api_key:
            try:
                if not sgdb_game_id and game_name:
                    sgdb_game_id = self.search_sgdb_game_id(game_name)

                if sgdb_game_id and prefer_square:
                    square_url = self.get_best_square_grid(sgdb_game_id, game_name=game_name)
                    if square_url:
                        if game_name:
                            self.cache_game_result(game_name, selected_url=square_url, source="square_grid")
                        self.cover_cache[cache_key] = square_url
                        return square_url

                if sgdb_game_id:
                    icon_url = self.get_first_icon(sgdb_game_id, game_name=game_name)
                    if icon_url:
                        self.cover_cache[cache_key] = icon_url
                        return icon_url

            except Exception:
                pass

        fallback_square_url = "https://cdn2.steamgriddb.com/grid/636ff76014a7300ea3c2b260a2edd559.webp"
        try:
            check = requests.head(fallback_square_url, timeout=2.5, allow_redirects=True)
            if check.status_code == 200:
                self.cover_cache[cache_key] = fallback_square_url
                if game_name:
                    self.cache_game_result(game_name, selected_url=fallback_square_url, source="fallback_square")
                return fallback_square_url
        except:
            pass

        region_map = {'U': 'US', 'E': 'EN', 'J': 'JA', 'K': 'KO', 'A': 'EN'}
        region_code = region_map.get(title_id[2], 'EN')
        gametdb_url = f"https://art.gametdb.com/ps3/cover/{region_code}/{title_id}.jpg"
        aldos1 = f"https://raw.githubusercontent.com/aldostools/Resources/main/COV/{title_id}.JPG"
        aldos2 = f"https://raw.githubusercontent.com/aldostools/Resources/main/COV/{title_id}.jpg"
        urls_to_try.extend([gametdb_url, aldos1, aldos2])

        for url in urls_to_try:
            try:
                check = requests.head(url, timeout=2.5, allow_redirects=True)
                if check.status_code == 200:
                    self.cover_cache[cache_key] = url
                    if game_name:
                        self.cache_game_result(game_name, selected_url=url, source="fallback")
                    return url
            except:
                continue

        self.cover_cache[cache_key] = "ps3_icon"
        return "ps3_icon"

    def get_game_status(self, ip):
        try:
            self.load_config()
            self.load_cache()

            def parse_status_from_soup(current_soup):
                parsed_image = "ps3"
                parsed_title = "Menú Principal"
                parsed_details = "XMB"
                parsed_search_name = None
                parsed_is_xmb = False
                parsed_game_id = None
                parsed_sgdb_game_id = None

                if current_soup.find("a", target="_blank"):
                    tag = current_soup.find("a", target="_blank")
                    raw_id_tag = str(tag)
                    try:
                        parsed_game_id = re.search(r">(.*)<", raw_id_tag).group(1)
                    except:
                        parsed_game_id = ""

                    raw_name = str(tag.find_next_sibling()).replace("\\n", "")
                    try:
                        full_name = re.search(r">(.*)<", raw_name).group(1)
                        clean_name = self.extract_text_clean(full_name)
                        parsed_details = clean_name.strip() if clean_name.strip() else "Juego PS3"
                        parsed_search_name = parsed_details
                    except:
                        parsed_details = "Juego PS3"
                        parsed_search_name = parsed_details

                    parsed_title = "Jugando"
                    cached_entry = self.get_cache_entry(parsed_search_name)
                    cached_url = cached_entry.get("selected_url")
                    cached_source = cached_entry.get("source")
                    can_upgrade_fallback = bool(
                        cached_url and
                        cached_source == "fallback" and
                        str(self.config.get("steamgriddb_api_key", "")).strip()
                    )

                    if cached_url and not can_upgrade_fallback:
                        parsed_image = cached_entry["selected_url"]
                    else:
                        parsed_sgdb_game_id = cached_entry.get("sgdb_game_id") or self.search_sgdb_game_id(parsed_search_name)
                        parsed_image = self.resolve_cover(parsed_game_id, game_name=parsed_search_name, sgdb_game_id=parsed_sgdb_game_id)

                elif current_soup.find("a", href=re.compile(r"/(dev_hdd0|dev_usb00[0-9])/(PSXISO|PS2ISO)")):
                    tag = current_soup.find("a", href=re.compile(r"/(dev_hdd0|dev_usb00[0-9])/(PSXISO|PS2ISO)"))
                    try:
                        parsed_details = re.search(r'">(.*)</a>', str(tag.find_next_sibling())).group(1)
                        parsed_details = self.extract_text_clean(parsed_details)
                    except:
                        parsed_details = "Juego Retro"
                    parsed_title = "Clásico"
                    parsed_image = "retro"
                else:
                    parsed_is_xmb = True

                return {
                    "image": parsed_image,
                    "title": parsed_title,
                    "details": parsed_details,
                    "search_name": parsed_search_name,
                    "is_xmb": parsed_is_xmb,
                    "game_id": parsed_game_id,
                    "sgdb_game_id": parsed_sgdb_game_id
                }

            safe_webman_mode = bool(self.config.get("safe_webman_mode", True))
            game_status_url = f"http://{ip}/sman.ps3" if safe_webman_mode else f"http://{ip}/cpursx.ps3?/sman.ps3"

            r = requests.get(game_status_url, headers=headers, timeout=5)
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "html.parser")

            state_text = None
            if self.config.get("show_temp", False):
                try:
                    if safe_webman_mode:
                        temp_r = requests.get(f"http://{ip}/cpursx.ps3", headers=headers, timeout=3)
                        if temp_r.status_code != 200:
                            raise ValueError("cpursx.ps3 no disponible")
                        temp_soup = BeautifulSoup(temp_r.text, "html.parser")
                        temps = str(temp_soup.find("a", href="/cpursx.ps3?up"))
                    else:
                        temps = str(soup.find("a", href="/cpursx.ps3?up"))
                    cpu = re.search(r"CPU(.+?)C", temps).group(0)
                    rsx = re.search(r"RSX(.+?)C", temps).group(0)
                    state_text = f"{cpu} | {rsx}"
                except:
                    pass

            parsed = parse_status_from_soup(soup)

            if safe_webman_mode and parsed["is_xmb"]:
                try:
                    legacy_r = requests.get(f"http://{ip}/cpursx.ps3?/sman.ps3", headers=headers, timeout=5)
                    if legacy_r.status_code == 200:
                        legacy_soup = BeautifulSoup(legacy_r.text, "html.parser")
                        legacy_parsed = parse_status_from_soup(legacy_soup)
                        if not legacy_parsed["is_xmb"]:
                            parsed = legacy_parsed
                except:
                    pass

            image = parsed["image"]
            title = parsed["title"]
            details = parsed["details"]
            search_name = parsed["search_name"]
            is_xmb = parsed["is_xmb"]
            game_id = parsed["game_id"]
            sgdb_game_id = parsed["sgdb_game_id"]

            large_text_value = details if not is_xmb else title

            return {
                "details": details[:127],
                "search_name": search_name,
                "sgdb_game_id": sgdb_game_id,
                "state": state_text,
                "large_image": image,
                "large_text": large_text_value[:127],
                "is_xmb": is_xmb,
                "game_key": f"{title}:{game_id}:{details}"
            }
        except Exception:
            return None

if __name__ == "__main__":
    app = PS3Manager()
    app.test_steamgriddb_key()

    while True:
        current_ip = None
        while not current_ip:
            current_ip = app.find_ps3()
            if not current_ip:
                sleep(15)

        print(f"Monitor activo en {current_ip}")
        start_time = time()
        strikes = 0
        app.last_game_key = None

        while True:
            app.load_config()
            app.load_cache()
            data = app.get_game_status(current_ip)

            if not data:
                strikes += 1
                if strikes >= 3:
                    print("PS3 Apagada.")
                    app.disconnect_discord()
                    app.last_game_key = None
                    break
                sleep(20)
                continue

            strikes = 0

            if data["is_xmb"] and not app.config.get("show_xmb", False):
                if app.rpc:
                    print("En XMB (Ocultando)...")
                    app.disconnect_discord()
                    app.last_game_key = None
                sleep(app.config.get("wait_seconds", 45))
                continue

            if data["game_key"] != app.last_game_key and not data["is_xmb"]:
                app.last_game_key = data["game_key"]
                start_time = time()
                print(f"Cambio de juego detectado: {data['details'][:60]}")

            if not app.rpc:
                if not app.connect_discord():
                    sleep(15)
                    continue

            try:
                app.rpc.update(
                    details=data["details"],
                    state=data["state"],
                    large_image=data["large_image"],
                    large_text=data["large_text"],
                    start=start_time
                )
            except:
                app.disconnect_discord()
                break

            sleep(app.config.get("wait_seconds", 45))

        sleep(5)