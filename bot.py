"""
- Fetches proxies from multiple public sources
- Checks live proxies concurrently
- Prunes dead or slow proxies automatically
- Shares live proxies to a Telegram chat
"""

import asyncio
import aiohttp
import requests
import datetime
import re
from tqdm import tqdm
from colorama import Fore, Style, init
import time
import random
import sys
from aiogram import Bot

# ---------------- SETTINGS ---------------- #
TOKEN = "8293451482:AAHVbqblT4O35Hn0HZG_-osVMAOsI-mF6Ko"
CHAT_ID = 8073139751
TEST_URL = "https://httpbin.org/ip"
TIMEOUT = 8
CONCURRENCY = 200
REFRESH_INTERVAL = 600  # seconds between fetch cycles
PRUNE_INTERVAL = 7200   # seconds between pruning cycles
MAX_LATENCY_MS = 500    # only keep proxies faster than this
USER_AGENT = "Mozilla/5.0 (compatible; YUICHI-proxy-collector/1.0)"
IPPORT_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b")

# ---------------- SOURCES ---------------- #
GEONODE_API = "https://proxylist.geonode.com/api/proxy-list?limit=100&sort_by=lastChecked&sort_type=desc"
PROXYSCRAPE_API = (
    "https://api.proxyscrape.com/v2/?request=getproxies"
    "&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
)
FREE_PROXY_URL = "https://free-proxy-list.net/"

# TheSpeedX raw proxy lists
SPEEDX_HTTP = "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
SPEEDX_HTTPS = "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/https.txt"
SPEEDX_SOCKS = "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"

# ---------------- BANNER ---------------- #
YUICHI_BANNER = r"""
##    ## ##     ## ####  ######  ##     ## #### 
 ##  ##  ##     ##  ##  ##    ## ##     ##  ##  
  ####   ##     ##  ##  ##       ##     ##  ##  
   ##    ##     ##  ##  ##       #########  ##  
   ##    ##     ##  ##  ##       ##     ##  ##  
   ##    ##     ##  ##  ##    ## ##     ##  ##  
   ##     #######  ####  ######  ##     ## #### 
"""

# Strip ANSI if unsupported
init(autoreset=True, strip=True, convert=True)

def print_banner():
    banner = f"{Fore.GREEN}{Style.BRIGHT}{YUICHI_BANNER}{Style.RESET_ALL}"
    print(banner)
    print(f"{Fore.CYAN}        Continuous Proxy Collector — By YUICHI\n{Style.RESET_ALL}")

# ---------------- FETCHING ---------------- #
def fetch_from_geonode():
    out = set()
    try:
        r = requests.get(GEONODE_API, headers={"User-Agent": USER_AGENT}, timeout=12)
        if r.status_code == 200:
            j = r.json()
            for item in j.get("data", []) if isinstance(j, dict) else []:
                ip = item.get("ip") or item.get("address") or ""
                port = str(item.get("port") or "")
                if ip and port:
                    out.add(f"{ip}:{port}")
    except Exception:
        pass
    return out

def fetch_from_proxyscrape():
    out = set()
    try:
        r = requests.get(PROXYSCRAPE_API, headers={"User-Agent": USER_AGENT}, timeout=12)
        if r.status_code == 200 and r.text:
            for line in r.text.splitlines():
                line = line.strip()
                if line and ":" in line:
                    out.add(line)
    except Exception:
        pass
    return out

def fetch_from_free_proxy_list():
    out = set()
    try:
        r = requests.get(FREE_PROXY_URL, headers={"User-Agent": USER_AGENT}, timeout=12)
        if r.status_code == 200 and r.text:
            matches = IPPORT_RE.findall(r.text)
            out.update(matches)
    except Exception:
        pass
    return out

def fetch_from_raw_github(url):
    out = set()
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=12)
        if r.status_code == 200 and r.text:
            for line in r.text.splitlines():
                line = line.strip()
                if line and ":" in line:
                    out.add(line)
    except Exception:
        pass
    return out

def fetch_all_sources():
    sources = [
        ("GeoNode", fetch_from_geonode),
        ("ProxyScrape", fetch_from_proxyscrape),
        ("FreeProxyList", fetch_from_free_proxy_list),
        ("SpeedX HTTP", lambda: fetch_from_raw_github(SPEEDX_HTTP)),
        ("SpeedX HTTPS", lambda: fetch_from_raw_github(SPEEDX_HTTPS)),
        ("SpeedX SOCKS5", lambda: fetch_from_raw_github(SPEEDX_SOCKS)),
    ]
    combined = set()
    print(f"{Fore.CYAN}Fetching from multiple sources...{Style.RESET_ALL}")
    for name, fn in sources:
        try:
            items = fn()
            print(f"{Fore.GREEN}[+] {len(items):5d}{Style.RESET_ALL} from {name}")
            combined.update(items)
        except Exception:
            print(f"{Fore.YELLOW}[!] Failed: {name}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}Total fetched (unique): {len(combined)}{Style.RESET_ALL}")
    return list(combined)

