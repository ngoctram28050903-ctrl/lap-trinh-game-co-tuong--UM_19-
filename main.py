from __future__ import annotations  # dùng khi các class tham chiếu lẫn nhau như Game, Player
import asyncio                     # Dùng để xử lý các tác vụ bất đồng bộ
import copy                        # Dùng để sao chép
import json                        # gửi/nhận dữ liệu qua WebSocket giữa client và server
import random                      # Sinh số ngẫu nhiên 
import sqlite3                     #  SQLite (lưu thông tin người chơi, lịch sử trận đấu)
import time                        # Dùng để đo thời gian hoặc tạo timestamp
import traceback                   # In ra lỗi chi tiết (stack trace) khi có lỗi trong quá trình chạy server — giúp debug dễ hơn
import uuid                        # Tạo chuỗi ID duy nhất 
from dataclasses import dataclass, field  # Dùng để tạo class dữ liệu GameState, Player, Room
from pathlib import Path            # Làm việc với đường dẫn file
from typing import Dict, List, Optional, Tuple  # Hỗ trợ khai báo kiểu dữ liệu rõ ràng cho biến và hàm (để code dễ đọc, tránh lỗi)
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # FastAPI là framework chính; WebSocket dùng để giao tiếp thời gian thực giữa người chơi và server
from fastapi.responses import FileResponse, JSONResponse     # Gửi file HTML hoặc JSON về client (trang chơi cờ hoặc dữ liệu API)
from fastapi.staticfiles import StaticFiles                   # Dùng để phục vụ file tĩnh (CSS, ảnh, JS) cho giao diện web game







# xử lý người chơi khi kết nối WebSocket và vào sảnh
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    player_name: Optional[str] = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await safe_send(websocket, {"type": "error", "reason": "invalid_json"})
                continue

            mtype = msg.get("type")

            # ---- LOBBY ----
            if mtype == "join_lobby":
                player_name = msg.get("player") or ("P" + str(int(time.time()) % 1000))
                async with lock:
                    if find_ws_by_name(player_name):
                        player_name = player_name + str(int(time.time()) % 100)
                    lobby[websocket] = player_name
                print(f"[LOBBY] {player_name} joined.")
                await safe_send(websocket, {"type": "system", "text": f"Chào mừng {player_name} đến sảnh."})
                await send_lobby_update()
                continue
