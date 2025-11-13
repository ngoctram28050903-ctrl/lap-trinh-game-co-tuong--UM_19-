from __future__ import annotatiogit config --global user.email "you@example.com"
  git config --global user.name "Your Name"  # dùng khi các class tham chiếu lẫn nhau như Game, Player
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
# ---------- CHALLENGE DECLINE ----------
# Xử lý khi người chơi từ chối lời mời thách đấu
if msg_type == "challenge_decline":

    # Lấy tên đối thủ (người đã gửi lời mời)
    opponent_name = msg.get("opponent_name")

    # Dùng khóa async để tránh xung đột dữ liệu khi nhiều người cùng thao tác
    async with lock:
        # Tìm kết nối WebSocket của người đã gửi lời mời (đối thủ)
        challenger_ws = find_ws_by_name(opponent_name)

        if challenger_ws:
            try:
                # Gửi thông báo hệ thống đến đối thủ: "người chơi hiện tại đã từ chối lời mời"
                await challenger_ws.send_text(json.dumps({
                    "type": "system",
                    "text": f"{player_name} đã từ chối lời mời."
                }, ensure_ascii=False))
            except:
                # Nếu có lỗi (ví dụ đối thủ đã thoát), thì bỏ qua
                pass

        # Xóa thông tin lời mời khỏi danh sách chờ
        pending_challenges.pop(player_name, None)          # Người chơi hiện tại không còn bị mời
        pending_challenge_targets.pop(opponent_name, None) # Đối thủ không còn chờ phản hồi

    # Kết thúc xử lý sự kiện này, tiếp tục lắng nghe các tin nhắn khác
    continue
# ---------- CHAT ----------
# Xử lý khi người chơi gửi tin nhắn chat
if msg_type == "chat_message":

    # Lấy nội dung tin nhắn người chơi gửi
    text = msg.get("text")

    # Nếu không có nội dung tin nhắn hoặc chưa xác định tên người chơi thì bỏ qua
    if not text or not player_name:
        continue

    # Tìm phòng mà người chơi này đang tham gia
    room_id = player_room_map.get(websocket)

    # Nếu người chơi không ở trong phòng nào hoặc phòng không tồn tại -> bỏ qua
    if not room_id or room_id not in rooms:
        continue

    # Tạo đối tượng tin nhắn chat (dạng JSON) để gửi cho các người chơi khác
    chat_msg = {
        "type": "new_chat_message",  # Kiểu thông điệp để client biết đây là tin nhắn mới
        "from": player_name,         # Người gửi tin nhắn
        "text": text                 # Nội dung tin nhắn
    }

    # Gửi tin nhắn đến tất cả người chơi trong cùng phòng (broadcast)
    await broadcast_to_room(room_id, chat_msg)

    # Sau khi xử lý xong, tiếp tục chờ tin nhắn khác
    continue
