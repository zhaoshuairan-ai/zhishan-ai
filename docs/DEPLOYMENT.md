# 部署指南（本地 → 局域网 → 公网）

> 三个阶段请按顺序完成。**在真正完成公网部署并验证之前，不要对外宣称已可公网访问，也不要使用示例地址。**
> 本文中出现的 `your-domain.com`、`192.168.1.100` 均为占位示例，需要替换成你自己的实际值。

---

## 阶段 A · 电脑本地开发

详见 [WINDOWS_SETUP.md](WINDOWS_SETUP.md)。最小步骤：

```powershell
cd D:\食品项目\food-safety-ai
.\start.bat            # 或手动启动前后端
# 浏览器打开 http://localhost:5173，使用 demo / demo123456 登录
```

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health     # data.status = ok
```

---

## 阶段 B · 手机局域网测试

### B1. 前提

- 手机与电脑连接**同一个 Wi-Fi**（同一网段，不能一个连 5G 一个连访客网络）
- 电脑没有开启「隔离模式/访客网络」的 AP
- 前端开发服务器已监听 `0.0.0.0`（本项目 `vite.config.ts` 已配置 `host: '0.0.0.0'`）

### B2. 查看电脑的局域网 IP

```powershell
ipconfig
```

找到当前 Wi-Fi 适配器的 **IPv4 地址**，例如：

```
无线局域网适配器 WLAN:
   IPv4 地址 . . . . . . . . . . . . : 192.168.1.100
```

也可以只取 Wi-Fi 的地址：

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.InterfaceAlias -like "*WLAN*" -or $_.InterfaceAlias -like "*Wi-Fi*" } |
  Select-Object IPAddress, InterfaceAlias
```

### B3. 手机访问地址

| 模式 | 手机地址 | 说明 |
| --- | --- | --- |
| 开发模式（Vite） | `http://192.168.1.100:5173` | 推荐；Vite 会把 `/api` 代理到本机 5000，手机只需访问 5173 |
| 生产模式（单服务 waitress） | `http://192.168.1.100:8000` | 运行 `start_prod.bat` 后可用，无需前端开发服务器 |
| 直接访问后端 | `http://192.168.1.100:5000/api/health` | 只用于验证后端，页面在 5173/8000 |

❌ **错误做法**：在手机上访问 `http://localhost:5173` —— localhost 指手机自己，必然打不开。

### B4. Windows 防火墙放行

首次启动 Python/Node 时系统通常会弹窗询问，选择「允许访问」并勾选「专用网络」。
若错过了，可用管理员 PowerShell 手动添加：

```powershell
# 以管理员身份运行 PowerShell
New-NetFirewallRule -DisplayName "智膳-前端5173" -Direction Inbound -Action Allow `
  -Protocol TCP -LocalPort 5173 -Profile Private
New-NetFirewallRule -DisplayName "智膳-后端5000" -Direction Inbound -Action Allow `
  -Protocol TCP -LocalPort 5000 -Profile Private
New-NetFirewallRule -DisplayName "智膳-生产8000" -Direction Inbound -Action Allow `
  -Protocol TCP -LocalPort 8000 -Profile Private
```

查看/删除：

```powershell
Get-NetFirewallRule -DisplayName "智膳*" | Select-Object DisplayName, Enabled
# Remove-NetFirewallRule -DisplayName "智膳-前端5173"
```

### B5. 验证与排查

1. 电脑浏览器打开 `http://192.168.1.100:5173`（用 IP 而不是 localhost）——能打开说明监听正确。
2. 手机浏览器打开同一地址。
3. 打不开时按顺序排查：
   - 手机是否在同一 Wi-Fi（关闭移动数据再试）
   - IP 是否写对（`ipconfig` 重新确认，路由器重启后 IP 可能变化）
   - 防火墙是否放行
   - 电脑是否休眠/锁屏断网
   - 路由器是否开启了「AP 隔离」

### B6. 跨设备数据共享验证（重要）

1. 电脑登录 `demo`，上传一张标签图片并完成分析。
2. 手机浏览器打开同一地址，登录**同一个账号**。
3. 手机「历史记录」中应能看到刚才那条记录，点开结果页与电脑一致。
4. 在手机上再新建一条记录，电脑刷新历史记录也能看到。

> 数据来自同一个后端 SQLite 数据库与 `uploads/` 目录，不是浏览器本地存储；
> 因此刷新页面、关闭浏览器、重启服务（数据文件保留）都不会丢失。

### B7. 局域网模式的限制

- 只在同一网络内可用，异地评委无法访问。
- 大多数家庭宽带没有公网 IP，**直接端口转发**通常不可行也不安全。
- 公网演示请使用下一阶段的方案。

---

## 管理员账号初始化（部署必做）

管理员不能通过注册页创建，必须在服务器上执行一次：

```bash
cd /opt/food-safety-ai
python scripts/create_admin.py --username admin
```

