# Curtainclock（幕窗钟）

骨架：**批窗定义 → 算力槽/执行器资源依赖就绪 → 开窗租约占用 → 关窗释放与冲突水位互证**

- 前端：http://127.0.0.1:6100 （React + Vite）
- API：http://127.0.0.1:11100

## 释放口径（全局唯一：分项释放）

租约占用算力槽与执行器两项资源，释放遵循分项释放：

- **关窗入口** `POST /api/leases/close`：一笔同释两项（事务内原子），直接收口，不产生半释放态。
- **分释入口** `POST /api/leases/release`：每次只释一项（`slot` / `executor`），租约进入 `partial`。
- **状态机**：`open → partial → closed`；两项都释放才 `closed`。
- **水位**：半释放期间 `open_leases` 不减；两项都释放才按租约减一，不会在半释放时清零。
- **阻挡语义**：半释放中已释资源可被其他批窗占用；未释资源仍阻挡对应新开窗。
- **批窗**：只有两项都释放才置 `done`，此前保持 `live`。
- **冲突预检**：按“该资源是否已释放”判定，而非租约整体状态。

关窗与分释共用同一事务服务层，重复释放/已结束时都会被拒绝，不会双写打架。

## 本地冒烟（推荐）

```powershell
cd D:\Asolo11\claude-workspace\curtainclock\source
# 本机若无 3.11：py -V:Astral/CPython3.11.15 -m venv .venv
py -V:Astral/CPython3.11.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
$env:PYTHONPATH = "$PWD\backend"
Start-Process .\.venv\Scripts\uvicorn.exe -ArgumentList 'app.main:app','--host','127.0.0.1','--port','11100' -WorkingDirectory "$PWD\backend"
cd frontend
# 前端需 Node ≥18；不足时用 docker compose 起 web
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:6100 ：开一节课 → 同算力槽冲突 → 关窗释放。

## Docker

```powershell
docker compose up -d --build
```
