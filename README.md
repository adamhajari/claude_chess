# Chess Stockfish MCP

An MCP server that gives Claude direct access to Stockfish and a Flask web app for chess analysis. Ask Claude to analyze positions, find the best move, or review a full game for blunders and mistakes.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Homebrew (Mac)

## Setup

**1. Install uv** (if not already installed)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. Install Stockfish**
```bash
brew install stockfish
```

**3. Clone this repo**
```bash
git clone <repo-url>
cd chess
```

**4. Connect to Claude**

**Claude Code** — restart Claude Code and open this directory. It will detect `.mcp.json` and load the server automatically.

**Claude Desktop** — from inside the cloned repo, run:
```bash
./claude_desktop_install.sh
```
Then restart Claude Desktop. This automatically updates your Claude Desktop config with the correct path.

Python dependencies are managed by `uv` and installed automatically on first run.

## Tools

### `get_instructions`
Returns the full analysis workflow and behavior guidelines from `CLAUDE.md`. Called automatically by Claude Code; Claude Desktop will call it at the start of each conversation.

### `analyze_position`
Returns the top moves for a position given in FEN notation.

```
analyze_position(fen, depth=20, num_moves=3)
```

### `get_best_move`
Returns the single best move for a position.

```
get_best_move(fen, depth=20)
```

### `analyze_game`
Walks through a full game in PGN notation and flags blunders (>200cp drop), mistakes (>100cp), and inaccuracies (>50cp).

```
analyze_game(pgn, color="both", max_move=0, time_per_move=0.1)
```

### `get_stockfish_line`
Returns a Stockfish-recommended continuation from a specific point in a game.

```
get_stockfish_line(pgn, from_ply, num_moves=4, time_per_move=0.1)
```

### `fetch_chesscom_game`
Fetches the PGN for a chess.com game from its URL (daily or live).

```
fetch_chesscom_game(url)
```

### `send_to_board`
Pushes a game to the browser UI, optionally with alternate variation lines.

```
send_to_board(pgn, note="", go_to_ply=-1, flip=False, variations=None)
```

## Web UI

A browser-based board for visualizing games and analysis.

**Start**
```bash
uv run web.py &
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

**Stop**
```bash
pkill -f web.py
```

## Usage

Once set up, just paste a PGN, FEN, or chess.com URL into Claude Code and ask for analysis. For example:

- *"Analyze this position: [FEN]"*
- *"Find all the blunders in this game: [PGN]"*
- *"Help me analyze this game: https://www.chess.com/game/daily/..."*

To get a PGN from Chess.com, open any game → More → Share & Export → Copy PGN.
