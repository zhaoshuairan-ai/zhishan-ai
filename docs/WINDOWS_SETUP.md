# Windows 本地运行指南（面向初学者）

本指南假设你使用的是 **Windows 10/11**，从未配置过 Python / Node.js 环境。
按顺序执行即可，每一步都给出了验证命令和预期结果。

---

## 一、安装必备软件

### 1. Python 3.11 或 3.12

1. 打开 <https://www.python.org/downloads/windows/>，下载 **Python 3.12.x**（64-bit installer）。
2. 安装时**务必勾选** `Add python.exe to PATH`。
3. 安装完成后，**新开一个 PowerShell 窗口**验证：

```powershell
python --version      # 期望：Python 3.12.x
pip --version         # 期望：pip 24.x ...
```

> 若提示「无法将 python 项识别为 cmdlet」，说明没有加入 PATH：
> 重新运行安装包 → Modify → 勾选 Add Python to PATH，或手动把
> `C:\Users\你的用户名\AppData\Local\Programs\Python\Python312\` 加入 PATH。

### 2. Node.js 18 或更高版本（推荐 LTS）

1. 打开 <https://nodejs.org/zh-cn/download>，下载 **LTS 版本**（.msi）。
2. 一路默认安装即可（会自动加入 PATH）。
3. 新开 PowerShell 验证：

```powershell
node --version        # 期望：v18.x / v20.x / v22.x
npm --version         # 期望：9.x / 10.x / 11.x
```

### 3. Git（可选，用于版本管理）

<https://git-scm.com/download/win>，安装后：

```powershell
git --version
```

---

## 二、获取项目

把 `food-safety-ai` 整个文件夹放到一个**路径不含空格**的位置，例如：

```
D:\食品项目\food-safety-ai
```

进入目录：

```powershell
cd D:\食品项目\food-safety-ai
```

---

## 三、一键启动（推荐）

双击 **`start.bat`**，或在 PowerShell 中执行：

```powershell
.\start.bat
```

脚本会依次完成：

| 步骤 | 内容 | 说明 |
| --- | --- | --- |
| 1/7 | 检查 Python / Node.js | 版本不符会给出明确提示 |
| 2/7 | 创建 `backend\.venv` | 首次约 10-30 秒 |
| 3/7 | 复制 `.env.example` → `.env` | 已存在则跳过 |
| 4/7 | 安装后端依赖 | 首次 1-3 分钟（含 OCR 引擎） |
| 5/7 | 安装前端依赖 | 首次 1-2 分钟 |
| 6/7 | 初始化数据库与知识库 | 建表 + 52 条知识 + 演示账号与演示记录 |
| 7/7 | 启动前后端并打开浏览器 | 前端 5173，后端 5000 |

启动成功后：

- 电脑访问：<http://localhost:5173>
- 演示账号：`demo` / `demo123456`
- 日志：`logs\backend.log`、`logs\frontend.log`

停止服务：双击 **`stop.bat`**（会释放 5000 / 5173 / 4173 / 8000 端口）。

---

## 四、手动启动（推荐至少完整走一遍）

### 4.1 后端

```powershell
cd D:\食品项目\food-safety-ai\backend

# 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 若提示「禁止运行脚本」，先执行（仅当前用户）：
# Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 安装依赖（国内网络可加镜像参数）
pip install -r requirements.txt
# pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 配置环境变量（已存在则跳过）
copy ..\.env.example ..\.env

# 初始化数据库
python init_db.py

# 启动
python wsgi.py
```

预期输出：

```
智膳 AI 后端已启动：http://127.0.0.1:5000
局域网访问：http://<本机局域网IP>:5000（手机与电脑需在同一 Wi-Fi）
健康检查：http://127.0.0.1:5000/api/health
```

### 4.2 前端（另开一个 PowerShell 窗口）

```powershell
cd D:\食品项目\food-safety-ai\frontend
npm install
npm run dev
```

预期输出：

```
VITE v5.4.x  ready in 600 ms
➜  Local:   http://localhost:5173/
➜  Network: http://192.168.x.x:5173/
```

### 4.3 验证

```powershell
# 后端
Invoke-RestMethod http://127.0.0.1:5000/api/health | ConvertTo-Json -Depth 4
# 期望：success=True，data.status="ok"，checks.database.status="ok"