- 交互式输入密码（≥10 位且含字母和数字），只保存 scrypt 哈希；
- 也可以用 `--random` 生成一次性强密码，脚本只打印一次，不落盘；
- 切勿把管理员密码写入仓库、README、环境变量文件或 CI 配置；
- 忘记密码时用 `--promote` 重新设置，同时会写一条 `admin.bootstrap` 审计日志；
- 登录地址：`https://你的域名/admin/login`。

## 阶段 C · 公网部署（HTTPS）

### C0. 先明确三件事

1. **数据库与图片必须持久化**：容器重启后 `/data` 不能丢，否则记录全部消失。
2. **HTTPS 是硬性要求**：PWA 安装、部分浏览器的相机/剪贴板能力只在 HTTPS（或 localhost）下可用。
3. **生产必须修改密钥**：`SECRET_KEY`、`DEMO_PASSWORD` 不能沿用示例值。

生产环境变量建议：

```ini
FLASK_ENV=production
SECRET_KEY=<用 python -c "import secrets;print(secrets.token_urlsafe(48))" 生成>
DEMO_PASSWORD=<改成你自己的演示密码>
SERVE_FRONTEND=1
APP_HOST=0.0.0.0
APP_PORT=8000
DATA_DIR=/data
UPLOAD_DIR=/data/uploads
PUBLIC_SITE_URL=https://your-domain.com
CORS_ORIGINS=https://your-domain.com
# Key 按需配置；不配置也能以本地 OCR + 规则模式运行
AI_API_KEY=
OCR_VISION_API_KEY=
```

---

### 方案 1（推荐）· 云服务器 + Docker + Caddy 自动 HTTPS

**适合**：有云服务器（阿里云/腾讯云/华为云/雨云等）与域名，想长期运行。

1. **准备服务器**：1 核 2G 起（OCR 推理需要一点内存，2G 更稳），系统 Ubuntu 22.04。
2. **域名解析**：把 `your-domain.com` 的 A 记录指向服务器公网 IP。
3. **安全组/防火墙**：放行 80、443（**不要**对公网开放 8000/5000）。
4. **上传项目并构建**：

```bash
# 服务器上
git clone <你的仓库> food-safety-ai && cd food-safety-ai   # 或 scp 上传
cp .env.example .env && nano .env      # 按上面「生产环境变量建议」修改
docker build -t food-safety-ai .
docker run -d --name fsai \
  -p 127.0.0.1:8000:8000 \
  -v fsai-data:/data \
  --env-file .env \
  --restart unless-stopped \
  food-safety-ai
```

> 只绑定 `127.0.0.1:8000`，由 Caddy 反向代理并负责 HTTPS。

5. **Caddy 反向代理（自动申请证书）**：

```bash
sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`：

```
your-domain.com {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
```

```bash
sudo systemctl reload caddy
sudo systemctl status caddy
```

6. **验证**：

```bash
curl -s https://your-domain.com/api/health | head -c 300
# 期望包含 "status":"ok"
```

在电脑上运行：

```powershell
backend\.venv\Scripts\python.exe scripts\prod_smoke_test.py --base-url https://your-domain.com
```

---

### 方案 2 · Render（PaaS，无需运维）

**适合**：不想管服务器，能接受免费实例休眠。

1. 注册 <https://render.com>，把仓库推到 GitHub。
2. New → **Web Service** → 连接仓库 → Runtime 选择 **Docker**。
3. 配置：
   - Health Check Path：`/api/health`
   - Environment：把上面「生产环境变量」逐条填进去（`SERVE_FRONTEND=1`、`DATA_DIR=/data`、`UPLOAD_DIR=/data/uploads`）
4. **添加持久磁盘**（Disks）：Mount Path 填 `/data`，大小 1GB 起。
   > 不挂磁盘的话，每次重新部署都会清空数据库与图片。
5. 部署完成后 Render 会给出 `https://xxx.onrender.com` 地址。
6. 验证：

```powershell
backend\.venv\Scripts\python.exe scripts\prod_smoke_test.py --base-url https://xxx.onrender.com
```

> 免费实例一段时间无访问会休眠，首次打开需要等待几十秒；比赛现场演示建议升级付费实例或使用方案 1/3。

---

### 方案 3 · Cloudflare Tunnel（最快拿到临时 HTTPS 地址）

**适合**：比赛前一天快速让异地评委访问，无需服务器与域名。

1. 本机以生产模式启动（`start_prod.bat`，监听 8000）。
2. 安装 cloudflared：<https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/>
3. 运行快速隧道（无需注册账号）：

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

4. 终端会输出类似：

```
Your quick Tunnel has been created! Visit it at:
https://random-words-1234.trycloudflare.com
```

5. **立刻**用手机/另一台设备验证该地址可用，再运行：

```powershell
backend\.venv\Scripts\python.exe scripts\prod_smoke_test.py --base-url https://random-words-1234.trycloudflare.com
```

⚠️ 注意：

