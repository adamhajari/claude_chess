from flask import Flask, request, jsonify, send_from_directory
import chess
import chess.engine
import chess.pgn
import io
import os
import threading

app = Flask(__name__)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCKFISH_PATH = "stockfish"

# Shared state for board sync
_state_lock = threading.Lock()
_board_state = {"pgn": None, "note": "", "go_to_ply": None, "variations": [], "flip": False, "evals": {}, "version": 0}

# Persistent Stockfish engine
_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    if _engine is None:
        _engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    return _engine


@app.route("/")
def index():
    return send_from_directory(_BASE_DIR, "index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    fen = data.get("fen")
    depth = data.get("depth", 18)
    num_moves = data.get("num_moves", 3)

    try:
        board = chess.Board(fen)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    with _engine_lock:
        results = get_engine().analyse(board, chess.engine.Limit(depth=depth), multipv=num_moves)

    moves = []
    for pv in results:
        move = pv["pv"][0]
        score = pv["score"]
        if score.is_mate():
            mate = score.relative.mate()
            score_str = f"Mate in {mate}" if mate > 0 else f"Mated in {abs(mate)}"
            cp = None
        else:
            cp = score.relative.score()
            score_str = f"{cp / 100:+.2f}"
        moves.append({"san": board.san(move), "score_str": score_str, "cp": cp})

    return jsonify({"moves": moves, "turn": "White" if board.turn else "Black"})


@app.route("/best_move", methods=["POST"])
def best_move():
    data = request.json
    fen = data.get("fen")
    depth = data.get("depth", 20)

    try:
        board = chess.Board(fen)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    with _engine_lock:
        result = get_engine().play(board, chess.engine.Limit(depth=depth))

    return jsonify({"san": board.san(result.move)})


@app.route("/eval_game", methods=["POST"])
def eval_game():
    data = request.json
    pgn = data.get("pgn", "")
    time_per_move = data.get("time_per_move", 0.1)

    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    if game is None:
        return jsonify({"error": "Could not parse PGN"}), 400

    board = game.board()
    evals = {}
    limit = chess.engine.Limit(time=time_per_move)
    ply = 0

    with _engine_lock:
        engine = get_engine()
        for move in game.mainline_moves():
            board.push(move)
            ply += 1
            info = engine.analyse(board, limit)
            score = info["score"].white()
            if score.is_mate():
                mate = score.mate()
                cp = 10000 if mate > 0 else -10000
                score_str = f"M{mate}" if mate > 0 else f"M{mate}"
            else:
                cp = score.score()
                score_str = f"{cp / 100:+.2f}"
            evals[str(ply)] = {"score_str": score_str, "cp": cp}

    return jsonify({"evals": evals})


@app.route("/analyze_game", methods=["POST"])
def analyze_game():
    data = request.json
    pgn = data.get("pgn", "")
    color = data.get("color", "both").lower()
    max_move = data.get("max_move", 0)
    time_per_move = data.get("time_per_move", 0.1)

    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    if game is None:
        return jsonify({"error": "Could not parse PGN"}), 400

    analyze_white = color in ("white", "both")
    analyze_black = color in ("black", "both")
    issues = []
    board = game.board()
    limit = chess.engine.Limit(time=time_per_move)

    with _engine_lock:
        engine = get_engine()
        for move in game.mainline_moves():
            move_san = board.san(move)
            move_num = board.fullmove_number
            is_white = board.turn == chess.WHITE
            color_str = "White" if is_white else "Black"

            if max_move and move_num > max_move:
                break
            if is_white and not analyze_white:
                board.push(move)
                continue
            if not is_white and not analyze_black:
                board.push(move)
                continue

            info_before = engine.analyse(board, limit, multipv=3)
            score_before = info_before[0]["score"].white().score(mate_score=10000)
            best_san = board.san(info_before[0]["pv"][0])
            best_score = info_before[0]["score"].white().score(mate_score=10000)

            board.push(move)

            info_after = engine.analyse(board, limit)
            score_after = info_after["score"].white().score(mate_score=10000)

            if score_before is None or score_after is None:
                continue

            drop = (score_before - score_after) if is_white else (score_after - score_before)
            score_str = f"{score_before / 100:+.2f} → {score_after / 100:+.2f}"

            if drop >= 200:
                label = "BLUNDER"
            elif drop >= 100:
                label = "Mistake"
            elif drop >= 50:
                label = "Inaccuracy"
            else:
                continue

            best_str = f" (best: {best_san} {best_score / 100:+.2f})" if best_san != move_san else ""
            issues.append(f"Move {move_num} ({color_str}): **{label}** {move_san} [{score_str}]{best_str}")

    return jsonify({"issues": issues})


@app.route("/stockfish_line", methods=["POST"])
def stockfish_line():
    data = request.json
    pgn = data.get("pgn", "")
    from_ply = data.get("from_ply", 0)
    num_moves = data.get("num_moves", 4)
    time_per_move = data.get("time_per_move", 0.1)

    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    if game is None:
        return jsonify({"error": "Could not parse PGN"}), 400

    board = game.board()
    positions = [board.fen()]
    for move in game.mainline_moves():
        board.push(move)
        positions.append(board.fen())

    if from_ply < 0 or from_ply >= len(positions):
        return jsonify({"error": f"from_ply {from_ply} out of range (game has {len(positions) - 1} plies)"}), 400

    board = chess.Board(positions[from_ply])
    moves = []
    evals = []
    limit = chess.engine.Limit(time=time_per_move)

    with _engine_lock:
        engine = get_engine()
        for _ in range(num_moves):
            if board.is_game_over():
                break
            info = engine.analyse(board, limit)
            best = info["pv"][0]
            moves.append(board.san(best))
            score = info["score"].white().score(mate_score=10000)
            evals.append(round(score / 100, 2) if score is not None else None)
            board.push(best)

    return jsonify({"moves": moves, "evals": evals})


@app.route("/load", methods=["POST"])
def load():
    data = request.json
    pgn = (data.get("pgn") or "").strip()
    note = (data.get("note") or "").strip()
    if not pgn:
        return jsonify({"error": "No PGN provided"}), 400
    with _state_lock:
        _board_state["pgn"] = pgn
        _board_state["note"] = note
        _board_state["go_to_ply"] = data.get("go_to_ply")
        _board_state["variations"] = data.get("variations") or []
        _board_state["flip"] = bool(data.get("flip", False))
        _board_state["evals"] = data.get("evals") or {}
        _board_state["version"] += 1
        version = _board_state["version"]
    return jsonify({"ok": True, "version": version})


@app.route("/current", methods=["GET"])
def current():
    with _state_lock:
        return jsonify(dict(_board_state))


if __name__ == "__main__":
    print("Chess analysis server running at http://localhost:5000")
    app.run(port=5000, debug=False)
