import json, requests, datetime, csv, os, urllib3
from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager

# 彻底禁用 InsecureRequestWarning 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 目录与文件路径配置 ---
DATA_DIR = "data"
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
CSV_FILE = os.path.join(DATA_DIR, "lucky_logs.csv")
GEO_CACHE_FILE = os.path.join(DATA_DIR, "ip_geo.json")
ICON_FILE = os.path.join(DATA_DIR, "icon.png") # 定义图标路径

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# --- 1. 配置加载逻辑 ---
def load_config():
    default_config = {
        "lucky_url": "https://YOUR_LUCKY_URL:16601",
        "open_token": "YOUR_TOKEN_HERE",
        "sync_interval_minutes": 1
    }
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"[*] 已生成默认配置，请修改 {CONFIG_FILE} 后重启程序。")
        return default_config
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

config = load_config()
LUCKY_URL = config.get("lucky_url")
TOKEN = config.get("open_token")
SYNC_MINS = config.get("sync_interval_minutes", 1)

# --- 2. 优化连接池 ---
session = requests.Session()
session.headers.update({"openToken": TOKEN})
session.verify = False

# --- 3. 归属地持久化逻辑 ---
ip_geo_cache = {}

if os.path.exists(GEO_CACHE_FILE):
    try:
        with open(GEO_CACHE_FILE, 'r', encoding='utf-8') as f:
            ip_geo_cache = json.load(f)
    except: ip_geo_cache = {}

def save_geo_cache():
    try:
        with open(GEO_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(ip_geo_cache, f, ensure_ascii=False)
    except Exception as e:
        print(f"保存 Geo 缓存失败: {e}")

def get_geo(ip):
    if ip.startswith(("192.168.", "10.", "172.", "127.", "169.254.")): return "局域网"
    if ip in ip_geo_cache: return ip_geo_cache[ip]
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?lang=zh-CN", timeout=3)
        res = r.json()
        if res.get('status') == 'success':
            location = f"{res.get('regionName','')} {res.get('city','')}".strip()
            ip_geo_cache[ip] = location or "未知公网"
            save_geo_cache()
            return ip_geo_cache[ip]
        return "查询失败"
    except: return "查询超时"

# --- 4. CSV 持久化逻辑 ---
def load_csv_logs():
    logs = []
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader: logs.append(row)
        except Exception as e: print(f"读取 CSV 失败: {e}")
    return logs

def save_logs_to_csv(logs):
    try:
        keys = ["time", "ip", "host", "method", "url", "rule"]
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(logs)
    except Exception as e: print(f"写入 CSV 失败: {e}")

current_logs = load_csv_logs()
data_cache = {"logs": current_logs, "ip_rank": [], "last_update": "启动中..."}

def fetch_lucky_data():
    global data_cache, current_logs
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 开始同步...")
    try:
        r_resp = session.get(f"{LUCKY_URL}/api/webservice/rules", timeout=10)
        rules_list = r_resp.json().get('ruleList', [])
        new_fetched_logs = []

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
                            new_fetched_logs.append({
                                "time": l['LogTime'],
                                "ip": ext.get('ClientIP'),
                                "host": ext.get('Host'),
                                "method": ext.get('Method'),
                                "url": ext.get('URL'),
                                "rule": r_name
                            })
                except: continue

        # 去重合并
        existing_keys = set((x['time'], x['ip'], x['url']) for x in current_logs)
        for log in new_fetched_logs:
            key = (log['time'], log['ip'], log['url'])
            if key not in existing_keys:
                current_logs.append(log)
                existing_keys.add(key)

        current_logs.sort(key=lambda x: x['time'], reverse=True)
        current_logs = current_logs[:2000]
        save_logs_to_csv(current_logs)

        ip_counts = {}
        for l in current_logs:
            ip = l['ip']
            ip_counts[ip] = ip_counts.get(ip, 0) + 1

        rank = [{"ip": ip, "count": count, "location": get_geo(ip)} for ip, count in ip_counts.items()]

        data_cache = {
            "logs": current_logs,
            "ip_rank": sorted(rank, key=lambda x: x['count'], reverse=True),
            "last_update": datetime.datetime.now().strftime("%H:%M:%S")
        }
    except Exception as e: print(f"同步异常: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    fetch_lucky_data()
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_lucky_data, 'interval', minutes=SYNC_MINS, max_instances=1, coalesce=True)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/api/data")
def get_api_data(): return data_cache

@app.get("/")
def read_index(): return FileResponse('index.html')

# --- 新增：Icon 图标路由 ---
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    if os.path.exists(ICON_FILE):
        return FileResponse(ICON_FILE)
    return Response(status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
