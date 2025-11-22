
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import json, asyncio, sqlite3, time, uuid, copy, traceback, random

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

DB_PATH = "games.db"

# ------------------ Database init ------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS games (
        id TEXT PRIMARY KEY,
        room TEXT,
        player_red TEXT,
        player_black TEXT,
        start_ts INTEGER,
        end_ts INTEGER,
        winner TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS moves (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id TEXT,
        move_index INTEGER,
        from_x INTEGER, from_y INTEGER,
        to_x INTEGER, to_y INTEGER,
        piece TEXT,
        ts INTEGER
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ------------------ In-memory structures ------------------
lobby = {}                # { websocket: player_name }
rooms = {}                # { room_id: {...} }
player_room_map = {}      # { websocket: room_id }
pending_challenges = {}   # { target_name: challenger_name }
pending_challenge_targets = {}  # { challenger_name: target_name }
lock = asyncio.Lock()

# ------------------ Game logic helpers ------------------
def init_board():
    board = [["" for _ in range(9)] for _ in range(10)]
    board[0] = ['車','馬','象','士','將','士','象','馬','車']
    board[2] = ['', '砲', '', '', '', '', '', '砲', '']
    board[3] = ['卒', '', '卒', '', '卒', '', '卒', '', '卒']
    board[9] = ['俥', '傌', '相', '仕', '帥', '仕', '相', '傌', '俥']
    board[7] = ['', '炮', '', '', '', '', '', '炮', '']
    board[6] = ['兵', '', '兵', '', '兵', '', '兵', '', '兵']
    return {"board": board}

def get_color(piece: str) -> str:
    if piece in ['俥','傌','相','仕','帥','炮','兵']: return 'red'
    if piece in ['車','馬','象','士','將','砲','卒']: return 'black'
    return 'none'

def get_opponent_color(color: str) -> str:
    return 'black' if color == 'red' else 'red'

def is_in_palace(x: int, y: int, color: str) -> bool:
    if not (3 <= x <= 5): return False
    if color == 'red' and (7 <= y <= 9): return True
    if color == 'black' and (0 <= y <= 2): return True
    return False

def find_king(board, color: str):
    king_piece = '帥' if color == 'red' else '將'
    for y in range(10):
        for x in range(9):
            if board[y][x] == king_piece:
                return (x, y)
    return (-1, -1)

def count_blockers(board, fx, fy, tx, ty) -> int:
    count = 0
    if fx == tx:
        step = 1 if ty > fy else -1
        for y in range(fy + step, ty, step):
            if board[y][fx] != "": count += 1
    elif fy == ty:
        step = 1 if tx > fx else -1
        for x in range(fx + step, tx, step):
            if board[fy][x] != "": count += 1
    return count

def _is_legal_chariot(board, fx, fy, tx, ty):
    return (fx == tx or fy == ty) and count_blockers(board, fx, fy, tx, ty) == 0

def _is_legal_horse(board, fx, fy, tx, ty):
    dx, dy = abs(tx - fx), abs(ty - fy)
    if not ((dx == 1 and dy == 2) or (dx == 2 and dy == 1)): return False
    if dx == 2:
        if board[fy][(fx + tx)//2] != "": return False
    else:
        if board[(fy + ty)//2][fx] != "": return False
    return True

def _is_legal_elephant(board, fx, fy, tx, ty, color):
    if not (abs(tx - fx) == 2 and abs(ty - fy) == 2): return False
    if (color == 'red' and ty < 5) or (color == 'black' and ty > 4): return False
    if board[(fy + ty)//2][(fx + tx)//2] != "": return False
    return True

def _is_legal_advisor(board, fx, fy, tx, ty, color):
    return abs(tx - fx) == 1 and abs(ty - fy) == 1 and is_in_palace(tx, ty, color)

def _is_legal_general(board, fx, fy, tx, ty, color):
    return (abs(tx - fx) + abs(ty - fy) == 1) and is_in_palace(tx, ty, color)

def _is_legal_cannon(board, fx, fy, tx, ty, target_piece):
    if not (fx == tx or fy == ty): return False
    blockers = count_blockers(board, fx, fy, tx, ty)
    if target_piece == "":
        return blockers == 0
    else:
        return blockers == 1

def _is_legal_soldier(board, fx, fy, tx, ty, color):
    dx, dy = abs(tx - fx), abs(ty - fy)
    if not (dx + dy == 1): return False
    if color == 'red':
        if ty > fy: return False
        if fy >= 5 and tx != fx: return False
    else:
        if ty < fy: return False
        if fy <= 4 and tx != fx: return False
    return True

def is_legal_move_for_piece(board, fx, fy, tx, ty):
    piece = board[fy][fx]
    color = get_color(piece)
    target_piece = board[ty][tx]
    if piece in ['俥','車']: return _is_legal_chariot(board, fx, fy, tx, ty)
    if piece in ['傌','馬']: return _is_legal_horse(board, fx, fy, tx, ty)
    if piece in ['相','象']: return _is_legal_elephant(board, fx, fy, tx, ty, color)
    if piece in ['仕','士']: return _is_legal_advisor(board, fx, fy, tx, ty, color)
    if piece in ['帥','將']: return _is_legal_general(board, fx, fy, tx, ty, color)
    if piece in ['炮','砲']: return _is_legal_cannon(board, fx, fy, tx, ty, target_piece)
    if piece in ['兵','卒']: return _is_legal_soldier(board, fx, fy, tx, ty, color)
    return False

def is_square_attacked(board, x, y, attacker_color):
    for fy in range(10):
        for fx in range(9):
            piece = board[fy][fx]
            if get_color(piece) == attacker_color:
                if is_legal_move_for_piece(board, fx, fy, x, y):
                    return True
    return False

def is_king_in_check(board, color):
    kx, ky = find_king(board, color)
    if kx == -1: return False
    return is_square_attacked(board, kx, ky, get_opponent_color(color))

def is_flying_general(board):
    rx, ry = find_king(board, 'red')
    bx, by = find_king(board, 'black')
    if rx == -1 or bx == -1: return False
    if rx != bx: return False
    if count_blockers(board, rx, ry, bx, by) == 0: return True
    return False

def apply_move(state, move):
    fx, fy = move["from"]["x"], move["from"]["y"]
    tx, ty = move["to"]["x"], move["to"]["y"]
    piece = state["board"][fy][fx]
    state["board"][fy][fx] = ""
    state["board"][ty][tx] = piece

def is_valid_move(board, move, player_color):
    fx, fy = move["from"]["x"], move["from"]["y"]
    tx, ty = move["to"]["x"], move["to"]["y"]

    if not (0 <= fx < 9 and 0 <= fy < 10 and 0 <= tx < 9 and 0 <= ty < 10):
        return False, "Đi ra ngoài bàn cờ"
    piece = board[fy][fx]
    if piece == "": return False, "Ô trống, không có quân"
    if get_color(piece) != player_color: return False, "Không phải quân của bạn"
    target_piece = board[ty][tx]
    if target_piece != "" and get_color(target_piece) == player_color:
        return False, "Không thể ăn quân mình"
    if not is_legal_move_for_piece(board, fx, fy, tx, ty):
        return False, "Nước đi không hợp lệ"
    return True, ""

# ------------------ DB helpers ------------------
def create_game_record(room_id, player_red, player_black):
    gid = str(uuid.uuid4())
    ts = int(time.time())
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO games(id, room, player_red, player_black, start_ts) VALUES (?,?,?,?,?)",
                  (gid, room_id, player_red, player_black, ts))
        conn.commit()
        conn.close()
        return gid
    except Exception as e:
        print(f"[DB] Error create_game_record: {e}")
        return None

def add_move_record(game_id, idx, fx, fy, tx, ty, piece):
    ts = int(time.time())
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO moves(game_id, move_index, from_x, from_y, to_x, to_y, piece, ts) VALUES (?,?,?,?,?,?,?,?)",
                  (game_id, idx, fx, fy, tx, ty, piece, ts))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] Error add_move_record: {e}")

def finish_game_record(game_id, winner):
    if not game_id: return
    ts = int(time.time())
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE games SET end_ts=?, winner=? WHERE id=?", (ts, winner, game_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] Error finish_game_record: {e}")

