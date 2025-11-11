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
# 'async with lock' đảm bảo chỉ một người xử lý việc mời tại một thời điểm.
    
    async with lock:
    # Tìm kiếm kết nối (websocket) của người được mời.
    target_ws = find_player_in_lobby(target_name)
    
    # Nếu không tìm thấy người được mời:
    if not target_ws:
        # Báo lỗi cho người mời và dừng xử lý.
        await websocket.send_text(json.dumps({"type":"error","reason":f"Không tìm thấy người chơi '{target_name}' trong sảnh."}, ensure_ascii=False))
        continue

    # Ghi lại trạng thái đang chờ: Ai mời ai?
    pending_challenges[target_name] = player_name
    pending_challenge_targets[player_name] = target_name
    
    try:
        # Gửi thông báo mời đến cho người được mời (target_ws).
        await target_ws.send_text(json.dumps({"type":"challenge_received", "from_player": player_name}, ensure_ascii=False))
    except Exception as e:
        # Nếu gửi bị lỗi (ví dụ: người được mời bị ngắt kết nối):
        print(f"[CHALLENGE] Failed to send to {target_name}: {e}")
        # Báo lỗi cho người mời.
        await websocket.send_text(json.dumps({"type":"error","reason":"Không thể gửi lời mời, đối thủ không phản hồi."}, ensure_ascii=False))
        
        # Hủy trạng thái chờ vì gửi lỗi.
        pending_challenges.pop(target_name, None)
        pending_challenge_targets.pop(player_name, None)
        continue # Dừng lại.

    # Nếu gửi mời thành công:
    print(f"[CHALLENGE] {player_name} -> {target_name}")
    # Báo cho người mời (websocket) biết là đã gửi xong.
    await websocket.send_text(json.dumps({"type":"system","text":f"Đã gửi lời mời đến {target_name}. Đang chờ đối thủ chấp nhận..."}))
    continue # Hoàn tất.
# Nếu tin nhắn nhận được là "chấp nhận lời mời".
if msg_type == "challenge_accept":
    # Lấy tên của người đã gửi lời mời (opponent).
    opponent_name = msg.get("opponent_name")
    # 'player_name' là tên của người chấp nhận (chính là websocket hiện tại).
    if not player_name: continue # Kiểm tra an toàn, nếu người chấp nhận không có tên thì bỏ qua.

    # Sử dụng 'lock' để đảm bảo việc tạo phòng game diễn ra an toàn,
    # tránh trường hợp 2 người chấp nhận cùng lúc hoặc lỗi dữ liệu.
    async with lock:
        # Tìm kết nối (websocket) của người đã mời.
        challenger_ws = find_ws_by_name(opponent_name)
        
        # [Phần dự phòng]: Nếu tìm không thấy VÀ trong danh sách chờ
        # đúng là 'opponent_name' đã mời 'player_name'.
        if not challenger_ws and pending_challenges.get(player_name) == opponent_name:
            # Thử tìm lại người đó trong sảnh (lobby).
            challenger_ws = find_player_in_lobby(opponent_name)

        # Nếu tìm đủ mọi cách mà vẫn không thấy người mời (có thể họ đã thoát):
        if not challenger_ws:
            # Báo lỗi về cho người chấp nhận (websocket).
            await websocket.send_text(json.dumps({"type":"error","reason":f"'{opponent_name}' không còn ở sảnh hoặc phiên đã lỗi."}, ensure_ascii=False))
            continue # Dừng xử lý.

        # --- Nếu tìm thấy người mời, bắt đầu tạo trận đấu ---

        # Dọn dẹp trạng thái "chờ mời" giữa 2 người này.
        # Xóa lời mời mà 'opponent_name' gửi cho 'player_name'.
        pending_challenges.pop(player_name, None)
        pending_challenge_targets.pop(opponent_name, None)
        # Xóa luôn nếu 'player_name' cũng đang mời 'opponent_name' (tránh xung đột).
        pending_challenges.pop(opponent_name, None)
        pending_challenge_targets.pop(player_name, None)

        # Xóa cả hai người chơi khỏi sảnh (lobby) vì họ sắp vào game.
        if websocket in lobby: del lobby[websocket]
        if challenger_ws in lobby: del lobby[challenger_ws]

        # Tạo một ID phòng game duy nhất.
        room_id = str(uuid.uuid4())
        
        # Lưu lại: 2 kết nối (websocket) này giờ thuộc về phòng 'room_id'.
        player_room_map[websocket] = room_id
        player_room_map[challenger_ws] = room_id

        # Gán tên cho rõ ràng.
        challenger_name = lobby.get(challenger_ws, opponent_name) # Tên người mời
        acceptor_name = player_name # Tên người chấp nhận
        
        # Tạo bản ghi game trong CSDL (Database) và lấy ID.
        game_id = create_game_record(room_id, challenger_name, acceptor_name)

        # Tạo đối tượng (dictionary) lưu trữ toàn bộ trạng thái của phòng game.
        rooms[room_id] = {
            "players": {websocket: acceptor_name, challenger_ws: challenger_name}, # Lưu ai điều khiển kết nối nào.
            "player_colors": {challenger_name: 'red', acceptor_name: 'black'}, # Người mời (challenger) luôn là đỏ (đi trước).
            "turn": "red", # Lượt đi đầu tiên là đỏ.
            "state": init_board(), # Trạng thái bàn cờ ban đầu.
            "game_id": game_id, # ID từ CSDL.
            "move_count": 0, # Số nước đã đi.
            "clocks": {"red": 300, "black": 300}, # Thời gian (ví dụ: 300 giây).
            "timer_task": None, # Biến để giữ "task" đếm giờ.
            "rematch_offered_by": None # Dùng cho việc mời tái đấu sau này.
        }
        
        # Tạo và khởi chạy một 'task' (luồng) riêng để đếm giờ cho phòng này.
        rooms[room_id]["timer_task"] = asyncio.create_task(timer_loop(room_id))

        # Gửi tin nhắn "game_start" cho người chấp nhận (websocket): họ là màu 'black'.
        await websocket.send_text(json.dumps({"type": "game_start", "room_id": room_id, "color": "black", "opponent": challenger_name}, ensure_ascii=False))
        # Gửi tin nhắn "game_start" cho người mời (challenger_ws): họ là màu 'red'.
        await challenger_ws.send_text(json.dumps({"type": "game_start", "room_id": room_id, "color": "red", "opponent": acceptor_name}, ensure_ascii=False))
        
        # In log trên server.
        print(f"[MATCH START] room={room_id} {challenger_name}(red) vs {acceptor_name}(black)")
        
        # Gửi trạng thái bàn cờ ban đầu cho cả 2 người.
        await send_state(room_id)
        
    # [Nằm ngoài 'lock'] Cập nhật lại danh sách sảnh cho tất cả người chơi khác
    # (vì 2 người vừa vào game, không còn ở sảnh nữa).
    await send_lobby_update()
    continue # Kết thúc xử lý tin nhắn này.