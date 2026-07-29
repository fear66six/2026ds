# game_vision.py — TaskSuite 任务4/5/6：扫盘 + Minimax + 发令（可含复位）
import math

EMPTY, YELLOW, BLUE = 0, 1, 2
WIN_NONE, WIN_YELLOW, WIN_BLUE, WIN_DRAW = 0, 1, 2, 3

LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)

THRESH_YELLOW = (20, 90, -20, 40, 20, 127)
THRESH_BLUE = (-19, 83, -13, 37, -72, -22)
PIXELS_THRESHOLD = 50
AREA_THRESHOLD = 400

DETECT_W, DETECT_H = 640, 480
# 与 Task08 / board_roi_config.h 对齐（BASE_ORIGIN_Y 110 + SHIFT_Y 30）
ORIGIN_X, ORIGIN_Y = 170, 140
CELL_W, CELL_H, ROI_SIZE = 95, 95, 60


def build_rois():
    ox, oy = ORIGIN_X, ORIGIN_Y
    half = ROI_SIZE // 2
    rois = []
    for r in range(3):
        row = []
        for c in range(3):
            cx = ox + ROI_SIZE // 2 + c * CELL_W
            cy = oy + ROI_SIZE // 2 + r * CELL_H
            x = max(0, min(DETECT_W - ROI_SIZE, cx - half))
            y = max(0, min(DETECT_H - ROI_SIZE, cy - half))
            row.append((x, y, ROI_SIZE, ROI_SIZE))
        rois.append(row)
    return rois


def _blob_pixels(b):
    try:
        return b.pixels()
    except Exception:
        try:
            return b[4]
        except Exception:
            return 0


def classify_roi(img, roi):
    try:
        yb = img.find_blobs([THRESH_YELLOW], roi=roi,
                            pixels_threshold=PIXELS_THRESHOLD,
                            area_threshold=AREA_THRESHOLD, merge=True)
        bb = img.find_blobs([THRESH_BLUE], roi=roi,
                            pixels_threshold=PIXELS_THRESHOLD,
                            area_threshold=AREA_THRESHOLD, merge=True)
    except Exception:
        return EMPTY
    ya = 0
    if yb:
        for b in yb:
            p = _blob_pixels(b)
            if p > ya:
                ya = p
    ba = 0
    if bb:
        for b in bb:
            p = _blob_pixels(b)
            if p > ba:
                ba = p
    if ya >= AREA_THRESHOLD and ya > ba:
        return YELLOW
    if ba >= AREA_THRESHOLD and ba > ya:
        return BLUE
    return EMPTY


def scan_board(img, rois):
    board = [[EMPTY] * 3 for _ in range(3)]
    for r in range(3):
        for c in range(3):
            board[r][c] = classify_roi(img, rois[r][c])
    return board


def flat(board2d):
    out = [EMPTY] * 9
    for r in range(3):
        for c in range(3):
            out[r * 3 + c] = board2d[r][c]
    return out


def winner_of(b):
    for a, c, d in LINES:
        if b[a] != EMPTY and b[a] == b[c] == b[d]:
            return b[a]
    return EMPTY


def is_full(b):
    return all(x != EMPTY for x in b)


def game_over_code(b):
    w = winner_of(b)
    if w == YELLOW:
        return WIN_YELLOW
    if w == BLUE:
        return WIN_BLUE
    if is_full(b):
        return WIN_DRAW
    return WIN_NONE


def minimax(b, yellow_to_move, depth, alpha, beta):
    w = winner_of(b)
    if w == YELLOW:
        return 100 - depth
    if w == BLUE:
        return depth - 100
    if is_full(b):
        return 0
    if yellow_to_move:
        best = -1000
        for i in range(9):
            if b[i] != EMPTY:
                continue
            b[i] = YELLOW
            score = minimax(b, False, depth + 1, alpha, beta)
            b[i] = EMPTY
            if score > best:
                best = score
            if score > alpha:
                alpha = score
            if beta <= alpha:
                break
        return best
    best = 1000
    for i in range(9):
        if b[i] != EMPTY:
            continue
        b[i] = BLUE
        score = minimax(b, True, depth + 1, alpha, beta)
        b[i] = EMPTY
        if score < best:
            best = score
        if score < beta:
            beta = score
        if beta <= alpha:
            break
    return best


def best_move_yellow(b):
    best_score, best_i = -1000, -1
    for i in (4, 0, 2, 6, 8, 1, 3, 5, 7):
        if b[i] != EMPTY:
            continue
        b[i] = YELLOW
        score = minimax(b, False, 0, -1000, 1000)
        b[i] = EMPTY
        if score > best_score:
            best_score, best_i = score, i
    return best_i


def best_move_blue(b):
    best_score, best_i = 1000, -1
    for i in (4, 0, 2, 6, 8, 1, 3, 5, 7):
        if b[i] != EMPTY:
            continue
        b[i] = BLUE
        score = minimax(b, True, 0, -1000, 1000)
        b[i] = EMPTY
        if score < best_score:
            best_score, best_i = score, i
    return best_i


def detect_color_moved(logic, vision, color):
    missing, extra = [], []
    for i in range(9):
        if logic[i] == color and vision[i] != color:
            missing.append(i + 1)
        if logic[i] != color and vision[i] == color and logic[i] == EMPTY:
            extra.append(i + 1)
    if len(missing) == 1 and len(extra) == 1:
        return extra[0], missing[0]
    return 0, 0


def find_new_color(logic, vision, color):
    cells = []
    for i in range(9):
        if vision[i] == color and logic[i] != color and logic[i] == EMPTY:
            cells.append(i + 1)
    if len(cells) == 1:
        return cells[0]
    return 0
