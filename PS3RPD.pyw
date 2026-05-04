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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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

print("--- PS3RPD Initializing ---")

config_path = Path("ps3rpdconfig.json")
cache_path = Path("ps3rpd_cache.json")

default_config = {
    "ip": "",
    "client_id": 780389261870235650,
    "wait_seconds": 45,
    "show_temp": False,
    "show_xmb": False,
    "safe_webman_mode": True,
    "probe_legacy_webman_on_xmb": False,
    "hibernate_seconds": 10,
    "steamgriddb_api_key": "",
    "prefer_square_covers": True,
    "manual_sgdb_map": {},
    "manual_grid_map": {},
    "boot_cooldown_seconds": 90,
    "boot_retry_cooldown_seconds": 30,
    "game_change_cooldown_seconds": 90,
        "xmb_poll_seconds": 30,
        # error-based pause
        "poll_error_threshold": 3,
        "poll_error_pause_seconds": 180,
        # Polling/backoff safety options
        "safe_poll": True,
        "poll_backoff_threshold_ms": 300,
        "poll_backoff_multiplier": 2.0,
        "poll_backoff_max_seconds": 300,
        "low_impact_when_disconnected": True,
        "low_impact_multiplier": 4.0,
        "game_poll_multiplier": 2.5,
        "game_poll_max_seconds": 300,
        "discovery_workers": 12,
        "discovery_window": 12
}

default_cache = {
    "games": {}
}

headers = {
    "User-Agent": "Mozilla/5.0"
}

