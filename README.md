# Lucky 流量审计看板 (Final Edition)
本看板专门针对 Lucky 的 Web 服务日志提供实时审计。

#项目架构
lucky-web-monitor/
├── Dockerfile
├── main.py
├── index.html
└── data/
    ├── config.json
    ├── lucky_logs.csv
    ├── ip_geo.json
    └── icon.png

#目录说明
- main.py : 后端核心逻辑
- index.html : 前端 UI 界面
- data/ : 数据存储目录
    - config.json : 核心配置文件
    - lucky_logs.csv ：日志存储目录
    - ip_geo.json : IP 归属地自动缓存
    - icon.png ：logo
 
#使用说明
在config文件内填入lucky的url与opentoken
推荐docker运行
docker build -t lucky-web-monitor:latest .
docker compose up -d

#依赖
   fastapi uvicorn requests apscheduler
