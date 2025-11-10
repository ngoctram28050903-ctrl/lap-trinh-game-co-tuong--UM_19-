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
            # xử lý khi có người chơi gửi tin nhắn kiểu "challenge".
            if msg_type == "challenge": #người chơi gửi yêu cầu thách đấu
                    target_name = msg.get("target_player") # Lấy tên người chơi bị thách đấu từ dữ liệu tin nhắn
                    if not player_name: continue
            # Nếu tên người chơi đang gửi yêu cầu không tồn tại hoặc rỗng, thì bỏ qua vòng lặp này
                    if target_name == player_name:
            # Nếu người chơi đang gửi yêu cầu tự thách đấu mình
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "reason": "Bạn không thể tự thách đấu mình."
                    }, ensure_ascii=False))
            # Gửi lại thông báo lỗi qua websocket tự thách đấu bản thân
                continue
            # Bỏ qua phần xử lý tiếp theo, quay lại chờ tin nhắn mớid
            
            # ----- CHALLENGE với bot -----
if target_name == "Bot":                           # người chơi chọn thách đấu với "Bot"
    async with lock:                               # tránh các clients khác sửa dữ liệu cùng lúc
        if websocket in lobby: del lobby[websocket] # Xóa người chơi khỏi danh sách chờ (lobby)
        room_id = str(uuid.uuid4())                # Tạo ID phòng ngẫu nhiên duy nhất
        player_room_map[websocket] = room_id        # Ghi nhớ người chơi này đang ở phòng nào

        human_player_name = player_name             # Lưu tên người chơi thật
        bot_player_name = "Bot"                     # Đặt tên cho đối thủ là "Bot"

        game_id = create_game_record(room_id, human_player_name, bot_player_name)
        # Tạo bản ghi game mới trong database (hoặc log) để lưu lại thông tin trận đấu

        rooms[room_id] = {                          # Khởi tạo thông tin phòng chơi
            "players": {websocket: human_player_name},     # Liên kết socket người chơi với tên
            "player_colors": {human_player_name: 'red', bot_player_name: 'black'}, # Người chơi thật cầm đỏ, bot cầm đen
            "turn": "red",   # Lượt đầu tiên là của người chơi đỏ
            "state": init_board(),      # Khởi tạo bàn cờ ban đầu
            "game_id": game_id,    # Gắn ID trận vào
            "move_count": 0,      # Đếm số lượt đi
            "clocks": {"red": 300, "black": 300},    # Mỗi bên có 300 giây (5 phút)
            "timer_task": None,       # Sẽ khởi tạo task đếm thời gian sau
            "rematch_offered_by": None    # Chưa ai đề nghị chơi lại
        }

        rooms[room_id]["timer_task"] = asyncio.create_task(timer_loop(room_id))
        # Bắt đầu chạy task đếm giờ song song cho phòng này

        await websocket.send_text(json.dumps({
            "type": "game_start",   # Gửi thông báo cho client biết trận đấu bắt đầu
            "room_id": room_id,           # ID phòng
            "color": "red",       # Màu quân của người chơi
            "opponent": bot_player_name      # Đối thủ là Bot
        }, ensure_ascii=False))

        print(f"[MATCH START] room={room_id} {human_player_name}(red) vs {bot_player_name}(black)")
        # In ra log server để theo dõi

        await send_state(room_id)                   # Gửi trạng thái bàn cờ ban đầu đến client
    await send_lobby_update()                       # Cập nhật lại danh sách lobby cho những người khác
    continue                                        # Quay lại vòng lặp chờ sự kiện tiếp theo