class PS3Manager:
    def __init__(self):
        self.config = default_config.copy()
        self.cache = default_cache.copy()
        self.rpc = None
        self.cover_cache = {}
        self.last_game_key = None
        self.last_search_name = None
        self.cooldown_until = 0
        self.boot_mode = False
        # Backoff state
        self.poll_backoff_counter = 0
        self.last_request_latency_ms = None
        # HTTP session & error state
        self.session = requests.Session()
        # mount retry adapter
        retries = Retry(total=2, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(headers)
        self.consecutive_errors = 0
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
            r = self.safe_get("https://www.steamgriddb.com/api/v2/search/autocomplete/God%20of%20War", headers=sgdb_headers, timeout=5)
            if not r:
                print(f"[SteamGridDB] Sin respuesta al probar la API")
                return False
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
        possible_ips = []
        if saved_ip and saved_ip.startswith(base_ip):
            try:
                saved_octet = int(saved_ip.split(".")[-1])
                window = int(self.config.get("discovery_window", 12) or 12)
                start_octet = max(1, saved_octet - window)
                end_octet = min(254, saved_octet + window)
                possible_ips.extend([f"{base_ip}{i}" for i in range(start_octet, end_octet + 1)])
            except Exception:
                pass
        possible_ips.extend([f"{base_ip}{i}" for i in range(1, 255) if f"{base_ip}{i}" not in possible_ips])
        workers = int(self.config.get("discovery_workers", 12) or 12)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
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
            r = self.safe_get(f"http://{ip}", timeout=timeout)
            if r and r.status_code == 200:
                return "wMAN" in r.text or "webMAN" in r.text
        except:
            pass
        return False

    def safe_get(self, url, timeout=5, headers=None, allow_redirects=True):
        try:
            start = time()
            r = self.session.get(url, headers=headers, timeout=timeout, allow_redirects=allow_redirects)
            latency_ms = int((time() - start) * 1000)
            self.last_request_latency_ms = latency_ms
            # reset consecutive error count on success
            self.consecutive_errors = 0
            return r
        except requests.RequestException as e:
            self.consecutive_errors += 1
            print(f"[HTTP] request error ({self.consecutive_errors}): {e}")
            thresh = int(self.config.get("poll_error_threshold", 3) or 3)
            pause = int(self.config.get("poll_error_pause_seconds", 180) or 180)
            if self.consecutive_errors >= thresh:
                print(f"[HTTP] demasiados errores consecutivos; pausando polling por {pause}s")
                try:
                    self.cooldown_until = time() + pause
                except:
                    pass
                self.consecutive_errors = 0
            return None

    def safe_head(self, url, timeout=2, headers=None, allow_redirects=True):
        try:
            start = time()
            r = self.session.head(url, headers=headers, timeout=timeout, allow_redirects=allow_redirects)
            latency_ms = int((time() - start) * 1000)
            self.last_request_latency_ms = latency_ms
            self.consecutive_errors = 0
            return r
        except requests.RequestException as e:
            self.consecutive_errors += 1
            print(f"[HTTP] head error ({self.consecutive_errors}): {e}")
            thresh = int(self.config.get("poll_error_threshold", 3) or 3)
            pause = int(self.config.get("poll_error_pause_seconds", 180) or 180)
            if self.consecutive_errors >= thresh:
                print(f"[HTTP] demasiados errores consecutivos (HEAD); pausando polling por {pause}s")
                try:
                    self.cooldown_until = time() + pause
                except:
                    pass
                self.consecutive_errors = 0
            return None

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
        # By default, only clear presence to avoid repeatedly closing underlying async transports
        # which can trigger ProactorBasePipeTransport warnings on Windows. Use force=True to fully close.
        def _do_close():
            try:
                self.rpc.clear()
            except:
                pass
            try:
                self.rpc.close()
            except:
                pass
            self.rpc = None

        # If caller passed a force flag via attribute set temporarily, respect it.
        # (We avoid changing many call sites — callers can set `self._force_close_rpc = True` before calling.)
        if getattr(self, '_force_close_rpc', False):
            try:
                delattr(self, '_force_close_rpc')
            except:
                pass
            _do_close()
            return

        # Default: only clear presence state, keep transport/connection open to avoid Windows Proactor issues.
        if self.rpc:
            try:
                self.rpc.clear()
            except:
                pass

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
                r = self.safe_get(f"https://www.steamgriddb.com/api/v2/search/autocomplete/{encoded_q}", headers=sgdb_headers, timeout=5)
                if r and r.status_code == 200:
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
                    # use safe_get to avoid hammering the API/PS3
                    url = f"https://www.steamgriddb.com/api/v2/grids/game/{sgdb_game_id}"
                    r = self.safe_get(url + f"?page={page}&limit=50&dimensions={dim}", headers=sgdb_headers, timeout=5)
                    status = r.status_code if r else 'ERR'
                    print(f"[COVER] grids/game/{sgdb_game_id} dim={dim} page={page} HTTP: {status}")

                    if not r or r.status_code != 200:
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
            print(f"[COVER] Grid cuadrado elegido: id={chosen.get('id')} width={chosen.get('width')} height={chosen.get('height')} url={chosen.get('url')}")
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
            r = self.safe_get(f"https://www.steamgriddb.com/api/v2/icons/game/{sgdb_game_id}", headers=sgdb_headers, timeout=5)
            if r and r.status_code == 200:
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

        cached_entry = self.get_cache_entry(game_name) if game_name else {}
        cached_url = cached_entry.get("selected_url")
        cached_source = cached_entry.get("source")
        if cached_url:
            if game_name:
                self.cache_game_result(game_name, selected_url=cached_url, source=cached_source or "cache")
            self.cover_cache[cache_key] = cached_url
            return cached_url

        fallback_square_url = "https://cdn2.steamgriddb.com/grid/636ff76014a7300ea3c2b260a2edd559.webp"
        try:
            check = self.safe_head(fallback_square_url, timeout=2.5, allow_redirects=True)
            if check and check.status_code == 200:
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
                check = self.safe_head(url, timeout=2.5, allow_redirects=True)
                if check and check.status_code == 200:
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
                image = "ps3"
                title = "Menú Principal"
                details = "XMB"
                search_name = None
                is_xmb = False
                game_id = None
                sgdb_game_id = None

                def _is_probable_title_id(tid):
                    tid = (tid or "").strip().upper()
                    if not re.fullmatch(r"[A-Z]{4}\d{5}", tid):
                        return False
                    # Known/common PS3 title-id families (reduces false positives from system pages)
                    valid_prefix2 = {"BL", "BC", "NP", "KT", "UL", "SL", "SC", "LA", "MO", "MR"}
                    return tid[:2] in valid_prefix2

                def assign_cover(search, tid):
                    cached_entry = self.get_cache_entry(search or "")
                    cached_url = cached_entry.get("selected_url")
                    cached_source = cached_entry.get("source")
                    can_upgrade_fallback = bool(
                        cached_url and cached_source == "fallback" and str(self.config.get("steamgriddb_api_key", "")).strip()
                    )
                    if cached_url and not can_upgrade_fallback:
                        return cached_url, cached_entry.get("sgdb_game_id")
                    sg = cached_entry.get("sgdb_game_id") or (self.search_sgdb_game_id(search) if search else None)
                    return self.resolve_cover(tid, game_name=search, sgdb_game_id=sg), sg

                # Strategy 0: explicit H2 block with TitleID + game title anchor (webMAN setup/home pages)
                for h2 in current_soup.find_all("h2"):
                    anchors = h2.find_all("a", href=True)
                    if not anchors:
                        continue

                    tid = None
                    name = None

                    for a in anchors:
                        txt = a.get_text(" ", strip=True)
                        mtid = re.search(r"([A-Z]{4}\d{5})", txt)
                        if mtid:
                            tid = mtid.group(1)
                            break

                    if not tid:
                        h2_text = h2.get_text(" ", strip=True)
                        mtid = re.search(r"([A-Z]{4}\d{5})", h2_text)
                        if mtid:
                            tid = mtid.group(1)

                    if not tid:
                        continue

                    for a in anchors:
                        href = (a.get("href") or "").lower()
                        txt = a.get_text(" ", strip=True)
                        if not txt:
                            continue
                        if re.search(r"([A-Z]{4}\d{5})", txt):
                            continue
                        if "pid=" in txt.lower() or "pid=" in href:
                            continue
                        if txt in ("▲", "▼"):
                            continue
                        if "google.com/search" in href:
                            name = txt
                            break

                    if not name:
                        for a in anchors:
                            txt = a.get_text(" ", strip=True)
                            href = (a.get("href") or "").lower()
                            if not txt:
                                continue
                            if re.search(r"([A-Z]{4}\d{5})", txt):
                                continue
                            if "pid=" in txt.lower() or "pid=" in href:
                                continue
                            if txt in ("▲", "▼"):
                                continue
                            if txt.lower().startswith("http"):
                                continue
                            name = txt
                            break

                    if name:
                        game_id = tid
                        details = self.extract_text_clean(name)
                        search_name = details
                        title = "Jugando"
                        image, sgdb_game_id = assign_cover(search_name, game_id)
                        return {
                            "image": image,
                            "title": title,
                            "details": details,
                            "search_name": search_name,
                            "is_xmb": is_xmb,
                            "game_id": game_id,
                            "sgdb_game_id": sgdb_game_id
                        }

                # Strategy 1: explicit target="_blank" anchor (legacy/typical)
                tag = current_soup.find("a", target="_blank")
                if tag:
                    # try get title id from anchor text or href
                    text_candidate = tag.get_text(" ", strip=True) or str(tag)
                    m = re.search(r"([A-Z]{4}\d{5})", text_candidate) or re.search(r"([A-Z]{4}\d{5})", str(tag.get('href', '')))
                    game_id = m.group(1) if m else ""
                    parent = tag.find_parent(['h2', 'H2']) or tag.parent
                    full_name = None
                    if parent:
                        anchors = parent.find_all('a')
                        # prefer the anchor after the title-id anchor
                        for a in anchors:
                            if a is tag:
                                continue
                            txt = a.get_text(' ', strip=True)
                            if txt:
                                full_name = txt
                                break
                        if not full_name:
                            full_name = parent.get_text(' ', strip=True)
                    if not full_name:
                        ns = tag.find_next_sibling()
                        raw_name = str(ns) if ns else ''
                        fm = re.search(r">(.*)<", raw_name)
                        full_name = fm.group(1) if fm else None

                    if full_name and game_id and _is_probable_title_id(game_id):
                        details = self.extract_text_clean(full_name)
                        search_name = details
                        title = "Jugando"
                        image, sgdb_game_id = assign_cover(search_name, game_id)
                        return {
                            "image": image,
                            "title": title,
                            "details": details,
                            "search_name": search_name,
                            "is_xmb": is_xmb,
                            "game_id": game_id,
                            "sgdb_game_id": sgdb_game_id
                        }

                # Strategy 2: scan <h2> tags for TitleID + name
                for h in current_soup.find_all(['h2', 'H3']):
                    h_text = h.get_text(' ', strip=True)
                    m = re.search(r"([A-Z]{4}\d{5})", h_text)
                    if m:
                        candidate_tid = m.group(1)
                        if _is_probable_title_id(candidate_tid):
                            game_id = candidate_tid
                        else:
                            continue
                        anchors = h.find_all('a')
                        name = None
                        for a in anchors:
                            t = a.get_text(' ', strip=True)
                            if t and not re.search(r"[Hh][Tt][Tt][Pp]", t):
                                # prefer non-url text
                                name = t
                                break
                        if not name:
                            name = re.sub(r"[\[\]\n]+", ' ', h_text).strip()
                        details = self.extract_text_clean(name)
                        search_name = details
                        title = "Jugando"
                        image, sgdb_game_id = assign_cover(search_name, game_id)
                        return {
                            "image": image,
                            "title": title,
                            "details": details,
                            "search_name": search_name,
                            "is_xmb": is_xmb,
                            "game_id": game_id,
                            "sgdb_game_id": sgdb_game_id
                        }

                # Strategy 3: anchors pointing to known assets or google search
                for a in current_soup.find_all('a', href=True):
                    h = a.get('href', '')
                    if 'a0.ww.np.dl.playstation.net' in h or 'google.com/search' in h or '/dev_bdvd' in h:
                        # try to find title id in nearby context
                        container = a.find_parent(['h2', 'div', 'span']) or a.parent
                        text_block = container.get_text(' ', strip=True) if container else a.get_text(' ', strip=True)
                        m = re.search(r"([A-Z]{4}\d{5})", text_block)
                        if m:
                            game_id = m.group(1)
                        # prefer adjacent anchor with name
                        name = None
                        if container:
                            anchors = container.find_all('a')
                            for aa in anchors:
                                t = aa.get_text(' ', strip=True)
                                if t and aa is not a and not re.search(r"[Hh][Tt][Tt][Pp]", t):
                                    name = t
                                    break
                        if not name:
                            name = re.sub(r"[\[\]\n]+", ' ', text_block).strip()
                        if name and game_id and _is_probable_title_id(game_id) and len(name.strip()) >= 2 and name.strip() not in ("▲", "▼"):
                            details = self.extract_text_clean(name)
                            search_name = details
                            title = 'Jugando'
                            image, sgdb_game_id = assign_cover(search_name, game_id)
                            return {
                                "image": image,
                                "title": title,
                                "details": details,
                                "search_name": search_name,
                                "is_xmb": is_xmb,
                                "game_id": game_id,
                                "sgdb_game_id": sgdb_game_id
                            }

                # Strategy 4: retro detection
                retro_tag = current_soup.find('a', href=re.compile(r"/(dev_hdd0|dev_usb00[0-9])/(PSXISO|PS2ISO)"))
                if retro_tag:
                    try:
                        details = re.search(r'">(.*)</a>', str(retro_tag.find_next_sibling())).group(1)
                        details = self.extract_text_clean(details)
                    except:
                        details = "Juego Retro"
                    title = "Clásico"
                    image = "retro"
                    return {
                        "image": image,
                        "title": title,
                        "details": details,
                        "search_name": search_name,
                        "is_xmb": False,
                        "game_id": game_id,
                        "sgdb_game_id": sgdb_game_id
                    }

                # nothing matched => XMB
                is_xmb = True
                return {
                    "image": image,
                    "title": title,
                    "details": details,
                    "search_name": search_name,
                    "is_xmb": is_xmb,
                    "game_id": game_id,
                    "sgdb_game_id": sgdb_game_id
                }

            safe_webman_mode = bool(self.config.get("safe_webman_mode", True))
            game_status_url = f"http://{ip}/sman.ps3" if safe_webman_mode else f"http://{ip}/cpursx.ps3?/sman.ps3"

            r = self.safe_get(game_status_url, timeout=5)
            if not r or r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "html.parser")

            state_text = None
            if self.config.get("show_temp", False):
                try:
                    if safe_webman_mode:
                        temp_r = self.safe_get(f"http://{ip}/cpursx.ps3", timeout=3)
                        if not temp_r or temp_r.status_code != 200:
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

            if safe_webman_mode and parsed["is_xmb"] and self.config.get("probe_legacy_webman_on_xmb", False):
                try:
                    legacy_r = self.safe_get(f"http://{ip}/cpursx.ps3?/sman.ps3", timeout=5)
                    if legacy_r and legacy_r.status_code == 200:
                        legacy_soup = BeautifulSoup(legacy_r.text, "html.parser")
                        legacy_parsed = parse_status_from_soup(legacy_soup)
                        if not legacy_parsed["is_xmb"]:
                            parsed = legacy_parsed
                except:
                    pass

            # additional fallback: some webMAN variants expose info under /home.ps3mapi/sman.ps3
            if parsed["is_xmb"]:
                try:
                    home_r = self.safe_get(f"http://{ip}/home.ps3mapi/sman.ps3", timeout=4)
                    if home_r and home_r.status_code == 200:
                        home_soup = BeautifulSoup(home_r.text, "html.parser")
                        home_parsed = parse_status_from_soup(home_soup)
                        if not home_parsed.get("is_xmb", True):
                            parsed = home_parsed
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
    try:
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
            app.last_search_name = None
            app.cooldown_until = 0
            app.boot_mode = False

            while True:
                now = time()
                app.load_config()
                app.load_cache()

                if now < app.cooldown_until:
                    sleep(2)
                    continue

                # Measure request latency to drive adaptive backoff
                req_start = time()
                data = app.get_game_status(current_ip)
                req_latency_ms = int((time() - req_start) * 1000)
                app.last_request_latency_ms = req_latency_ms
                # Backoff decision
                threshold_ms = int(app.config.get("poll_backoff_threshold_ms", 300) or 300)
                multiplier = float(app.config.get("poll_backoff_multiplier", 2.0) or 2.0)
                max_backoff = int(app.config.get("poll_backoff_max_seconds", 300) or 300)
                low_impact_when_disconnected = bool(app.config.get("low_impact_when_disconnected", True))
                low_impact_multiplier = float(app.config.get("low_impact_multiplier", 4.0) or 4.0)

                if req_latency_ms and req_latency_ms >= threshold_ms:
                    app.poll_backoff_counter = min(app.poll_backoff_counter + 1, 8)
                    print(f"[Polling] alta latencia {req_latency_ms}ms -> backoff nivel {app.poll_backoff_counter}")
                else:
                    if app.poll_backoff_counter:
                        print(f"[Polling] latencia normal, reset backoff (was {app.poll_backoff_counter})")
                    app.poll_backoff_counter = 0

                base_wait = int(app.config.get("wait_seconds", 45) or 45)
                effective_wait = base_wait * (multiplier ** app.poll_backoff_counter)
                if effective_wait > max_backoff:
                    effective_wait = max_backoff
                # If Discord client disconnected and low-impact mode enabled, poll even less frequently
                if low_impact_when_disconnected and not app.rpc:
                    effective_wait = min(max_backoff, int(effective_wait * low_impact_multiplier))

                safe_poll_enabled = bool(app.config.get("safe_poll", True))
                game_poll_multiplier = float(app.config.get("game_poll_multiplier", 2.5) or 2.5)
                game_poll_max_seconds = int(app.config.get("game_poll_max_seconds", 300) or 300)

                if not data:
                    strikes += 1
                    if strikes >= 3:
                        print("PS3 Apagada o sin respuesta.")
                        app.disconnect_discord()
                        app.last_game_key = None
                        app.last_search_name = None
                        break
                    app.cooldown_until = time() + app.config.get("boot_retry_cooldown_seconds", 30)
                    sleep(5)
                    continue

                strikes = 0

                if data["is_xmb"] and not app.config.get("show_xmb", False):
                    if app.rpc:
                        print("En XMB (ocultando)...")
                        app.disconnect_discord()
                        app.last_game_key = None
                        app.last_search_name = None
                    xmb_poll_seconds = int(app.config.get("xmb_poll_seconds", 30) or 30)
                    for _ in range(max(1, xmb_poll_seconds // 5)):
                        sleep(5)
                    continue

                # sanitize details to avoid glyph-only results like '▲'
                details = data.get("details") or ""
                search_name = data.get("search_name")
                title = data.get("large_text") or ""

                def _is_valid_presence_text(v):
                    v = (v or "").strip()
                    if len(v) < 2:
                        return False
                    if v in ("▲", "▼"):
                        return False
                    if re.match(r"^[^A-Za-z0-9]+$", v):
                        return False
                    return True

                def _sanitize_details(d, search, tit):
                    d = (d or "").strip()
                    search = (search or "").strip()
                    tit = (tit or "").strip()

                    if _is_valid_presence_text(d):
                        return d
                    if _is_valid_presence_text(search):
                        return search
                    if _is_valid_presence_text(tit):
                        return tit
                    return "Juego PS3"

                details = _sanitize_details(details, search_name, data.get("title") or "Juego PS3")
                data["details"] = details

                # Safety net: if it doesn't look like a real PS3 title id, treat it as XMB and hide when configured.
                if not data["is_xmb"]:
                    m = re.search(r"([A-Z]{4}\d{5})", data.get("game_key", ""))
                    tid = m.group(1) if m else ""
                    if not _is_valid_presence_text(details) or not re.fullmatch(r"[A-Z]{4}\d{5}", tid):
                        data["is_xmb"] = True

                if data["game_key"] != app.last_game_key and not data["is_xmb"]:
                    print(f"Cambio de juego detectado: {data['details'][:60]}")
                    app.last_game_key = data["game_key"]
                    app.last_search_name = data["search_name"]
                    start_time = time()
                    app.cooldown_until = time() + app.config.get("boot_cooldown_seconds", 90)

                if safe_poll_enabled and not data["is_xmb"]:
                    game_wait = min(game_poll_max_seconds, int(base_wait * game_poll_multiplier))
                    if game_wait > effective_wait:
                        effective_wait = game_wait

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
                        start=start_time,
                        status_display_type=2
                    )
                except Exception as e:
                    print(f"[RPC] update error: {e}")
                    app.disconnect_discord()
                    break

                try:
                    sleep(int(effective_wait))
                except Exception:
                    sleep(int(app.config.get("wait_seconds", 45) or 45))

            sleep(5)
    except KeyboardInterrupt:
        print("Saliendo por interrupción de usuario...")
    except Exception as e:
        print(f"Error inesperado: {e}")
    finally:
        try:
            # force full close at exit to clean transports
            app._force_close_rpc = True
            app.disconnect_discord()
        except:
            pass
        try:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.stop()
                loop.close()
            except Exception:
                pass
        except Exception:
            pass