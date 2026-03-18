import atexit
import chess
import chess.pgn
import io
import json
import os
import subprocess
import time
import urllib.request
from mcp.server.fastmcp import FastMCP

STOCKFISH_PATH = "stockfish"
WEB_URL = "http://localhost:5000"

mcp = FastMCP("chess-stockfish")

# --- Web server lifecycle ---

_web_process = None


def _start_web_server():
    global _web_process
    try:
        with urllib.request.urlopen(WEB_URL, timeout=2):
            return  # already running, don't manage it
    except Exception:
        pass

    web_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web.py")
    _web_process = subprocess.Popen(
        ["uv", "run", web_py],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    atexit.register(_stop_web_server)

    for _ in range(20):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(WEB_URL, timeout=1):
                return
        except Exception:
            pass


def _stop_web_server():
    global _web_process
    if _web_process is not None:
        _web_process.terminate()
        _web_process = None


_start_web_server()


# --- HTTP helper ---

def _post(path, data, timeout=300):
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{WEB_URL}{path}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# --- MCP tools ---

@mcp.tool()
def start_web_server() -> str:
    """Start the chess web UI (web.py) if it's not already running.

    Returns the URL to open in the browser.
    """
    try:
        with urllib.request.urlopen(WEB_URL, timeout=2):
            return f"Web server running at {WEB_URL}"
    except Exception:
        _start_web_server()
        return f"Web server started at {WEB_URL}"


@mcp.tool()
def fetch_chesscom_game(url: str) -> str:
    """Fetch the PGN for a chess.com game from its URL.

    Supports daily and live game URLs, e.g.:
      https://www.chess.com/game/daily/871993649
      https://www.chess.com/game/live/12345678

    Args:
        url: The chess.com game URL
    """
    import re

    m = re.search(r"chess\.com/game/(daily|live)/(\d+)", url)
    if not m:
        return f"Could not parse chess.com game URL: {url}"
    game_type, game_id = m.group(1), m.group(2)

    callback_url = f"https://www.chess.com/callback/{game_type}/game/{game_id}"
    req = urllib.request.Request(callback_url, headers={"User-Agent": "chess-mcp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        return f"Could not fetch game metadata: {e}"

    try:
        username = data["players"]["bottom"]["username"]
        end_date = data["game"].get("pgnHeaders", {}).get("EndDate", "")
        if not end_date:
            return "Could not determine game end date from metadata."
        year, month, _ = end_date.split(".")
    except (KeyError, ValueError) as e:
        return f"Unexpected metadata structure: {e}"

    archive_url = f"https://api.chess.com/pub/player/{username}/games/{year}/{month}"
    req2 = urllib.request.Request(archive_url, headers={"User-Agent": "chess-mcp/1.0"})
    try:
        with urllib.request.urlopen(req2, timeout=10) as resp:
            archive = json.loads(resp.read())
    except Exception as e:
        return f"Could not fetch game archive: {e}"

    target_url = f"https://www.chess.com/game/{game_type}/{game_id}"
    for game in archive.get("games", []):
        if game.get("url", "").rstrip("/") == target_url:
            return game.get("pgn", "PGN not found in archive entry.")

    return f"Game {game_id} not found in {username}'s archive for {year}/{month}."


@mcp.tool()
def analyze_position(fen: str, depth: int = 20, num_moves: int = 3) -> str:
    """Analyze a chess position and return the top moves with evaluations.

    Args:
        fen: The position in FEN notation
        depth: How deep to analyze (higher = stronger but slower, default 20)
        num_moves: How many top moves to return (default 3)
    """
    try:
        result = _post("/analyze", {"fen": fen, "depth": depth, "num_moves": num_moves})
    except Exception as e:
        return f"Analysis failed: {e}"

    if "error" in result:
        return f"Error: {result['error']}"

    lines = [f"Position: {fen}", f"Turn: {result['turn']}", ""]
    for i, m in enumerate(result["moves"]):
        lines.append(f"{i + 1}. {m['san']} ({m['score_str']})")
    return "\n".join(lines)


@mcp.tool()
def get_best_move(fen: str, depth: int = 20) -> str:
    """Get the single best move for a position.

    Args:
        fen: The position in FEN notation
        depth: How deep to analyze (default 20)
    """
    try:
        result = _post("/best_move", {"fen": fen, "depth": depth})
    except Exception as e:
        return f"Analysis failed: {e}"

    if "error" in result:
        return f"Error: {result['error']}"
    return f"Best move: {result['san']}"


@mcp.tool()
def analyze_game(
    pgn: str,
    color: str = "both",
    max_move: int = 0,
    time_per_move: float = 0.1,
) -> str:
    """Analyze a chess game and identify blunders, mistakes, and inaccuracies.

    Thresholds:
      - Blunder: evaluation drops by more than 200 centipawns
      - Mistake: evaluation drops by 100-200 centipawns
      - Inaccuracy: evaluation drops by 50-100 centipawns

    For each error, also returns the best alternative move and its evaluation.

    Args:
        pgn: The full game in PGN notation
        color: Which side to analyze — "white", "black", or "both" (default "both").
               When reviewing a specific player's game, pass their color to skip
               analyzing the opponent's moves entirely.
        max_move: Stop analysis after this move number (default 0 = full game).
                  Useful for focusing on the opening/early middlegame where mistakes
                  have the most impact on the game's direction.
        time_per_move: Seconds of Stockfish thinking time per position (default 0.1).
                       0.1s is fast and accurate enough to find all real mistakes.
                       Do NOT use depth-based analysis — time-based is faster and
                       equally reliable for game review purposes.
    """
    try:
        result = _post("/analyze_game", {
            "pgn": pgn, "color": color, "max_move": max_move, "time_per_move": time_per_move,
        })
    except Exception as e:
        return f"Analysis failed: {e}"

    if "error" in result:
        return f"Error: {result['error']}"

    issues = result.get("issues", [])
    return "\n".join(issues) if issues else "No significant errors found."


@mcp.tool()
def get_stockfish_line(
    pgn: str,
    from_ply: int,
    num_moves: int = 4,
    time_per_move: float = 0.1,
) -> str:
    """Get a Stockfish-recommended continuation from a specific point in a game.

    Plays through the PGN to the given ply, then runs Stockfish to generate
    the best continuation for the requested number of half-moves.

    IMPORTANT: Always use this tool to get variation moves. Never compute or
    guess variation moves manually — Stockfish is the authoritative source.

    Args:
        pgn: The full game PGN (from move 1)
        from_ply: Branch point using the same ply formula as send_to_board:
                  ply = (move_number - 1) * 2 + (1 if white_just_moved else 2)
                  e.g. after White's move 10 = ply 19, after Black's move 10 = ply 20
        num_moves: Number of half-moves to generate (default 4)
        time_per_move: Seconds of Stockfish thinking time per move (default 0.1)

    Returns:
        JSON with "moves" (list[str] of SAN moves) and "evals" (list of scores).
        Pass "moves" directly into send_to_board variations[].moves.
    """
    try:
        result = _post("/stockfish_line", {
            "pgn": pgn, "from_ply": from_ply, "num_moves": num_moves, "time_per_move": time_per_move,
        })
    except Exception as e:
        return f"Analysis failed: {e}"

    if "error" in result:
        return f"Error: {result['error']}"
    return json.dumps(result)


@mcp.tool()
def send_to_board(
    pgn: str,
    note: str = "",
    go_to_ply: int = -1,
    variations: list[dict] | None = None,
    flip: bool = False,
    evals: dict | None = None,
) -> str:
    """Send a full game PGN to the browser chess board for visualization.

    Args:
        pgn: The full game in PGN notation (always from move 1)
        note: Optional message to show alongside the board
        go_to_ply: Which ply (half-move) to jump to after loading. 0 = starting
                   position, 1 = after White's first move, 2 = after Black's first,
                   etc. Use -1 (default) to go to the end of the game.
                   Formula: ply = (move_number - 1) * 2 + (1 if white_just_moved else 2)
                   e.g. after White's move 9 = ply 17, after Black's move 9 = ply 18.
        flip: Set to True when the user is playing Black, so the board is shown
              from Black's perspective (Black pieces at the bottom).
        variations: Up to 3 alternative lines to show alongside the main game.
                    Each entry is a dict with:
                      - from_ply (int): branch point — same ply formula as go_to_ply
                      - moves (list[str]): SAN moves from the branch position
                      - note (str, optional): label shown on the tab and banner
                      - evals (list[float], optional): Stockfish evals in pawns, one per
                        move, from White's perspective. Pass the "evals" list returned
                        directly by get_stockfish_line. These are displayed as you step
                        through the variation — no need to hit Analyze.
                    Example: [{"from_ply": 18, "moves": ["Nf6", "Bg5", "Be7"],
                               "evals": [0.3, 0.2, 0.4],
                               "note": "Better was Nf6"}]
        evals: Optional pre-computed Stockfish evaluations keyed by ply number.
               Each entry: {"score_str": "+2.30", "cp": 230}
               If omitted, evals are fetched automatically from /eval_game for all positions.
               The board will auto-display these without needing the Analyze button.
    """
    validated_variations = []
    if variations:
        try:
            game = chess.pgn.read_game(io.StringIO(pgn))
            if game:
                main_board = game.board()
                main_positions = [main_board.fen()]
                for move in game.mainline_moves():
                    main_board.push(move)
                    main_positions.append(main_board.fen())

                for v in variations[:3]:
                    from_ply = v.get("from_ply", 0)
                    san_list = v.get("moves") or []
                    if from_ply < 0 or from_ply >= len(main_positions):
                        continue
                    vboard = chess.Board(main_positions[from_ply])
                    valid_sans = []
                    ok = True
                    for san in san_list:
                        try:
                            move = vboard.parse_san(san)
                            valid_sans.append(vboard.san(move))
                            vboard.push(move)
                        except Exception:
                            ok = False
                            break
                    if ok and valid_sans:
                        entry = {
                            "from_ply": from_ply,
                            "moves": valid_sans,
                            "note": (v.get("note") or "").strip(),
                        }
                        if v.get("evals"):
                            entry["evals"] = v["evals"]
                        validated_variations.append(entry)
        except Exception:
            pass

    if not evals:
        try:
            ev_result = _post("/eval_game", {"pgn": pgn})
            evals = ev_result.get("evals", {})
        except Exception:
            evals = {}

    try:
        result = _post("/load", {
            "pgn": pgn,
            "note": note,
            "go_to_ply": go_to_ply,
            "variations": validated_variations,
            "flip": flip,
            "evals": evals,
        })
        return f"Sent to board (version {result.get('version', '?')})"
    except Exception as e:
        return f"Could not reach web server: {e}"


if __name__ == "__main__":
    mcp.run()
