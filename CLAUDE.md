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
uv run web.py
```
Use `&` or `&disown` to run in the background. If `send_to_board` fails with "Connection refused", the server isn't running.

**index.html** — Single-page chess UI served by web.py at `http://localhost:5000`.

## send_to_board details

- `flip=True` when the user is playing Black
- `go_to_ply` formula: `(move_number - 1) * 2 + 1` after White's move N, `+2` after Black's move N
- `variations`: up to 3 alternative lines, each `{"from_ply": N, "moves": [...], "note": "...", "evals": [...]}`
- Always bundle all variations into **one** `send_to_board` call, not separate calls
- `evals` is auto-fetched from `/eval_game` if omitted — but this adds latency; prefer passing it explicitly when you already have it

## Game analysis workflow

1. Determine the user's color first (see **Identifying the user's color** below) before running any analysis. DO NOT PROCEED TO STEP 2 UNTIL YOU HAVE DETERMINED THE USER'S COLOR EITHER FROM A MEMORY OR BY EXPLICITYLY ASKING.
2. Run `analyze_game` with the user's color to analyze only their moves
3. Identify the **3-5 key moments** that most decided the game
4. Send the main line to the board immediately via `send_to_board`, passing the evals you already have. Set `go_to_ply` to the first key moment. **Always set `flip=True` if the user is playing Black.** DO NOT PROCEED TO STEP 5 UNTIL STEP 4 IS COMPLETE.
5. Give the user the URL: `http://localhost:5000`. DO NOT PROCEED TO STEP 6 UNTIL STEP 5 IS COMPLETE.
6. Summarize the 3-5 key moments in text
7. Ask the user if they'd like to see alternative lines for any of these moments. THIS STEP IS REQUIRED. DON'T SKIP IT.
9. Once confirmed, call `get_stockfish_line` (go 4 moves deep unless the user says otherwise) for each selected moment and send all variations in a single `send_to_board` call. **Again set `flip=True` if the user is playing Black.**

**Do not wait for the user to ask for variations before sending the main line to the board.**

## Game analysis rules

- Identify the 3-5 moves that actually decided the game rather than listing every inaccuracy
- Use **time-based** Stockfish analysis (`time_per_move=0.1`), not depth-based. Depth 18-20 on every ply is extremely slow.

## Variation move accuracy

**Never manually compute or guess variation moves or FENs.** Always use `get_stockfish_line` to generate them.

- Call `get_stockfish_line(pgn, from_ply, num_moves=8)` for each branch point (4 moves = 8 half-moves, or more if user requested)
- Pass the returned `moves` list directly into `send_to_board` variations[].moves

## Identifying the user's color

1. Check memory for a saved chess.com username for this user.
2. If no username is saved, **ask before doing anything else**. Save the answer to memory for future conversations.
3. Cross-reference the username against the `[White]` and `[Black]` PGN headers to determine color.
4. **Always state this explicitly** before analyzing (e.g. "Analyzing as Black — playing as adamjdanger"). Set `flip=True` in `send_to_board` when the user is Black.
