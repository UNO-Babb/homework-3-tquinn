# BoardGame.py
"""
Flask backend for the linear board game.

Features:
- Linear board with LAST_TILE tiles (default 100)
- Two players (Player1 and Player2)
- Move by rolling a 6-sided die (POST /roll)
- Events read from game.txt:
    Treasure -> move forward 10
    Portal   -> move backward 3
- Load game state from game.txt at startup
- Save game state to game.txt (POST /save)
- End game when a player reaches or passes LAST_TILE
- Exposes endpoints:
    GET  /          -> serves index.html
    GET  /game_state -> return JSON of current state
    POST /roll      -> perform die roll + move + events; returns move result
    POST /save      -> save current state back to game.txt
    POST /reset     -> reset to initial state from game.txt (optional)
"""

import subprocess
import sys
import os
import random
from flask import Flask, jsonify, render_template, request


try:
    from flask import Flask  
except Exception:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
    except Exception:
        print("Please install Flask manually: pip install Flask")
        raise

app = Flask(__name__)


LAST_TILE = 100          
TREASURE_MOVE = 10       
PORTAL_MOVE = -3         
GAME_FILE = "game.txt"   

state = {
    "turn": "Player1",
    "positions": {"Player1": 0, "Player2": 0},
    "events": {},
    "winner": None
}



def parse_game_file(path):
    """
    Parse a basic text file format for the game.
    Expected (case-insensitive keys):
        Turn: Player1
        Player1: 0
        Player2: 0
        Events:
        12: Treasure
        20: Portal, Treasure

    Returns a dict compatible with `state`.
    """
    parsed = {
        "turn": "Player1",
        "positions": {"Player1": 0, "Player2": 0},
        "events": {},
        "winner": None
    }

    if not os.path.exists(path):
        return parsed

    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines()]

    mode = None  
    for ln in lines:
        if ln == "" or ln.startswith("#"):
            continue
        if ln.lower().startswith("turn:"):
            right = ln.split(":", 1)[1].strip()
            parsed["turn"] = right if right in ("Player1", "Player2") else "Player1"
            continue
        if ln.lower().startswith("player1:"):
            try:
                parsed["positions"]["Player1"] = max(0, int(ln.split(":", 1)[1].strip()))
            except Exception:
                parsed["positions"]["Player1"] = 0
            continue
        if ln.lower().startswith("player2:"):
            try:
                parsed["positions"]["Player2"] = max(0, int(ln.split(":", 1)[1].strip()))
            except Exception:
                parsed["positions"]["Player2"] = 0
            continue
        if ln.lower().startswith("events:"):
            mode = "events"
            continue
        if mode == "events":
          
            if ":" not in ln:
                continue
            left, right = ln.split(":", 1)
            try:
                tile = int(left.strip())
            except Exception:
                continue
          
            evs = [e.strip().capitalize() for e in right.split(",") if e.strip()]
            if evs:
                parsed["events"].setdefault(tile, []).extend(evs)


    for p in ("Player1", "Player2"):
        parsed["positions"][p] = max(0, min(LAST_TILE, parsed["positions"].get(p, 0)))

  
    for p in ("Player1", "Player2"):
        if parsed["positions"][p] >= LAST_TILE:
            parsed["winner"] = p
            parsed["positions"][p] = LAST_TILE

    return parsed


def write_game_file(path, st):
    """
    Write the game state back to a text file using same basic format.
    """
    lines = []
    lines.append(f"Turn: {st['turn']}")
    lines.append(f"Player1: {st['positions']['Player1']}")
    lines.append(f"Player2: {st['positions']['Player2']}")
    lines.append("")  # blank
    lines.append("Events:")
    if st["events"]:
        for tile in sorted(st["events"].keys()):
            events = ", ".join(st["events"][tile])
            lines.append(f"{tile}: {events}")
    content = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def load_game_state():
    global state
    parsed = parse_game_file(GAME_FILE)
    state["turn"] = parsed["turn"]
    state["positions"] = parsed["positions"]
    state["events"] = parsed["events"]
    state["winner"] = parsed.get("winner", None)


def save_game_state():
    write_game_file(GAME_FILE, state)


def roll_die():
    return random.randint(1, 6)


def apply_events(player_name):
    """
    After the player has moved to a tile, apply all events on that tile.
    Events supported:
    - 'Treasure' -> move forward TREASURE_MOVE
    - 'Portal'   -> move backward abs(PORTAL_MOVE)
    Returns a list of applied events and final position.
    """
    pos = state["positions"][player_name]
    applied = []

    events = state["events"].get(pos, [])

    for ev in events:
        ev_lower = ev.lower()
        if ev_lower == "treasure":
            pos += TREASURE_MOVE
            applied.append("Treasure")
        elif ev_lower == "portal":
            pos += PORTAL_MOVE
            applied.append("Portal")
   


    pos = max(0, min(LAST_TILE, pos))
    state["positions"][player_name] = pos

    if pos >= LAST_TILE:
        state["winner"] = player_name

    return applied, pos


def attempt_move(player_name, steps):
    """
    Move the player forward `steps` spots, then apply events.
    Returns dict with details of roll, intermediate position, events_applied, final_position, winner(if any)
    """
    if state["winner"] is not None:
        return {"error": "Game already finished", "winner": state["winner"]}

    start = state["positions"][player_name]
    new_pos = start + steps
    new_pos = min(new_pos, LAST_TILE)
    state["positions"][player_name] = new_pos

    if new_pos >= LAST_TILE:
        state["winner"] = player_name
        return {
            "player": player_name,
            "rolled": steps,
            "start": start,
            "moved_to": new_pos,
            "events": [],
            "final": new_pos,
            "winner": player_name
        }

    applied, final_pos = apply_events(player_name)

    return {
        "player": player_name,
        "rolled": steps,
        "start": start,
        "moved_to": new_pos,
        "events": applied,
        "final": final_pos,
        "winner": state["winner"]
    }


def switch_turn():
    state["turn"] = "Player2" if state["turn"] == "Player1" else "Player1"



load_game_state()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/game_state", methods=["GET"])
def get_game_state():
    """
    Return the full current state (for frontend rendering).
    """
    return jsonify({
        "turn": state["turn"],
        "positions": state["positions"],
        "events": state["events"],
        "winner": state["winner"],
        "last_tile": LAST_TILE
    })


@app.route("/roll", methods=["POST"])
def handle_roll():
    """
    Perform a die roll for the current player, move them, apply events, switch turn (unless game ended).
    Returns JSON with detailed move information.
    """
    if state["winner"] is not None:
        return jsonify({"error": "Game already finished", "winner": state["winner"]}), 400

    player = state["turn"]
    die = roll_die()
    result = attempt_move(player, die)

    if state["winner"] is None:
        switch_turn()

    try:
        save_game_state()
    except Exception:
    
        pass

    return jsonify(result)


@app.route("/save", methods=["POST"])
def handle_save():
    try:
        save_game_state()
        return jsonify({"saved": True})
    except Exception as e:
        return jsonify({"saved": False, "error": str(e)}), 500


@app.route("/reset", methods=["POST"])
def handle_reset():
    """
    Reset in-memory state to initial contents of game.txt.
    """
    load_game_state()
    return jsonify({"reset": True, "state": state})


if __name__ == "__main__":
    print("Starting Flask server at http://127.0.0.1:5000")
    app.run(debug=True)