# ------------------ Core send/broadcast helpers ------------------
async def broadcast_to_room(room_id: str, message: dict, exclude_ws: WebSocket = None):
    if room_id not in rooms: return
    msg = json.dumps(message, ensure_ascii=False)
    tasks = []
    for ws in list(rooms[room_id]["players"].keys()):
        if ws == exclude_ws: continue
        try:
            tasks.append(ws.send_text(msg))
        except Exception:
            pass
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def broadcast_to_lobby(message: dict, exclude_ws: WebSocket = None):
    msg = json.dumps(message, ensure_ascii=False)
    tasks = []
    for ws in list(lobby.keys()):
        if ws == exclude_ws: continue
        try:
            tasks.append(ws.send_text(msg))
        except Exception:
            pass
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def send_lobby_update():
    players = list(lobby.values())
    dead_clients = []
    for ws, name in list(lobby.items()):
        try:
            await ws.send_text(json.dumps({"type": "lobby_update", "players": players}, ensure_ascii=False))
        except Exception as e:
            print(f"[WARN] Không gửi được cho {name}: {e}")
            dead_clients.append(ws)
    for ws in dead_clients:
        lobby.pop(ws, None)
    print(f"[LOBBY] Hiện có {len(players)} người: {', '.join(players) if players else 'Sảnh trống.'}")