# ---------------- CHECKING ---------------- #
async def check_single_proxy(session, proxy, seen_live, file_lock, bot, measure_latency=False):
    if proxy in seen_live:
        return
    try:
        proxy_url = "http://" + proxy
        start = time.time()
        async with session.get(TEST_URL, proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
            latency_ms = (time.time() - start) * 1000
            if 200 <= resp.status < 400:
                if measure_latency and latency_ms > MAX_LATENCY_MS:
                    return
                async with file_lock:
                    if proxy not in seen_live:
                        seen_live.add(proxy)
                        print(f"{Fore.GREEN}[LIVE]{Style.RESET_ALL} {proxy} ({int(latency_ms)}ms)")
                        try:
                            await bot.send_message(CHAT_ID, f"LIVE Proxy: {proxy} ({int(latency_ms)}ms)")
                        except Exception as e:
                            print(f"{Fore.YELLOW}Failed to send to Telegram: {e}{Style.RESET_ALL}")
    except Exception:
        return

async def check_batch(proxies, seen_live, bot, measure_latency=False):
    if not proxies:
        return
    connector = aiohttp.TCPConnector(ssl=False, limit_per_host=CONCURRENCY)
    sem = asyncio.Semaphore(CONCURRENCY)
    file_lock = asyncio.Lock()
    async with aiohttp.ClientSession(connector=connector) as session:
        async def bounded(p):
            async with sem:
                await check_single_proxy(session, p, seen_live, file_lock, bot, measure_latency)
        tasks = [bounded(p) for p in proxies]
        for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc=f"{Fore.CYAN}Checking", ncols=100):
            try:
                await f
            except Exception:
                pass

# ---------------- PRUNING ---------------- #
async def prune_live_proxies(seen_live, bot):
    while True:
        if not seen_live:
            await asyncio.sleep(PRUNE_INTERVAL)
            continue
        print(f"{Fore.CYAN}Pruning live proxies...{Style.RESET_ALL}")
        proxies = list(seen_live)
        seen_live_copy = set()
        connector = aiohttp.TCPConnector(ssl=False, limit_per_host=CONCURRENCY)
        file_lock = asyncio.Lock()
        sem = asyncio.Semaphore(CONCURRENCY)
        async with aiohttp.ClientSession(connector=connector) as session:
            async def bound_check(p):
                async with sem:
                    await check_single_proxy(session, p, seen_live_copy, file_lock, bot, measure_latency=True)
            tasks = [bound_check(p) for p in proxies]
            for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc=f"{Fore.MAGENTA}Pruning", ncols=100):
                try:
                    await f
                except Exception:
                    pass
        seen_live.clear()
        seen_live.update(seen_live_copy)
        print(f"{Fore.GREEN}Pruning complete. Live proxies now: {len(seen_live)}{Style.RESET_ALL}")
        await asyncio.sleep(PRUNE_INTERVAL)

# ---------------- MAIN LOOP ---------------- #
async def run_continuous(bot):
    seen_all = set()
    seen_live = set()

    cycle = 1
    asyncio.create_task(prune_live_proxies(seen_live, bot))

    while True:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        print(f"\n{Fore.MAGENTA}=== Cycle {cycle} @ {now} ==={Style.RESET_ALL}")
        proxies = fetch_all_sources()
        new = [p for p in proxies if p not in seen_all]
        print(f"{Fore.CYAN}New proxies to test this cycle: {len(new)}{Style.RESET_ALL}")
        for p in new:
            seen_all.add(p)
        if new:
            await check_batch(new, seen_live, bot)
        else:
            print(f"{Fore.YELLOW}No new proxies found this cycle.{Style.RESET_ALL}")
        cycle += 1
        await asyncio.sleep(REFRESH_INTERVAL)

# ---------------- ENTRY POINT ---------------- #
async def main_async():
    bot = Bot(token=TOKEN)
    print_banner()
    try:
        await bot.send_message(CHAT_ID, f"{YUICHI_BANNER}\nContinuous Proxy Collector — By YUICHI\nStarted!")
    except Exception as e:
        print(f"{Fore.YELLOW}Failed to send start message: {e}{Style.RESET_ALL}")
    try:
        await run_continuous(bot)
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Stopped by user. Bye from YUICHI.{Style.RESET_ALL}")
        try:
            await bot.send_message(CHAT_ID, "Proxy Collector stopped.")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main_async())