# 前端
(Invoke-WebRequest http://localhost:5173 -UseBasicParsing).StatusCode
# 期望：200
```

浏览器打开 <http://localhost:5173>，用 `demo / demo123456` 登录，应能看到演示数据。

---

## 五、环境自检脚本

不确定哪里没装好时，运行：

```powershell
backend\.venv\Scripts\python.exe scripts\check_env.py
```

输出示例（本机实测）：

```
[ OK ] Python 版本            3.12.14
[ OK ] 依赖 Flask             已安装
[ OK ] 本地 OCR（rapidocr）    已安装，可离线识别中文标签
[WARN] AI_API_KEY            未配置（使用基础规则模式）
[ OK ] 端口 5173（前端）       正在监听
检查完成：23 项，失败 0 项，提示 4 项
```

---

## 六、配置 AI 与 OCR（可选）

编辑项目根目录的 `.env`：

```ini
# 大模型解读（OpenAI 兼容接口）
AI_API_KEY=sk-你的密钥
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat

# 视觉模型 OCR（可选，默认用本地 OCR）
OCR_PROVIDER=auto
OCR_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OCR_VISION_API_KEY=
OCR_VISION_MODEL=qwen-vl-max
```

修改后**重启后端**，在「设置与帮助」页可以看到「已配置」状态（不会显示密钥内容）。

- 不配置任何 Key：本地 OCR + 知识库规则模式（全站标注）。
- 只配置 `AI_API_KEY`：本地 OCR + 大模型解读。
- 再配置 `OCR_VISION_API_KEY` 并把 `OCR_PROVIDER=vision`：用视觉模型识别。

### 不花钱验证「大模型模式」界面

没有真实 Key 时，可以用仓库自带的模拟服务体验完整的 AI 模式界面：

```powershell
# 窗口 1：启动模拟 OpenAI 兼容服务（仅本地，不产生真实调用）
backend\.venv\Scripts\python.exe scripts\mock_llm_server.py --port 5055

# 窗口 2：临时用模拟服务启动后端（PowerShell）
$env:AI_PROVIDER="openai"
$env:AI_API_KEY="mock-key"
$env:AI_BASE_URL="http://127.0.0.1:5055/v1"
$env:AI_MODEL="mock-model"
backend\.venv\Scripts\python.exe backend\wsgi.py
```

重新分析一条记录，结果页会显示「大模型分析 · 模型：mock-model」。
该结果由模拟服务生成，**仅用于验证链路**，不能当作真实模型输出引用；验证完请关闭这两个窗口。

---

## 七、数据备份与重置

| 操作 | 方法 |
| --- | --- |
| 备份 | 复制 `data\food_safety.db` 与整个 `uploads\` 目录 |
| 重置数据库 | 停止服务 → 删除 `data\food_safety.db` → `python backend\init_db.py` |
| 清空图片 | 停止服务 → 清空 `uploads\` 目录（数据库记录会保留，但图片打不开） |
| 修改演示密码 | 修改 `.env` 的 `DEMO_PASSWORD` → 删除数据库 → 重新初始化 |

---

## 八、常见错误速查

| 报错 / 现象 | 原因 | 解决 |
| --- | --- | --- |
| `无法将"python"项识别为 cmdlet` | PATH 未配置 | 重装 Python 勾选 Add to PATH，或手动加 PATH |
| `无法加载文件 ... Activate.ps1，因为在此系统上禁止运行脚本` | 执行策略限制 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `ModuleNotFoundError: No module named 'flask'` | 未安装依赖或用了系统 Python | 确认命令行提示符前有 `(.venv)`；`pip install -r requirements.txt` |
| `npm ERR! code ECONNREFUSED` / 安装很慢 | 网络问题 | `npm config set registry https://registry.npmmirror.com` 后重试 |
| `port 5000 is already in use` | 端口被占用 | `stop.bat`；或改 `.env` 的 `APP_PORT` |
| 前端 502 / 接口 404 | 后端没起来 | 看 `logs\backend.log`；先单独启动后端 |
| 上传后 OCR 报「引擎初始化失败」 | OCR 依赖不完整 | `pip install -r requirements.txt`（含 onnxruntime）；或临时设 `OCR_PROVIDER=demo` |
| 手机打不开 `http://电脑IP:5173` | 防火墙 / 不同 Wi-Fi | 放行端口，确认同一网段（见 docs/DEPLOYMENT.md 阶段 B） |
| 中文乱码 | 终端编码 | 执行 `chcp 65001`；或直接看日志文件（UTF-8） |
| 数据库提示缺列 | 旧版本数据库 | 已内置自动补列；仍失败则删库重新初始化 |

---

## 九、下一步

- 手机访问：见 [DEPLOYMENT.md](DEPLOYMENT.md) 阶段 B
- 公网部署与扫码：见 [DEPLOYMENT.md](DEPLOYMENT.md) 阶段 C
- 比赛演示流程与讲稿：见 [DEMO_SCRIPT.md](DEMO_SCRIPT.md)