async def send_state(room_id: str):
    if room_id not in rooms: return
    game = rooms[room_id]

    board = game["state"]["board"]
    check_state = {
        "red": is_king_in_check(board, 'red'),
        "black": is_king_in_check(board, 'black')
    }

    state_to_send = {
        "type": "state",
        "turn": game["turn"],
        "state": game["state"],
        "colors": game["player_colors"],
        "clocks": game.get("clocks", {"red": 300, "black": 300}),
        "check_state": check_state
    }
    await broadcast_to_room(room_id, state_to_send)

# === HÀM ĐÃ THAY ĐỔI ===
async def send_game_over(room_id, winner_color, reason):
    if room_id not in rooms: return
    game = rooms[room_id]
    if game.get("timer_task"):
        try:
            game["timer_task"].cancel()
        except:
            pass
        game["timer_task"] = None

    # Tìm tên người chiến thắng từ màu (red/black)
    winner_name = None
    for name, color in game["player_colors"].items():
        if color == winner_color:
            winner_name = name
            break
    
    # Xử lý trường hợp Bot thắng
    if winner_name is None and "Bot" in game["player_colors"]:
         if game["player_colors"]["Bot"] == winner_color:
             winner_name = "Bot"

    # Nếu vẫn không tìm thấy (hiếm khi), dùng tên màu
    if winner_name is None: 
        winner_name = winner_color.capitalize() 

    if game.get("game_id"):
        # Lưu tên người thắng vào DB, không phải màu
        finish_game_record(game["game_id"], winner_name)

    game["game_id"] = None
    game["rematch_offered_by"] = None

    # Gửi cả tên và màu của người thắng
    msg = {
        "type": "game_over", 
        "winner_color": winner_color, 
        "winner_name": winner_name, 
        "reason": reason
    }
    await broadcast_to_room(room_id, msg)
# === KẾT THÚC THAY ĐỔI ===

# ------------------ Timer loop ------------------
async def timer_loop(room_id: str):
    print(f"[TIMER] Starting for room {room_id}")
    try:
        while True:
            await asyncio.sleep(1)
            async with lock:
                if room_id not in rooms:
                    break
                game = rooms[room_id]
                if game.get("game_id") is None:
                    continue
                
                player_names = list(game["player_colors"].keys())
                is_bot_game = "Bot" in player_names
                
                turn = game["turn"]

                if is_bot_game and game["player_colors"].get("Bot") == turn:
                    continue 

                game["clocks"][turn] -= 1
                await broadcast_to_room(room_id, {"type": "clock_update", "clocks": game["clocks"]})
                
                if game["clocks"][turn] <= 0:
                    winner_color = get_opponent_color(turn) # Đây là 'red' hoặc 'black'
                    reason = f"{turn.capitalize()} hết giờ"
                    print(f"[TIMER] Room {room_id} - {turn} ran out. Winner: {winner_color}")
                    await send_game_over(room_id, winner_color, reason) # Gửi màu
                    break
    except asyncio.CancelledError:
        print(f"[TIMER] Cancelled for room {room_id}")
    except Exception as e:
        print(f"[TIMER] Error for room {room_id}: {e}")
        traceback.print_exc()
        async with lock:
            if room_id in rooms:
                rooms[room_id]["timer_task"] = None

# ------------------ Bot logic ------------------
async def run_bot_move(room_id: str, bot_color: str):
    await asyncio.sleep(1.0) 
    try:
        async with lock:
            if room_id not in rooms or rooms[room_id].get("game_id") is None:
                return 
            game = rooms[room_id]
            if game["turn"] != bot_color:
                return 

            board = game["state"]["board"]
            all_moves = []

            for y in range(10):
                for x in range(9):
                    piece = board[y][x]
                    if get_color(piece) == bot_color:
                        for ty in range(10):
                            for tx in range(9):
                                move = {"from": {"x": x, "y": y}, "to": {"x": tx, "y": ty}}
                                
                                valid_base, _ = is_valid_move(board, move, bot_color)
                                if not valid_base:
                                    continue
                                
                                temp_board = copy.deepcopy(board)
                                temp_board[ty][tx] = temp_board[y][x]
                                temp_board[y][x] = "" # Lỗi logic bot ở đây, phải là temp_board[y][fx]
                                # Sửa lại:
                                # temp_board[ty][tx] = temp_board[y][x]
                                # temp_board[y][x] = "" # fx không tồn tại, phải là x
                                
                                # Kiểm tra lại logic bot
                                # `temp_board[y][fx] = ""` -> fx không được định nghĩa
                                # Phải là: temp_board[y][x] = ""
                                
                                # Sửa logic bot
                                temp_board_fix = copy.deepcopy(board)
                                temp_board_fix[ty][tx] = temp_board_fix[y][x]
                                temp_board_fix[y][x] = "" # Đã sửa fx -> x
                                
                                if is_flying_general(temp_board_fix) or is_king_in_check(temp_board_fix, bot_color):
                                    continue 

                                all_moves.append(move)
            
            if not all_moves:
                winner_color = get_opponent_color(bot_color) # Đây là 'red' hoặc 'black'
                reason = "Chiếu bí! Bot không còn nước đi."
                await send_game_over(room_id, winner_color, reason) # Gửi màu
                return

            chosen_move = random.choice(all_moves)
            
            fx, fy = chosen_move["from"]["x"], chosen_move["from"]["y"]
            tx, ty = chosen_move["to"]["x"], chosen_move["to"]["y"]
            piece = board[fy][fx]

            apply_move(game["state"], chosen_move)

            opponent_color = get_opponent_color(bot_color)
            is_check_alert = is_king_in_check(game["state"]["board"], opponent_color)

            idx = game.get("move_count", 0) + 1
            add_move_record(game["game_id"], idx, fx, fy, tx, ty, piece)
            game["move_count"] = idx
            game["turn"] = opponent_color

            red_king = find_king(game["state"]["board"], 'red')[0] != -1
            black_king = find_king(game["state"]["board"], 'black')[0] != -1

            if not red_king or not black_king:
                winner_color = 'red' if red_king and not black_king else 'black'
                reason_msg = "Tướng đã bị ăn"
                await send_game_over(room_id, winner_color, reason_msg) # Gửi màu
                return

        await send_state(room_id)
        if is_check_alert:
            await broadcast_to_room(room_id, {"type":"system", "text": "BOT CHIẾU TƯỚNG!"})

    except Exception as e:
        print(f"[BOT] Error in run_bot_move: {e}")
        traceback.print_exc()


