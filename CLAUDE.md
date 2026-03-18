# Chess Analysis MCP — Claude Instructions

## Architecture

Three components run together:

**server.py** — MCP server. Exposes these tools to Claude:
- `start_web_server()` — starts web.py if not running, returns URL
- `fetch_chesscom_game(url)` — fetches PGN from a chess.com game URL (daily or live)
- `analyze_position(fen, depth, num_moves)` — top N moves with scores for a position
- `get_best_move(fen, depth)` — single best move for a position
- `analyze_game(pgn, color, max_move, time_per_move)` — full game blunder/mistake/inaccuracy report
- `get_stockfish_line(pgn, from_ply, num_moves, time_per_move)` — Stockfish-recommended continuation from a ply
- `send_to_board(pgn, note, go_to_ply, variations, flip, evals)` — pushes a game to the browser UI

**web.py** — Flask server on port 5000. Start it with:
```
uv run --with flask --with chess web.py
```
Use `&` or `&disown` to run in the background. If `send_to_board` fails with "Connection refused", the server isn't running.

**index.html** — Single-page chess UI served by web.py at `http://localhost:5000`.

## send_to_board details

- `flip=True` when the user is playing Black
- `go_to_ply` formula: `(move_number - 1) * 2 + 1` after White's move N, `+2` after Black's move N
- `variations`: up to 3 alternative lines, each `{"from_ply": N, "moves": [...], "note": "...", "evals": [...]}`
- Always bundle all variations into **one** `send_to_board` call, not separate calls
- `evals` is auto-fetched from `/eval_game` if omitted — but this adds latency; prefer passing it explicitly when you already have it

## Game analysis rules

- Identify the 2-4 moves that actually decided the game rather than listing every inaccuracy
- Use **time-based** Stockfish analysis (`time_per_move=0.1`), not depth-based. Depth 18-20 on every ply is extremely slow.
- For each of the 2-4 moves that decided the game, find and alternate branch that shows what the user should have done
- send the main line and all alternate branches (along with evaluation scores) to be displayed by the web app


## Variation move accuracy

**Never manually compute or guess variation moves or FENs.** Always use `get_stockfish_line` to generate them.

- Call `get_stockfish_line(pgn, from_ply)` for each branch point
- Pass the returned `moves` list directly into `send_to_board` variations[].moves
- Keep variations to 6-8 half-moves

## Identifying the user's color

When a user shares a chess.com URL or PGN, **infer which color they are playing from context** — do not ask, and do not hardcode any username. State your assumption explicitly before analyzing (e.g. "I'll analyze this from Black's perspective"). Set `flip=True` in `send_to_board` when the user is Black.
