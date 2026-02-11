<img width="1912" height="924" alt="image" src="https://github.com/user-attachments/assets/3f25fe68-9c85-46c4-a0da-ef4cc7e48fa1" />
# Lucky 流量审计看板 (Final Edition)
本看板专门针对 Lucky 的 Web 服务日志提供实时审计。

#项目架构  
lucky-web-monitor/  
├── Dockerfile  
├── main.py  
├── index.html  
└── data/  
&emsp;&emsp;├── config.json  
&emsp;&emsp;├── lucky_logs.csv  
&emsp;&emsp;├── ip_geo.json  
&emsp;&emsp;└── icon.png  

#目录说明
- main.py : 后端核心逻辑
- index.html : 前端 UI 界面
- data/ : 数据存储目录
    - config.json : 核心配置文件
    - lucky_logs.csv ：日志存储文件
    - ip_geo.json : IP 归属地自动缓存
    - icon.png ：logo
 
#使用说明
在config文件内填入lucky的url与opentoken  
推荐docker运行  
docker build -t lucky-web-monitor:latest .  
docker compose up -d  

#依赖
   fastapi uvicorn requests apscheduler