# ------------------ Cleanup on disconnect or leave ------------------
async def cleanup_player(ws: WebSocket):
    async with lock:
        if ws in lobby:
            name = lobby.pop(ws)
            print(f"[CLEANUP] Lobby player '{name}' disconnected/left.")
            await send_lobby_update()
            pending_challenges.pop(name, None)
            pending_challenge_targets.pop(name, None)
            return

        if ws in player_room_map:
            room_id = player_room_map.pop(ws)
            if room_id in rooms:
                game = rooms[room_id]
                name = game["players"].pop(ws, None)
                if name:
                    color = game["player_colors"].get(name)
                    if color in ("red", "black") and game.get("game_id"):
                        winner_color = get_opponent_color(color) # Đây là 'red' hoặc 'black'
                        
                        reason = f"{name} ({color}) đã ngắt kết nối"
                        print(f"[CLEANUP] Player {name} disconnected in room {room_id}. Winner: {winner_color}")
                        await send_game_over(room_id, winner_color, reason) # Gửi màu
                    else:
                        await broadcast_to_room(room_id, {"type":"system","text": f"{name} đã rời phòng."}, exclude_ws=ws)

                if not game["players"]:
                    print(f"[CLEANUP] Room {room_id} is empty. Deleting.")
                    if game.get("timer_task"):
                        try: game["timer_task"].cancel()
                        except: pass
                    del rooms[room_id]

            pending_challenges.pop(name, None)
            pending_challenge_targets.pop(name, None)

# ------------------ Utilities to find sockets by name ------------------
def find_player_in_lobby(player_name: str):
    for ws, name in lobby.items():
        if name == player_name:
            return ws
    return None

def find_ws_by_name(player_name: str):
    ws = find_player_in_lobby(player_name)
    if ws: return ws
    for room in rooms.values():
        for w, n in room["players"].items():
            if n == player_name:
                return w
    return None

def get_opponent_ws(room_id: str, self_ws: WebSocket):
    if room_id not in rooms: return None
    for ws in rooms[room_id]["players"]:
        if ws != self_ws:
            return ws
    return None

# ------------------ HTTP routes ------------------
@app.get("/")
async def index():
    return FileResponse("static/client_web.html")

@app.get("/leaderboard")
async def leaderboard():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT winner, COUNT(*) FROM games WHERE winner IS NOT NULL AND winner != 'Bot' GROUP BY winner ORDER BY COUNT(*) DESC")
        rows = c.fetchall()
        conn.close()
        return JSONResponse([{"player": r[0], "wins": r[1]} for r in rows])
    except Exception as e:
        print(f"[DB] leaderboard error: {e}")
        return JSONResponse([])