- 该地址是**临时的**，关掉 cloudflared 就失效，重启后地址会变。
- 电脑休眠/断网会导致外网不可访问；演示时保持电脑唤醒、网络稳定。
- 需要固定地址时，请使用 Cloudflare 账号创建 **命名隧道** 并绑定自己的域名（免费版即可）。
- 同理可用 `ngrok http 8000`（需要注册 token），但免费域名同样会变化。

---

### C1. HTTPS 相关说明

| 项目 | 说明 |
| --- | --- |
| 证书 | 方案 1 由 Caddy 自动申请与续期；PaaS 方案由平台提供 |
| 混合内容 | 前端通过相对路径 `/api` 访问，同源部署不会出现 http/https 混用 |
| Cookie | 本项目使用 `Authorization: Bearer`，不依赖 Cookie，因此无需 SameSite 配置 |
| 信任代理 | 若在代理后需要真实客户端 IP，请在 Nginx/Caddy 里透传 `X-Forwarded-For`（登录限流会读取它） |
| HTTP 跳转 | 建议把 80 端口 301 跳转到 443（Caddy 默认已处理） |

---

### C2. 前端与后端分开部署（可选）

若前端放 Vercel/Netlify、后端放 Render：

1. 前端构建时设置环境变量：

```ini
VITE_API_BASE_URL=https://your-backend.onrender.com/api
```

2. 后端 `.env` 设置：

```ini
CORS_ORIGINS=https://your-frontend.vercel.app
SERVE_FRONTEND=0
```

3. 重新构建前端（`npm run build`），把 `dist` 部署到静态托管。
4. 注意：分开部署时图片接口仍需带 Authorization 头（前端已这样实现），不要直接把图片 URL 放到 `<img src>`。

---

### C3. 部署后检查清单

- [ ] `GET https://你的域名/api/health` 返回 `200` 且 `data.status = "ok"`
- [ ] 首页、登录页能正常打开（无混合内容报错）
- [ ] 能注册/登录，上传图片并完成 OCR → 分析 → 报告
- [ ] 手机浏览器打开同一地址，登录同一账号能看到电脑创建的记录
- [ ] 刷新页面、重启容器后记录仍在（验证持久化卷）
- [ ] `python scripts/prod_smoke_test.py --base-url https://你的域名` 全部通过
- [ ] `SECRET_KEY` 与 `DEMO_PASSWORD` 已改为非默认值
- [ ] 数据库与 `uploads/` 在持久化目录，且已配置备份
- [ ] 未把 `.env` 提交到公开仓库

### C4. 生成扫码二维码

```powershell
backend\.venv\Scripts\python.exe scripts\generate_qr.py --url https://你的域名 --out docs/qr-code.png
```

生成的图片可以直接放到 PPT 或打印出来。**先自己用手机扫一次确认能打开**，再交给评委。

---

## 附：常见部署问题

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| 打开首页 404 | `SERVE_FRONTEND=0` 或未部署 `frontend/dist` | 构建前端并设置 `SERVE_FRONTEND=1`，或使用分离部署 |
| 页面能开但接口 502 | 后端容器没起来/端口不对 | 看容器日志；确认 `waitress` 监听 8000 |
| 上传图片后 502/超时 | 反向代理超时太短 | Caddy/Nginx 增加 `proxy_read_timeout 300s` |
| 记录在重启后消失 | 没挂持久化卷 | 挂载 `/data`（数据库与图片都在里面） |
| 手机能开但上传失败 | HTTPS 证书问题或反向代理限制请求体 | 调大 `client_max_body_size`（Nginx）并确认证书有效 |
| PWA 无法安装 | 非 HTTPS 或 manifest 未正确返回 | 确认 HTTPS，访问 `/manifest.webmanifest` 返回 JSON |
| OCR 很慢 | 免费实例 CPU 弱 | 换 2 核以上实例；或配置视觉模型 OCR |
| 演示账号能登录但没数据 | 初始化时未生成演示数据 | 运行 `python backend/init_db.py`（幂等） |

---

## 家庭食材临期通知（每日 08:00）

```bash
# 发一次（适合 Windows 任务计划 / cron）
.\backend\.venv\Scripts\python.exe scripts\pantry_daily_notify.py

# 常驻模式，每天 08:00 发送
.\backend\.venv\Scripts\python.exe scripts\pantry_daily_notify.py --loop --at 08:00
```

- 未配置 `SMTP_HOST` / `SMTP_FROM` 时，会把摘要写入 `data/notifications/email-YYYY-MM-DD.log`，并标记为 `simulated`，不会假装发送；
- 配置 `WECOM_WEBHOOK_URL` / `DINGTALK_WEBHOOK_URL` 可同时推送群机器人；
- 通知内容只包含当前用户自己的库存临期信息；脚本遍历启用账号逐个生成摘要；
- 这是「每日 8 点推送」的定时任务实现；Web 页面内还有 SSE 实时提醒（仅食材管家页），两者不冲突。
