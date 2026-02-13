import json, requests, datetime, csv, os, urllib3, re, ipaddress, builtins, logging
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager

LOGGING_CONFIG = uvicorn.config.LOGGING_CONFIG
LOGGING_CONFIG["formatters"]["default"]["fmt"] = "[%(asctime)s] %(levelprefix)s %(message)s"
LOGGING_CONFIG["formatters"]["access"]["fmt"] = "[%(asctime)s] %(levelprefix)s %(client_addr)s - '%(request_line)s' %(status_code)s"
LOGGING_CONFIG["formatters"]["default"]["datefmt"] = "%Y-%m-%d %H:%M:%S"
LOGGING_CONFIG["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

original_print = builtins.print
def timed_print(*args, **kwargs):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return original_print(f"[{now}]", *args, **kwargs)
builtins.print = timed_print

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONFIG_DIR, DATA_DIR = "config", "data"
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
CSV_FILE = os.path.join(DATA_DIR, "lucky_logs.csv")
GEO_CACHE_FILE = os.path.join(DATA_DIR, "ip_geo.json")
ICON_FILE = os.path.join(DATA_DIR, "icon.png")

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def get_config():
    DEFAULT_URL = "http://YOUR_LUCKY_URL:YOUR_LUCKY_PORT/安全入口"
    DEFAULT_TOKEN = "YOUR_LUCKY_OPENTOKEN"

    file_conf = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_conf = json.load(f)
        except Exception as e:
            print(f"解析 config.json 失败 (请检查 JSON 格式): {e}")

    env_url = os.getenv("LUCKY_URL")
    env_token = os.getenv("OPEN_TOKEN")

    final_url = env_url or file_conf.get("lucky_url") or DEFAULT_URL
    final_token = env_token or file_conf.get("open_token") or DEFAULT_TOKEN

    use_seconds = False
    interval_val = 1

    e_sec, e_min = os.getenv("SYNC_INTERVAL_SECONDS"), os.getenv("SYNC_INTERVAL_MINUTES")
    f_sec, f_min = file_conf.get("sync_interval_seconds"), file_conf.get("sync_interval_minutes")

    if e_sec:
        interval_val, use_seconds = int(e_sec), True
    elif e_min:
        interval_val, use_seconds = int(e_min), False
    elif f_sec is not None:
        interval_val, use_seconds = int(f_sec), True
    elif f_min is not None:
        interval_val, use_seconds = int(f_min), False
    else:
        interval_val, use_seconds = 1, False

    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"lucky_url": final_url, "open_token": final_token, "sync_interval_minutes": 1}, f, indent=4, ensure_ascii=False)
            print(f"已生成配置文件模板: {CONFIG_FILE}")

    return {
        "lucky_url": final_url.rstrip('/'),
        "open_token": final_token,
        "use_seconds": use_seconds,
        "interval_val": interval_val
    }

conf = get_config()
LUCKY_URL, TOKEN = conf["lucky_url"], conf["open_token"]
USE_SECONDS, INTERVAL_VAL = conf["use_seconds"], conf["interval_val"]

session = requests.Session()
session.headers.update({"openToken": TOKEN})
session.verify = False
ip_geo_cache = {}

if os.path.exists(GEO_CACHE_FILE):
    try:
        with open(GEO_CACHE_FILE, 'r', encoding='utf-8') as f: ip_geo_cache = json.load(f)
    except: pass

def get_geo(ip):
    ip = ip.strip().split("%", 1)[0]
    try:
        addr = ipaddress.ip_address(ip)
        if addr.is_private or addr.is_loopback: return "局域网"
    except: return "格式错误"

    if ip in ip_geo_cache: return ip_geo_cache[ip]
    try:
        if ":" in ip:
            r = requests.get("https://rest.ipw.cn/api/ip/query", params={"ip": ip, "lang": "zh"}, timeout=3)
            d = r.json().get("data", {})
            loc = " ".join([d.get(k) for k in ["province", "city", "isp"] if d.get(k)])
        else:
            r = requests.get(f"http://ip-api.com/json/{ip}?lang=zh-CN", timeout=3)
            res = r.json()
            loc = f"{res.get('regionName','')} {res.get('city','')}".strip() if res.get('status') == 'success' else ""
        if loc:
            ip_geo_cache[ip] = loc
            with open(GEO_CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(ip_geo_cache, f, ensure_ascii=False)
            return loc
        return "未知位置"
    except: return "查询超时"

def load_csv_logs():
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, 'r', encoding='utf-8') as f: return list(csv.DictReader(f))
        except: return []
    return []