# API xử lý kết nối WebSocket chính
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # 1. BẮT TAY KẾT NỐI
    # Chấp nhận yêu cầu kết nối từ Client (trình duyệt)
    await websocket.accept()
    player_name = None # Biến lưu tên người chơi của phiên kết nối này

    try:
        # Vòng lặp vô hạn: Server luôn lắng nghe tin nhắn từ Client gửi lên
        while True:
            # Chờ nhận dữ liệu dạng text (JSON string)
            data = await websocket.receive_text()
            
            # Cố gắng giải mã JSON
            try:
                msg = json.loads(data)
            except Exception:
                # Nếu dữ liệu rác, không phải JSON chuẩn -> Báo lỗi và bỏ qua
                await websocket.send_text(json.dumps({"type":"error","reason":"invalid_json"}))
                continue

            # Lấy loại hành động (ví dụ: "move", "join_lobby", "challenge"...)
            msg_type = msg.get("type")

            # ==========================================
            # 1. XỬ LÝ VÀO SẢNH (JOIN LOBBY)
            # ==========================================
            if msg_type == "join_lobby":
                # Lấy tên người chơi gửi lên, hoặc tự sinh tên "P..." nếu rỗng
                player_name = msg.get("player") or ("P"+str(int(time.time())%1000))
                
                # KHÓA (LOCK): Đảm bảo an toàn khi nhiều người cùng vào sảnh 1 lúc
                async with lock:
                    # Kiểm tra xem tên có bị trùng không
                    existing_ws = find_ws_by_name(player_name)
                    if existing_ws:
                        # Nếu trùng, thêm đuôi số vào sau tên
                        player_name = player_name + str(int(time.time())%100)
                    # Lưu websocket vào danh sách lobby toàn cục
                    lobby[websocket] = player_name
                
                print(f"[LOBBY] {player_name} joined lobby.")
                # Gửi thông báo riêng cho người chơi: "Chào mừng..."
                await websocket.send_text(json.dumps({"type":"system","text":f"Chào mừng {player_name} đến sảnh."}, ensure_ascii=False))
                # Gửi danh sách tất cả người chơi trong sảnh cho MỌI NGƯỜI cập nhật giao diện
                await send_lobby_update()
                continue

            # ==========================================
            # 2. XỬ LÝ THÁCH ĐẤU (CHALLENGE)
            # ==========================================
            if msg_type == "challenge":
                target_name = msg.get("target_player") # Tên người bị thách đấu
                if not player_name: continue # Chưa có tên thì không được thách đấu
                
                # Không cho phép tự thách đấu chính mình
                if target_name == player_name:
                    await websocket.send_text(json.dumps({"type":"error","reason":"Bạn không thể tự thách đấu mình."}, ensure_ascii=False))
                    continue

                # ----- TRƯỜNG HỢP 2.1: ĐÁNH VỚI BOT (MÁY) -----
                if target_name == "Bot":
                    async with lock:
                        # Xóa người chơi khỏi sảnh (để không ai mời được nữa)
                        if websocket in lobby: del lobby[websocket]
                        
                        # Tạo ID phòng mới (UUID ngẫu nhiên)
                        room_id = str(uuid.uuid4())
                        player_room_map[websocket] = room_id # Gán người chơi vào phòng này
                        
                        human_player_name = player_name
                        bot_player_name = "Bot"
                        # Tạo bản ghi game trong Database
                        game_id = create_game_record(room_id, human_player_name, bot_player_name)
                        
                        # Khởi tạo dữ liệu phòng game
                        rooms[room_id] = {
                            "players": {websocket: human_player_name}, 
                            "player_colors": {human_player_name: 'red', bot_player_name: 'black'}, # Người là Đỏ, Bot là Đen
                            "turn": "red", # Đỏ đi trước
                            "state": init_board(), # Bàn cờ ban đầu
                            "game_id": game_id,
                            "move_count": 0,
                            "clocks": {"red": 300, "black": 300}, # 5 phút mỗi bên
                            "timer_task": None,
                            "rematch_offered_by": None
                        }
                        # Bắt đầu luồng đếm ngược thời gian
                        rooms[room_id]["timer_task"] = asyncio.create_task(timer_loop(room_id))
                        
                        # Gửi tin nhắn "Bắt đầu game" cho client
                        await websocket.send_text(json.dumps({"type": "game_start", "room_id": room_id, "color": "red", "opponent": bot_player_name}, ensure_ascii=False))
                        print(f"[MATCH START] room={room_id} {human_player_name}(red) vs {bot_player_name}(black)")
                        
                        # Gửi trạng thái bàn cờ để client vẽ hình
                        await send_state(room_id)
                    
                    # Cập nhật lại sảnh (để người khác thấy người này biến mất khỏi sảnh)
                    await send_lobby_update()
                    continue

                # ----- TRƯỜNG HỢP 2.2: ĐÁNH VỚI NGƯỜI KHÁC -----
                async with lock:
                    target_ws = find_player_in_lobby(target_name) # Tìm websocket của đối thủ
                    if not target_ws:
                        await websocket.send_text(json.dumps({"type":"error","reason":f"Không tìm thấy người chơi '{target_name}' trong sảnh."}, ensure_ascii=False))
                        continue
                    
                    # Lưu lại lời mời vào danh sách chờ
                    pending_challenges[target_name] = player_name
                    pending_challenge_targets[player_name] = target_name
                    
                    try:
                        # Chuyển lời mời đến máy của đối thủ
                        await target_ws.send_text(json.dumps({"type":"challenge_received", "from_player": player_name}, ensure_ascii=False))
                    except Exception as e:
                        # Xử lý nếu đối thủ rớt mạng
                        print(f"[CHALLENGE] Failed to send to {target_name}: {e}")
                        await websocket.send_text(json.dumps({"type":"error","reason":"Không thể gửi lời mời, đối thủ không phản hồi."}, ensure_ascii=False))
                        pending_challenges.pop(target_name, None)
                        pending_challenge_targets.pop(player_name, None)
                        continue
                
                # Phản hồi cho người mời biết là đã gửi xong
                print(f"[CHALLENGE] {player_name} -> {target_name}")
                await websocket.send_text(json.dumps({"type":"system","text":f"Đã gửi lời mời đến {target_name}. Đang chờ đối thủ chấp nhận..."}))
                continue

            # ==========================================
            # 3. CHẤP NHẬN LỜI MỜI (ACCEPT)
            # ==========================================
            if msg_type == "challenge_accept":
                opponent_name = msg.get("opponent_name") # Tên người đã mời mình
                if not player_name: continue
                async with lock:
                    challenger_ws = find_ws_by_name(opponent_name)
                    # Kiểm tra kỹ xem người mời còn đó không
                    if not challenger_ws and pending_challenges.get(player_name) == opponent_name:
                         challenger_ws = find_player_in_lobby(opponent_name)
                    
                    if not challenger_ws:
                        await websocket.send_text(json.dumps({"type":"error","reason":f"'{opponent_name}' không còn ở sảnh hoặc phiên đã lỗi."}, ensure_ascii=False))
                        continue
                    
                    # Xóa các lời mời đang chờ
                    pending_challenges.pop(player_name, None)
                    pending_challenge_targets.pop(opponent_name, None)
                    # ... dọn dẹp thêm các chiều khác ...
                    pending_challenges.pop(opponent_name, None)
                    pending_challenge_targets.pop(player_name, None)

                    # Xóa cả 2 người khỏi sảnh
                    if websocket in lobby: del lobby[websocket]
                    if challenger_ws in lobby: del lobby[challenger_ws]
                    
                    # Tạo phòng
                    room_id = str(uuid.uuid4())
                    player_room_map[websocket] = room_id
                    player_room_map[challenger_ws] = room_id
                    
                    challenger_name = lobby.get(challenger_ws, opponent_name)
                    acceptor_name = player_name # Người chấp nhận lời mời
                    game_id = create_game_record(room_id, challenger_name, acceptor_name)
                    
                    # Người MỜI (Challenger) cầm ĐỎ, người NHẬN cầm ĐEN
                    rooms[room_id] = {
                        "players": {websocket: acceptor_name, challenger_ws: challenger_name},
                        "player_colors": {challenger_name: 'red', acceptor_name: 'black'},
                        "turn": "red", "state": init_board(), "game_id": game_id,
                        "move_count": 0, "clocks": {"red": 300, "black": 300},
                        "timer_task": None, "rematch_offered_by": None
                    }
                    rooms[room_id]["timer_task"] = asyncio.create_task(timer_loop(room_id))
                    
                    # Gửi tin nhắn bắt đầu game cho CẢ 2 NGƯỜI
                    await websocket.send_text(json.dumps({"type": "game_start", "room_id": room_id, "color": "black", "opponent": challenger_name}, ensure_ascii=False))
                    await challenger_ws.send_text(json.dumps({"type": "game_start", "room_id": room_id, "color": "red", "opponent": acceptor_name}, ensure_ascii=False))
                    
                    print(f"[MATCH START] room={room_id} {challenger_name}(red) vs {acceptor_name}(black)")
                    await send_state(room_id) # Gửi bàn cờ
                
                await send_lobby_update() # Cập nhật sảnh
                continue

            # ==========================================
            # 3.1 TỪ CHỐI LỜI MỜI (DECLINE)
            # ==========================================
            if msg_type == "challenge_decline":
                opponent_name = msg.get("opponent_name")
                async with lock:
                    challenger_ws = find_ws_by_name(opponent_name)
                    if challenger_ws:
                        try:
                            # Báo cho người mời biết là bị từ chối
                            await challenger_ws.send_text(json.dumps({"type":"system", "text": f"{player_name} đã từ chối lời mời."}, ensure_ascii=False))
                        except: pass
                    # Dọn dẹp danh sách chờ
                    pending_challenges.pop(player_name, None)
                    pending_challenge_targets.pop(opponent_name, None)
                continue

            # ==========================================
            # 3.2 CHAT TRONG GAME
            # ==========================================
            if msg_type == "chat_message":
                text = msg.get("text")
                if not text or not player_name: continue
                room_id = player_room_map.get(websocket)
                if not room_id or room_id not in rooms: continue
                
                # Broadcast tin nhắn cho mọi người trong phòng
                chat_msg = {"type": "new_chat_message", "from": player_name, "text": text}
                await broadcast_to_room(room_id, chat_msg)
                continue

            # ==========================================
            # 4. XỬ LÝ NƯỚC ĐI (MOVE) - QUAN TRỌNG NHẤT
            # ==========================================
            if msg_type == "move":
                move = msg.get("move") # Thông tin nước đi: từ {x,y} đến {x,y}
                room_id = player_room_map.get(websocket)
                if not room_id or room_id not in rooms:
                    await websocket.send_text(json.dumps({"type":"error","reason":"Bạn không ở trong phòng."}, ensure_ascii=False))
                    continue

                # Các cờ cảnh báo (Chiếu tướng, Lộ mặt tướng...)
                is_check_alert = False
                is_self_check_alert = False
                is_flying_general_alert = False
                bot_color_to_move = None # Cờ báo hiệu Bot cần đi sau nước này

                async with lock:
                    game = rooms[room_id]
                    player = game["players"].get(websocket)
                    if not player: continue

                    # Kiểm tra lượt đi (Turn)
                    player_color = game["player_colors"].get(player, "spectator")
                    if player_color != game["turn"]:
                        await websocket.send_text(json.dumps({"type":"error","reason":"Không phải lượt của bạn"}, ensure_ascii=False))
                        continue
                    
                    if game.get("game_id") is None:
                        await websocket.send_text(json.dumps({"type":"error","reason":"Game đã kết thúc"}, ensure_ascii=False))
                        continue

                    # Kiểm tra luật cờ (Hàm is_valid_move)
                    valid, reason = is_valid_move(game["state"]["board"], move, player_color)
                    if not valid:
                        await websocket.send_text(json.dumps({"type":"error","reason":reason}, ensure_ascii=False))
                        continue

                    # --- THỰC HIỆN NƯỚC ĐI ---
                    fx, fy = move["from"]["x"], move["from"]["y"]
                    piece = game["state"]["board"][fy][fx]
                    apply_move(game["state"], move) # Cập nhật dữ liệu bàn cờ

                    # --- KIỂM TRA HẬU QUẢ CỦA NƯỚC ĐI ---
                    if is_flying_general(game["state"]["board"]):
                        is_flying_general_alert = True # 2 tướng nhìn mặt nhau
                    if is_king_in_check(game["state"]["board"], player_color):
                        is_self_check_alert = True # Tự làm mình bị chiếu
                    
                    opponent_color = get_opponent_color(player_color)
                    if is_king_in_check(game["state"]["board"], opponent_color):
                        is_check_alert = True # Chiếu tướng đối thủ

                    # Lưu log nước đi vào DB
                    idx = game.get("move_count", 0) + 1
                    add_move_record(game["game_id"], idx, fx, fy, move["to"]["x"], move["to"]["y"], piece)
                    game["move_count"] = idx
                    
                    # ĐỔI LƯỢT
                    game["turn"] = opponent_color

                    # --- KIỂM TRA THẮNG THUA (ĂN MẤT TƯỚNG) ---
                    red_king = find_king(game["state"]["board"], 'red')[0] != -1
                    black_king = find_king(game["state"]["board"], 'black')[0] != -1

                    if not red_king or not black_king:
                        # Nếu một trong 2 tướng biến mất -> Game Over
                        winner_color = 'red' if red_king and not black_king else 'black'
                        reason_msg = "Tướng đã bị ăn"
                        await send_game_over(room_id, winner_color, reason_msg)
                        continue

                    # Kiểm tra nếu đối thủ là BOT thì chuẩn bị kích hoạt Bot
                    player_names = list(game["player_colors"].keys())
                    opponent_name = player_names[1] if player_names[0] == player else player_names[0]
                    if opponent_name == "Bot" and game.get("game_id") and game["turn"] == game["player_colors"]["Bot"]:
                        bot_color_to_move = game["turn"]
                
                # Gửi bàn cờ mới cho cả phòng
                await send_state(room_id)
                
                # Gửi các cảnh báo hệ thống
                if is_flying_general_alert:
                    await websocket.send_text(json.dumps({"type":"system", "text": "⚠️ CẢNH BÁO: Lộ tướng!"}, ensure_ascii=False))
                if is_self_check_alert:
                     await websocket.send_text(json.dumps({"type":"system", "text": "⚠️ CẢNH BÁO: Tướng của bạn đang bị chiếu!"}, ensure_ascii=False))
                if is_check_alert:
                    await broadcast_to_room(room_id, {"type":"system", "text": "CHIẾU TƯỚNG!"})
                
                # Nếu đến lượt Bot -> Gọi hàm Bot suy nghĩ (asyncio.create_task để không chặn server)
                if bot_color_to_move:
                    asyncio.create_task(run_bot_move(room_id, bot_color_to_move))

                continue

            # ==========================================
            # 5. XỬ LÝ CHƠI LẠI (REMATCH) - ĐÃ SỬA LỖI
            # ==========================================
            if msg_type == "offer_rematch":
                room_id = player_room_map.get(websocket)
                if not room_id or room_id not in rooms: continue

                async with lock:
                    game = rooms[room_id]
                    # Chỉ cho phép rematch khi game đã kết thúc (game_id là None)
                    if game.get("game_id") is not None:
                        await websocket.send_text(json.dumps({"type":"error","reason":"Game chưa kết thúc"}))
                        continue

                    player = game["players"].get(websocket)
                    player_names = list(game["player_colors"].keys())
                    
                    # === ĐÂY LÀ DÒNG FIX LỖI "UNDEFINED VARIABLE" ===
                    # Kiểm tra xem trong phòng có "Bot" không
                    is_bot_game = "Bot" in player_names
                    # ================================================

                    # 1. Logic nếu chơi với BOT
                    if is_bot_game:
                        print(f"[{room_id}] Chơi lại với Bot")
                        p1, p2 = player_names
                        # Tạo game mới ngay lập tức (Bot luôn đồng ý)
                        game_id = create_game_record(room_id, p1, p2) 
                        game["state"] = init_board() # Reset bàn cờ
                        game["turn"] = "red" 
                        game["move_count"] = 0
                        game["game_id"] = game_id
                        game["clocks"] = {"red": 300, "black": 300} # Reset đồng hồ
                        game["rematch_offered_by"] = None
                        
                        # Reset task đếm giờ
                        if game.get("timer_task"):
                             try: game["timer_task"].cancel()
                             except: pass
                        game["timer_task"] = asyncio.create_task(timer_loop(room_id))
                        
                        await send_state(room_id)
                        await broadcast_to_room(room_id, {"type":"system", "text": "Bot đã đồng ý. Trận đấu mới bắt đầu!"})
                        continue

                    # 2. Logic nếu chơi NGƯỜI vs NGƯỜI
                    # Nếu đối thủ đã mời trước đó -> Cả 2 cùng đồng ý -> Bắt đầu
                    if game["rematch_offered_by"] and game["rematch_offered_by"] != player:
                        p1, p2 = list(game["player_colors"].keys())
                        game_id = create_game_record(room_id, p1, p2)
                        game["state"] = init_board()
                        game["turn"] = "red"
                        game["move_count"] = 0
                        game["game_id"] = game_id
                        game["clocks"] = {"red": 300, "black": 300}
                        game["rematch_offered_by"] = None
                        if game.get("timer_task"):
                             try: game["timer_task"].cancel()
                             except: pass
                        game["timer_task"] = asyncio.create_task(timer_loop(room_id))
                        await send_state(room_id)
                        await broadcast_to_room(room_id, {"type":"system", "text": "Cả hai đã đồng ý. Trận đấu mới bắt đầu!"})
                    else:
                        # Nếu chưa ai mời -> Lưu lại trạng thái chờ người kia đồng ý
                        game["rematch_offered_by"] = player
                        opponent_ws = get_opponent_ws(room_id, websocket)
                        if opponent_ws:
                            try:
                                await opponent_ws.send_text(json.dumps({"type":"rematch_offered", "from": player}, ensure_ascii=False))
                            except: pass
                        await websocket.send_text(json.dumps({"type":"system", "text": "Đã gửi lời mời chơi lại."}, ensure_ascii=False))
                continue

            # ==========================================
            # 6. THOÁT GAME (LEAVE)
            # ==========================================
            if msg_type == "leave_game":
                room_id = player_room_map.get(websocket)
                # Nếu đang không trong game -> Quay về sảnh
                if not room_id or room_id not in rooms:
                    async with lock:
                        if websocket not in lobby and player_name:
                            lobby[websocket] = player_name
                            await send_lobby_update()
                    continue

                # Nếu đang trong game -> Xử lý rời phòng (thua cuộc nếu đang chơi)
                await cleanup_player(websocket)
                async with lock:
                    if player_name:
                        lobby[websocket] = player_name
                await websocket.send_text(json.dumps({"type":"system","text":"Đã quay về sảnh."}, ensure_ascii=False))
                await send_lobby_update()
                continue

            # Loại tin nhắn lạ, không hiểu
            await websocket.send_text(json.dumps({"type":"error","reason":"unknown_message_type"}))

    # Xử lý khi người chơi tắt trình duyệt hoặc mất mạng
    except WebSocketDisconnect:
        print(f"[WS] Disconnect: {player_name}")
        await cleanup_player(websocket)
    except Exception as e:
        print(f"[WS] Exception for {player_name}: {e}")
        traceback.print_exc()
        await cleanup_player(websocket)