# ---------- MOVE ----------
# Xử lý khi người chơi thực hiện một nước đi
if msg_type == "move":

    # Lấy thông tin nước đi từ dữ liệu client gửi lên (VD: from -> to)
    move = msg.get("move")

    # Xác định phòng mà người chơi này đang ở
    room_id = player_room_map.get(websocket)

    # Nếu người chơi không ở trong phòng hoặc phòng không tồn tại -> báo lỗi
    if not room_id or room_id not in rooms:
        await websocket.send_text(json.dumps({"type":"error","reason":"Bạn không ở trong phòng."}, ensure_ascii=False))
        continue

    # Các cờ cảnh báo đặc biệt trong cờ tướng
    is_check_alert = False            # Chiếu tướng đối thủ
    is_self_check_alert = False       # Tự chiếu (nước đi sai)
    is_flying_general_alert = False   # Hai tướng đối mặt trực tiếp (lộ tướng)
    bot_color_to_move = None          # Dành cho chế độ chơi với Bot

    # Khóa để tránh xung đột khi nhiều người cùng gửi dữ liệu
    async with lock:
        # Lấy thông tin game trong phòng hiện tại
        game = rooms[room_id]

        # Lấy tên người chơi từ websocket
        player = game["players"].get(websocket)
        if not player:
            continue  # Nếu không tìm thấy, bỏ qua

        # Xác định màu của người chơi (đỏ / đen)
        player_color = game["player_colors"].get(player, "spectator")

        # Kiểm tra xem có phải lượt của người chơi không
        if player_color != game["turn"]:
            await websocket.send_text(json.dumps({"type":"error","reason":"Không phải lượt của bạn"}, ensure_ascii=False))
            continue

        # Nếu game đã kết thúc rồi (game_id không tồn tại) -> báo lỗi
        if game.get("game_id") is None:
            await websocket.send_text(json.dumps({"type":"error","reason":"Game đã kết thúc"}, ensure_ascii=False))
            continue

        # Kiểm tra nước đi hợp lệ hay không
        valid, reason = is_valid_move(game["state"]["board"], move, player_color)
        if not valid:
            # Nếu sai quy tắc, gửi lỗi lý do
            await websocket.send_text(json.dumps({"type":"error","reason":reason}, ensure_ascii=False))
            continue

        # Lưu tọa độ quân cờ di chuyển (from_x, from_y)
        fx, fy = move["from"]["x"], move["from"]["y"]
        piece = game["state"]["board"][fy][fx]  # Quân cờ được di chuyển

        # Thực hiện cập nhật bàn cờ với nước đi đó
        apply_move(game["state"], move)

        # Kiểm tra các tình huống đặc biệt sau khi di chuyển:
        if is_flying_general(game["state"]["board"]):
            is_flying_general_alert = True   # Hai tướng nhìn thẳng nhau (lộ tướng)
        if is_king_in_check(game["state"]["board"], player_color):
            is_self_check_alert = True       # Nước đi khiến tướng mình bị chiếu (sai luật)
        
        # Kiểm tra xem có chiếu tướng đối thủ không
        opponent_color = get_opponent_color(player_color)
        if is_king_in_check(game["state"]["board"], opponent_color):
            is_check_alert = True            # Thông báo chiếu tướng

        # Ghi lại nước đi vào lịch sử (database hoặc log)
        idx = game.get("move_count", 0) + 1
        add_move_record(game["game_id"], idx, fx, fy, move["to"]["x"], move["to"]["y"], piece)
        game["move_count"] = idx

        # Đổi lượt cho người chơi còn lại
        game["turn"] = opponent_color

        # Kiểm tra xem tướng của 2 bên còn tồn tại hay không
        red_king = find_king(game["state"]["board"], 'red')[0] != -1
        black_king = find_king(game["state"]["board"], 'black')[0] != -1

        # Nếu 1 trong 2 tướng bị ăn → game kết thúc
        if not red_king or not black_king:
            winner_color = 'red' if red_king and not black_king else 'black'
            reason_msg = "Tướng đã bị ăn"
            await send_game_over(room_id, winner_color, reason_msg)
            continue  # Dừng xử lý nước đi tiếp theo (vì ván đã kết thúc)

        # Xác định người đối thủ (tên player còn lại trong phòng)
        player_names = list(game["player_colors"].keys())
        opponent_name = player_names[1] if player_names[0] == player else player_names[0]

        # Nếu đối thủ là Bot và đến lượt Bot đi -> chuẩn bị cho Bot di chuyển
        if opponent_name == "Bot" and game.get("game_id") and game["turn"] == game["player_colors"]["Bot"]:
            bot_color_to_move = game["turn"]

    # Sau khi thoát khỏi lock, gửi lại trạng thái bàn cờ mới cho tất cả người trong phòng
    await send_state(room_id)

    # Hiển thị cảnh báo đặc biệt cho người chơi hiện tại (chỉ gửi riêng)
    if is_flying_general_alert:
        await websocket.send_text(json.dumps({"type":"system", "text": "⚠️ CẢNH BÁO: Lộ tướng!"}, ensure_ascii=False))
    if is_self_check_alert:
        await websocket.send_text(json.dumps({"type":"system", "text": "⚠️ CẢNH BÁO: Tướng của bạn đang bị chiếu!"}, ensure_ascii=False))
    
    # Nếu người chơi vừa chiếu tướng đối thủ → thông báo công khai cho cả phòng
    if is_check_alert:
        await broadcast_to_room(room_id, {"type":"system", "text": "CHIẾU TƯỚNG!"})
    
    # Nếu đến lượt Bot → tạo task cho Bot tự động đi nước tiếp theo
    if bot_color_to_move:
        asyncio.create_task(run_bot_move(room_id, bot_color_to_move))

    # Kết thúc xử lý nước đi, tiếp tục lắng nghe các tin nhắn khác
    continue
# ---------- LEAVE_GAME ----------
# Xử lý khi người chơi rời khỏi ván game (ấn nút "Thoát game" hoặc rời phòng)
if msg_type == "leave_game":

    # Lấy ID của phòng hiện tại mà người chơi đang tham gia
    room_id = player_room_map.get(websocket)

    # Nếu người chơi KHÔNG ở trong phòng nào hoặc phòng đã bị xóa:
    if not room_id or room_id not in rooms:
        async with lock:
            # Kiểm tra nếu người chơi chưa có trong sảnh (lobby)
            if websocket not in lobby and player_name:
                # Thêm người chơi trở lại vào sảnh chờ (lobby)
                lobby[websocket] = player_name
                # Gửi cập nhật danh sách sảnh cho tất cả người chơi
                await send_lobby_update()
        continue  # Bỏ qua các bước sau, quay lại vòng lặp chờ tin nhắn tiếp theo

    # Nếu người chơi đang ở trong phòng game:
    # -> Gọi hàm dọn dẹp (rời phòng, cập nhật trạng thái, giải phóng tài nguyên, v.v.)
    await cleanup_player(websocket)

    async with lock:
        # Sau khi rời game, thêm người chơi quay lại sảnh
        if player_name:
            lobby[websocket] = player_name

    # Gửi tin nhắn xác nhận cho người chơi: đã quay về sảnh
    await websocket.send_text(json.dumps({
        "type": "system",
        "text": "Đã quay về sảnh."
    }, ensure_ascii=False))

    # Gửi cập nhật danh sách người chơi trong sảnh (để hiển thị cho tất cả client)
    await send_lobby_update()

    # Tiếp tục vòng lặp (lắng nghe tin nhắn tiếp theo)
    continue
# ----------------- XỬ LÝ NGẮT KẾT NỐI -----------------
except WebSocketDisconnect:
    # Khi người chơi bị ngắt kết nối (đóng tab, mất mạng, thoát game,...)
    print(f"[WS] Disconnect: {player_name}")   # In thông báo ra console để theo dõi
    await cleanup_player(websocket)            # Gọi hàm dọn dẹp dữ liệu người chơi (xóa khỏi phòng, cập nhật sảnh,...)
