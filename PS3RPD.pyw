import sys
import os
from pathlib import Path
from socket import socket, AF_INET, SOCK_DGRAM
import json
import re
from time import sleep, time
import concurrent.futures
from bs4 import BeautifulSoup
import requests
from requests.exceptions import ConnectionError, Timeout
from pypresence import Presence, DiscordNotFound

# Log
try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except: pass

class SafeLogger(object):
    def __init__(self):
        self.file = open("debug_log.txt", "w", buffering=1, encoding='utf-8', errors='ignore')
        self.console = sys.stdout if sys.stdout is not None else None
    def write(self, message):
        try: self.file.write(message); self.file.flush()
        except: pass
        if self.console:
            try: self.console.write(message); self.console.flush()
            except: pass
    def flush(self):
        try: self.file.flush()
        except: pass

sys.stdout = SafeLogger()
sys.stderr = sys.stdout


config_path = Path("ps3rpdconfig.txt")

# Config por defecto
default_config = {
    "ip": "",
    "client_id": 780389261870235650,
    "wait_seconds": 45,     
    "show_temp": False,
    "show_xmb": False,      
    "hibernate_seconds": 10,
}

headers = {
    "User-Agent": "Mozilla/5.0",
    "Connection": "close"
}

class PS3Manager:
    def __init__(self):
        self.config = default_config
        self.rpc = None
        self.cover_cache = {}
        self.load_config()

    def load_config(self):
        if config_path.is_file():
            try:
                with config_path.open("r") as f:
                    loaded_config = json.load(f)
                
                config_changed = False
                for key, val in default_config.items():
                    if key not in loaded_config:
                        loaded_config[key] = val
                        config_changed = True
                
                self.config = loaded_config
                
                if config_changed:
                    self.save_config()
                    print("Config updated.")
                    
            except Exception:
                pass
        else:
            self.config = default_config
            self.save_config()

    def save_config(self):
        try:
            with config_path.open("w+") as f:
                json.dump(self.config, f, indent=4)
        except: pass

    def find_ps3(self):
        self.load_config() 
        
        saved_ip = self.config.get("ip")
        if saved_ip:
            if self.check_webman(saved_ip, timeout=3):
                return saved_ip
        
        print("Searching for PS3...")
        base_ip = self.get_local_network_base()
        if not base_ip: return None

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
                except: pass
        
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
            return re.search(r"^(.*)\.", local_ip).group(0)
        except: return None

    def check_webman(self, ip, timeout=2):
        if not ip: return False
        try:
            r = requests.get(f"http://{ip}", headers=headers, timeout=timeout)
            if r.status_code == 200:
                return "wMAN" in r.text or "webMAN" in r.text
        except: pass
        return False


    def connect_discord(self):
        if self.rpc: return True
        try:
            self.rpc = Presence(self.config["client_id"])
            self.rpc.connect()
            return True
        except:
            self.rpc = None
            return False

    def disconnect_discord(self):
        if self.rpc:
            try: self.rpc.clear()
            except: pass
            try: self.rpc.close()
            except: pass
            self.rpc = None

# Actu de Covers
    def resolve_cover(self, title_id):
        if title_id in self.cover_cache:
            return self.cover_cache[title_id]

        if not title_id or len(title_id) < 4:
            return "ps3_icon"

        urls_to_try = []
        # GameTDB
        region_map = {'U': 'US', 'E': 'EN', 'J': 'JA', 'K': 'KO', 'A': 'EN'}
        region_code = region_map.get(title_id[2], 'EN')
        urls_to_try.append(f"https://art.gametdb.com/ps3/cover/{region_code}/{title_id}.jpg")
        # Aldostools
        urls_to_try.append(f"https://raw.githubusercontent.com/aldostools/Resources/main/COV/{title_id}.JPG")
        urls_to_try.append(f"https://raw.githubusercontent.com/aldostools/Resources/main/COV/{title_id}.jpg") 

        valid_url = "ps3_icon" 
        for url in urls_to_try:
            try:
                check = requests.head(url, timeout=1.5)
                if check.status_code == 200:
                    valid_url = url
                    break
            except: continue
        
        self.cover_cache[title_id] = valid_url
        return valid_url

    def get_game_status(self, ip):
        try:
            url = f"http://{ip}/cpursx.ps3?/sman.ps3"
            r = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(r.text, "html.parser")
            
            self.load_config()

            state_text = None 
            if self.config.get("show_temp", False):
                try:
                    temps = str(soup.find("a", href="/cpursx.ps3?up"))
                    cpu = re.search(r"CPU(.+?)C", temps).group(0)
                    rsx = re.search(r"RSX(.+?)C", temps).group(0)
                    state_text = f"{cpu} | {rsx}"
                except: pass

            image = "ps3" 
            title = "Menú Principal" 
            details = "XMB" 
            is_xmb = False

            if soup.find("a", target="_blank"):
                tag = soup.find("a", target="_blank")
                raw_id_tag = str(tag)
                try: game_id = re.search(r">(.*)<", raw_id_tag).group(1)
                except: game_id = ""

                raw_name = str(tag.find_next_sibling()).replace("\n", "")
                try:
                    full_name = re.search(r">(.*)<", raw_name).group(1)
                    clean_name = re.sub(r"\s+v?\d{2}\.\d{2}$", "", full_name)
                    clean_name = re.sub(r"\s+\d\.\d{2}$", "", clean_name)
                    clean_name = re.sub(r"\[.*?\]", "", clean_name)
                    details = clean_name.strip()
                except: details = "Juego PS3"

                title = "Jugando"
                image = self.resolve_cover(game_id)

            elif soup.find("a", href=re.compile(r"/(dev_hdd0|dev_usb00[0-9])/(PSXISO|PS2ISO)")):
                tag = soup.find("a", href=re.compile(r"/(dev_hdd0|dev_usb00[0-9])/(PSXISO|PS2ISO)"))
                try: details = re.search(r'">(.*)</a>', str(tag.find_next_sibling())).group(1)
                except: details = "Juego Retro"
                title = "Clásico"
                image = "retro"
            else:
                is_xmb = True

            return {
                "details": details[:127],
                "state": state_text,      
                "large_image": image,     
                "large_text": title,
                "is_xmb": is_xmb
            }
        except Exception:
            return None

# Main
if __name__ == "__main__":
    app = PS3Manager()
    
    while True:
        # Busca IP de PS#
        current_ip = None
        while not current_ip:
            current_ip = app.find_ps3()
            if not current_ip: sleep(15)
        
        start_time = time()
        strikes = 0
        
        while True:
            app.load_config()

            data = app.get_game_status(current_ip)
            
            if not data:
                strikes += 1
                if strikes >= 3:
                    print("PS3 Apagada.")
                    app.disconnect_discord()
                    break 
                sleep(20) 
                continue 
            strikes = 0 

            if data['is_xmb'] and not app.config.get("show_xmb", False):
                if app.rpc:
                    print("En XMB (Ocultando)...")
                    app.disconnect_discord()
                sleep(app.config.get("wait_seconds", 45))
                continue
            
            if not app.rpc:
                if not app.connect_discord():
                    sleep(15)
                    continue

            try:
                app.rpc.update(
                    details=data['details'],
                    state=data['state'], 
                    large_image=data['large_image'],
                    large_text=data['large_text'],
                    start=start_time
                )
            except:
                app.disconnect_discord()
                break

            sleep(app.config.get("wait_seconds", 45))
        
        sleep(5)