current_logs = load_csv_logs()
data_cache = {"logs": current_logs, "ip_rank": [], "last_update": "正在获取首次数据..."}

def fetch_lucky_data():
    global data_cache, current_logs
    if "YOUR_LUCKY_" in TOKEN:
        print("警告: 尚未在 config.json 或环境变量中配置有效的 OPEN_TOKEN，跳过同步。")
        return

    try:
        r_resp = session.get(f"{LUCKY_URL}/api/webservice/rules", timeout=10)
        r_resp.raise_for_status()
        rules_list = r_resp.json().get('ruleList', [])
        new_fetched = []

        for rule in rules_list:
            rk = rule.get('RuleKey')
            proxy_list = rule.get('ProxyList') or []
            for proxy in proxy_list:
                sk = proxy.get('Key')
                r_name = proxy.get('Remark') or (proxy.get('Domains')[0] if proxy.get('Domains') else sk)
                try:
                    l_resp = session.get(f"{LUCKY_URL}/api/webservice/{rk}/{sk}/logs?pageSize=100", timeout=5)
                    raw_logs = l_resp.json().get('logs') or []
                    for l in raw_logs:
                        ext = json.loads(l.get('LogContent', '{}')).get('ExtInfo', {})
                        if ext:
                            new_fetched.append({
                                "time": l['LogTime'], "ip": ext.get('ClientIP'),
                                "host": ext.get('Host'), "method": ext.get('Method'),
                                "url": ext.get('URL'), "rule": r_name
                            })
                except: continue

        existing_keys = set((x['time'], x['ip'], x['url']) for x in current_logs)
        added_count = 0
        for log in new_fetched:
            if (log['time'], log['ip'], log['url']) not in existing_keys:
                current_logs.append(log)
                added_count += 1

        if added_count > 0:
            current_logs.sort(key=lambda x: x['time'], reverse=True)
            current_logs = current_logs[:2000]
            with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=["time", "ip", "host", "method", "url", "rule"])
                writer.writeheader()
                writer.writerows(current_logs)

        ip_counts = {}
        for l in current_logs: ip_counts[l['ip']] = ip_counts.get(l['ip'], 0) + 1
        rank = sorted([{"ip": ip, "count": c, "location": get_geo(ip)} for ip, c in ip_counts.items()], key=lambda x: x['count'], reverse=True)

        data_cache = {"logs": current_logs, "ip_rank": rank, "last_update": datetime.datetime.now().strftime("%H:%M:%S")}
        print(f"同步完成: 新增 {added_count} 条，总计 {len(current_logs)} 条")
    except Exception as e:
        print(f"同步失败: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    fetch_lucky_data()
    sch = BackgroundScheduler()
    mode = "秒" if USE_SECONDS else "分钟"
    print(f"[*] 调度启动：每 {INTERVAL_VAL} {mode}执行一次同步")
    if USE_SECONDS:
        sch.add_job(fetch_lucky_data, 'interval', seconds=INTERVAL_VAL, max_instances=1, coalesce=True)
    else:
        sch.add_job(fetch_lucky_data, 'interval', minutes=INTERVAL_VAL, max_instances=1, coalesce=True)
    sch.start()
    yield
    sch.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/api/data")
def get_api_data(): return data_cache

@app.get("/")
def read_index(): return FileResponse('index.html')

@app.get("/favicon.ico", include_in_schema=False)
async def favicon(): return FileResponse(ICON_FILE) if os.path.exists(ICON_FILE) else Response(status_code=404)

if __name__ == "__main__":
    print(f"正在启动 Web 服务，监听 8001 端口...")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_config=LOGGING_CONFIG)
