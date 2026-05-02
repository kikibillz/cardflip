import tkinter as tk
from tkinter import messagebox
import random
import mysql.connector
from dotenv import load_dotenv
import os

# ─────────────────────────────────────────────────────────────────────────────
# ENV & DB
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()
DB_HOST     = os.getenv("DB_HOST")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME     = os.getenv("DB_NAME")

conn = mysql.connector.connect(
    host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
)
cursor = conn.cursor()
cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`")
cursor.execute(f"USE `{DB_NAME}`")
cursor.execute("""
CREATE TABLE IF NOT EXISTS scores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    mode         VARCHAR(50),
    player_score INT,
    computer_score INT,
    winner       VARCHAR(50)
)
""")
conn.commit()

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
BG          = "#f0f8ff"
CARD_BACK   = "#e6e6e6"   # face-down
CARD_REVEAL = "#cce5ff"   # revealed but not yet part of any scoring group
CARD_PAIR   = "#90EE90"   # light-green  – pair matched (1 pt)
CARD_TRIO   = "#FFD700"   # gold         – full trio matched (2 pts)

# 9 cards: 3 symbols × 3 copies each
SYMBOLS     = ["🍎", "🍎", "🍎",
               "🍌", "🍌", "🍌",
               "🍇", "🍇", "🍇"]
TOTAL       = 9

# ─────────────────────────────────────────────────────────────────────────────
# ROOT WINDOW  (created once, never destroyed)
# ─────────────────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("Card Flip")
root.configure(bg=BG)

# ─────────────────────────────────────────────────────────────────────────────
# GAME STATE
# ─────────────────────────────────────────────────────────────────────────────
values          = []          # shuffled symbol list, index = card position
revealed        = set()       # indices that are permanently face-up
scored_indices  = set()       # indices that have already been counted for points
# Each card state: 'hidden' | 'revealed' | 'pair' | 'trio'
card_state      = {}

player_score    = 0
computer_score  = 0
turn            = "Player"
mode            = None
time_elapsed    = 0
timer_running   = False
locked          = False       # True while computer is animating

canvas          = None
player_text = computer_text = turn_text = timer_text = None

computer_memory = {}          # {index: symbol} – what computer has seen

# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────
def show_homepage():
    clear_screen()
    f = tk.Frame(root, bg=BG)
    f.pack(pady=50)
    tk.Label(f, text="🎴 Card Flip 🎴",
             font=("Arial", 28, "bold"), bg=BG).pack(pady=10)
    for txt, cmd in [("Start Game",    show_menu),
                     ("View History",  show_history),
                     ("Clear History", clear_history),
                     ("Quit",          root.destroy)]:
        tk.Button(f, text=txt, width=22, command=cmd).pack(pady=7)

def show_menu():
    clear_screen()
    f = tk.Frame(root, bg=BG)
    f.pack(pady=50)
    tk.Label(f, text="Select Mode",
             font=("Arial", 20, "bold"), bg=BG).pack(pady=10)
    for txt, m in [("PvC Easy",  "PvC_Easy"),
                   ("PvC Smart", "PvC_Smart"),
                   ("PvP",       "PvP"),
                   ("Solo",      "Solo")]:
        tk.Button(f, text=txt, width=22,
                  command=lambda m=m: start_game(m)).pack(pady=5)
    tk.Button(f, text="Back", width=22, command=show_homepage).pack(pady=5)

def show_history():
    clear_screen()
    f = tk.Frame(root, bg=BG)
    f.pack(fill="both", expand=True)
    tk.Label(f, text="Game History",
             font=("Arial", 20, "bold"), bg=BG).pack(pady=10)
    tb = tk.Text(f, wrap="word", width=80, height=20)
    tb.pack(padx=10, pady=10, fill="both", expand=True)
    cursor.execute("SELECT * FROM scores")
    rows = cursor.fetchall()
    if not rows:
        tb.insert("end", "No games played yet.")
    else:
        for h in rows:
            p2 = "Player 2" if h[1] == "PvP" else "Computer"
            tb.insert("end",
                f"Game {h[0]} | Mode: {h[1]} | "
                f"Player: {h[2]} | {p2}: {h[3]} | Winner: {h[4]}\n")
    tk.Button(f, text="Back", command=show_homepage).pack(pady=10)

def clear_history():
    if messagebox.askyesno("Clear History", "Delete all game history?"):
        cursor.execute("DELETE FROM scores")
        conn.commit()
        messagebox.showinfo("Done", "History cleared.")

def clear_screen():
    for w in root.winfo_children():
        w.destroy()

# ─────────────────────────────────────────────────────────────────────────────
# GAME START
# ─────────────────────────────────────────────────────────────────────────────
def start_game(selected_mode):
    global mode, values, revealed, scored_indices, card_state
    global player_score, computer_score, turn
    global time_elapsed, timer_running, locked, computer_memory

    mode            = selected_mode
    values          = SYMBOLS[:]
    random.shuffle(values)

    revealed        = set()
    scored_indices  = set()
    card_state      = {i: "hidden" for i in range(TOTAL)}
    computer_memory = {}
    locked          = False
    player_score    = 0
    computer_score  = 0
    turn            = "Player 1" if mode == "PvP" else "Player"
    time_elapsed    = 0
    timer_running   = True

    show_game()

# ─────────────────────────────────────────────────────────────────────────────
# BOARD LAYOUT
# ─────────────────────────────────────────────────────────────────────────────
def show_game():
    clear_screen()
    global canvas, player_text, computer_text, turn_text, timer_text

    canvas = tk.Canvas(root, width=620, height=670, bg=BG)
    canvas.pack()

    # Title
    canvas.create_text(310, 28, text="Card Flip — Memory Match",
                       font=("Arial", 22, "bold"), fill="darkblue")

    # Scoring legend
    canvas.create_rectangle(30, 46, 590, 66, fill="#ddeeff", outline="#aabbcc")
    canvas.create_text(310, 56,
        text="🟩 Pair (2 same) = 1 pt     🟨 Trio (3 same) = 2 pts     Cards never go back!",
        font=("Arial", 10), fill="#334455")

    # Scoreboard row
    p2_label = "Player 2" if mode == "PvP" else "Computer"
    player_text   = canvas.create_text(100, 88,
                        text=f"Player: {player_score}",
                        font=("Arial", 15, "bold"), fill="darkgreen")
    computer_text = canvas.create_text(310, 88,
                        text=f"{p2_label}: {computer_score}",
                        font=("Arial", 15, "bold"), fill="darkred")
    turn_text     = canvas.create_text(510, 88,
                        text=f"Turn: {turn}",
                        font=("Arial", 13, "bold"), fill="#005577")
    timer_text    = canvas.create_text(310, 112,
                        text="Time: 0s",
                        font=("Arial", 13), fill="#333333")

    # Toolbar
    for tag, label, x0, x1, colour, cb in [
        ("back",    "◀ Back",    20,  130, "#d0d0d0", lambda e: show_menu()),
        ("end",     "End Game", 235,  385, "#ffaaaa", lambda e: end_game()),
        ("restart", "Restart ↺", 490, 600, "#aaddff", lambda e: start_game(mode)),
    ]:
        canvas.create_rectangle(x0, 124, x1, 148, fill=colour,
                                outline="#888", tags=tag)
        canvas.create_text((x0+x1)//2, 136, text=label,
                           font=("Arial", 11, "bold"), tags=tag)
        canvas.tag_bind(tag, "<Button-1>", cb)

    # Card grid  (3 × 3, card size 160×140, small gap)
    draw_grid()
    update_display()
    update_timer()

CARD_W, CARD_H = 160, 140
GRID_X0, GRID_Y0 = 30, 162
GAP = 12

def card_bbox(i):
    col, row = i % 3, i // 3
    x = GRID_X0 + col * (CARD_W + GAP)
    y = GRID_Y0 + row * (CARD_H + GAP)
    return x, y, x + CARD_W, y + CARD_H

def draw_grid():
    for i in range(TOTAL):
        x0, y0, x1, y1 = card_bbox(i)
        canvas.create_rectangle(x0, y0, x1, y1,
                                fill=CARD_BACK, outline="#555", width=2,
                                tags=f"card_{i}")
        canvas.create_text((x0+x1)//2, (y0+y1)//2,
                           text="", font=("Arial", 44),
                           tags=f"text_{i}")
        canvas.tag_bind(f"card_{i}", "<Button-1>",
                        lambda e, i=i: on_player_click(i))
    # Restore any already-revealed cards (e.g. after restart)
    for i in revealed:
        _paint_card(i)

def _card_colour(i):
    st = card_state[i]
    if st == "trio":   return CARD_TRIO
    if st == "pair":   return CARD_PAIR
    if st == "revealed": return CARD_REVEAL
    return CARD_BACK

def _paint_card(i):
    colour = _card_colour(i)
    canvas.itemconfig(f"card_{i}", fill=colour)
    canvas.itemconfig(f"text_{i}",
                      text=values[i] if i in revealed else "")

# ─────────────────────────────────────────────────────────────────────────────
# CORE FLIP LOGIC  — the heart of the new rules
# ─────────────────────────────────────────────────────────────────────────────
def do_flip(i):
    """
    Flip card i face-up (permanently).
    Then check whether this symbol now has 2 or 3 revealed copies and score.
    Returns points earned (0, 1, or 2).
    """
    # Mark permanently revealed
    revealed.add(i)
    card_state[i] = "revealed"
    computer_memory[i] = values[i]

    # Count how many copies of this symbol are now revealed
    sym = values[i]
    sym_revealed = [j for j in revealed if values[j] == sym]
    total_of_sym = values.count(sym)   # always 3 in this deck

    points_earned = 0

    if len(sym_revealed) == total_of_sym:
        # ── TRIO: all 3 of this symbol are now revealed ──────────────────────
        # If a pair was already scored, upgrade earns +1; otherwise full 2 pts
        previously_scored = [j for j in sym_revealed if j in scored_indices]
        points_earned = 1 if previously_scored else 2

        for j in sym_revealed:
            card_state[j] = "trio"
            scored_indices.add(j)
        _repaint_symbol(sym)

    elif len(sym_revealed) == 2:
        # ── PAIR: exactly 2 of 3 revealed ────────────────────────────────────
        previously_scored = [j for j in sym_revealed if j in scored_indices]
        if not previously_scored:
            # brand new pair – 1 point
            points_earned = 1
            for j in sym_revealed:
                card_state[j] = "pair"
                scored_indices.add(j)
            _repaint_symbol(sym)
    else:
        # Only 1 of this symbol revealed — no score, just show it
        _paint_card(i)

    return points_earned

def _repaint_symbol(sym):
    """Repaint every card that carries `sym` to reflect its current state."""
    for j in range(TOTAL):
        if values[j] == sym:
            _paint_card(j)

def _award(pts):
    """Credit points to whichever player/computer is currently taking a turn."""
    global player_score, computer_score
    if mode == "PvP":
        if turn == "Player 1":
            player_score += pts
        else:
            computer_score += pts
    elif mode == "Solo":
        player_score += pts
    else:   # PvC
        if turn == "Player":
            player_score += pts
        else:
            computer_score += pts

def _switch_turn():
    global turn
    if mode == "PvP":
        turn = "Player 2" if turn == "Player 1" else "Player 1"
    elif mode in ("PvC_Easy", "PvC_Smart"):
        turn = "Computer" if turn == "Player" else "Player"
    # Solo: turn never changes

# ─────────────────────────────────────────────────────────────────────────────
# PLAYER CLICK
# ─────────────────────────────────────────────────────────────────────────────
def on_player_click(i):
    global locked

    if locked:
        return
    if i in revealed:          # already face-up — ignore
        return
    if mode in ("PvC_Easy", "PvC_Smart") and turn != "Player":
        return

    pts = do_flip(i)
    _award(pts)
    update_display()

    # Check win condition
    if len(revealed) == TOTAL:
        root.after(500, end_game)
        return

    # Scoring gives the current player another turn; no score → switch
    if pts == 0:
        _switch_turn()
        update_display()
        if mode in ("PvC_Easy", "PvC_Smart") and turn == "Computer":
            locked = True
            root.after(700, run_computer_turn)

# ─────────────────────────────────────────────────────────────────────────────
# COMPUTER AI
# ─────────────────────────────────────────────────────────────────────────────
def run_computer_turn():
    global locked

    if mode not in ("PvC_Easy", "PvC_Smart") or turn != "Computer":
        locked = False
        return

    hidden = [i for i in range(TOTAL) if i not in revealed]
    if not hidden:
        locked = False
        return

    chosen = _computer_pick(hidden)
    _computer_flip_sequence(chosen, 0)

def _computer_flip_sequence(queue, idx):
    """Flip one computer card at a time with 900 ms between flips."""
    global locked

    if idx >= len(queue):
        locked = False
        return

    i = queue[idx]
    pts = do_flip(i)
    _award(pts)
    update_display()

    if len(revealed) == TOTAL:
        locked = False
        root.after(500, end_game)
        return

    if pts > 0:
        # Computer scored → keep going (another flip in sequence or restart turn)
        root.after(900, lambda: _computer_flip_sequence(queue, idx + 1))
    else:
        # No score on this flip — continue flipping remaining picks
        if idx + 1 < len(queue):
            root.after(900, lambda: _computer_flip_sequence(queue, idx + 1))
        else:
            # Exhausted the planned picks — switch turn
            _switch_turn()
            update_display()
            if turn == "Computer":
                # Computer goes again (scored at some point, stayed on its turn)
                root.after(700, run_computer_turn)
            else:
                locked = False

def _computer_pick(hidden):
    """
    Decide which hidden cards the computer will flip this turn.
    Returns a list of indices to flip in order.
    """
    if mode == "PvC_Smart":
        # Priority 1: complete a known pair → certain 2 pts
        for sym in set(values[j] for j in hidden):
            known_of_sym = [j for j in computer_memory if values[j] == sym
                            and j not in revealed]
            revealed_of_sym = [j for j in revealed if values[j] == sym]
            # If 2 are already revealed and the 3rd is hidden & known
            if len(revealed_of_sym) == 2:
                candidates = [j for j in known_of_sym if j not in revealed]
                if candidates:
                    return [candidates[0]]
            # If 1 revealed and 2 hidden are known → flip both
            if len(revealed_of_sym) == 1:
                candidates = [j for j in known_of_sym if j not in revealed]
                if len(candidates) >= 2:
                    return candidates[:2]
            # If 0 revealed and all 3 known → flip all 3 at once
            if len(revealed_of_sym) == 0:
                candidates = [j for j in known_of_sym if j not in revealed]
                if len(candidates) == 3:
                    return candidates[:3]

        # Priority 2: flip one unseen card (expand memory)
        unseen = [j for j in hidden if j not in computer_memory]
        if unseen:
            pick = random.choice(unseen)
            sym  = values[pick]
            # If flipping this exposes a pair/trio opportunity, queue the partner too
            partner_known = [j for j in computer_memory
                             if values[j] == sym and j not in revealed and j != pick]
            revealed_of_sym = [j for j in revealed if values[j] == sym]
            if partner_known and len(revealed_of_sym) + 1 + len(partner_known) >= 2:
                return [pick] + partner_known[:2]
            return [pick]

        # Priority 3: all hidden cards are known but no complete set — flip randomly
        return [random.choice(hidden)]

    else:
        # PvC_Easy — flip one random hidden card per turn
        return [random.choice(hidden)]

# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY & TIMER
# ─────────────────────────────────────────────────────────────────────────────
def update_display():
    p2_label = "Player 2" if mode == "PvP" else "Computer"
    canvas.itemconfig(player_text,   text=f"Player: {player_score}")
    canvas.itemconfig(computer_text, text=f"{p2_label}: {computer_score}")
    canvas.itemconfig(turn_text,     text=f"Turn: {turn}")

def update_timer():
    global time_elapsed
    if timer_running:
        time_elapsed += 1
        canvas.itemconfig(timer_text, text=f"Time: {time_elapsed}s")
        root.after(1000, update_timer)

# ─────────────────────────────────────────────────────────────────────────────
# END GAME
# ─────────────────────────────────────────────────────────────────────────────
def end_game():
    global timer_running, locked
    timer_running = False
    locked        = True

    if mode == "Solo":
        winner = "Player"
        msg = (f"Game Over!\n"
               f"All cards revealed!\n"
               f"Your score: {player_score} pts\n"
               f"Time: {time_elapsed}s")
    else:
        p2_label = "Player 2" if mode == "PvP" else "Computer"
        if player_score > computer_score:
            winner = "Player 1" if mode == "PvP" else "Player"
        elif computer_score > player_score:
            winner = p2_label
        else:
            winner = "Tie"
        msg = (f"Game Over!\n"
               f"🏆 Winner: {winner}\n\n"
               f"Player: {player_score} pts\n"
               f"{p2_label}: {computer_score} pts\n"
               f"Time: {time_elapsed}s")

    messagebox.showinfo("Game Over", msg)
    cursor.execute(
        "INSERT INTO scores (mode, player_score, computer_score, winner) "
        "VALUES (%s, %s, %s, %s)",
        (mode, player_score, computer_score, winner)
    )
    conn.commit()
    show_menu()

# ─────────────────────────────────────────────────────────────────────────────
# LAUNCH
# ─────────────────────────────────────────────────────────────────────────────
show_homepage()
root.mainloop()