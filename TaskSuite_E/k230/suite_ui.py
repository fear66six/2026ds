# suite_ui.py — TaskSuite_E 触控主程序
# 主菜单 2x3；任务2/3 九宫格；任务4/5/6 对局+再来一局
#
# 显示/触控对齐 WonderMK 课程（01 触摸功能 / 3.多媒体）：
#   Display.JD9852 320x240 + to_ide
#   Pin(25) 打开 LCD 背光
#   TOUCH(0) 系统触控 CST328
#   MediaManager.init() 在 Display.init 之后
# I2C 与 ESP：GPIO11=SCL GPIO12=SDA addr=0x5F mem=64

import time
import gc
import os
import sys

from media.display import *
from media.media import *
import image
from machine import TOUCH, Pin

try:
    from media.sensor import Sensor
except Exception:
    Sensor = None

import game_vision as gv

# WonderMK 板载屏（课程文档）
LCD_W, LCD_H = 320, 240
LCD_BL_PIN = 25
I2C_ADDR = 0x5F
MEM_SIZE = 64
PIN_SCL, PIN_SDA, SLAVE_ID = 11, 12, 2

REG_MAGIC0, REG_MAGIC1 = 0x00, 0x01
REG_CMD, REG_ARG, REG_COLOR, REG_SLOT = 0x02, 0x03, 0x04, 0x05
REG_STATUS, REG_SEQ, REG_PHASE = 0x06, 0x07, 0x08
REG_FIRST_CELL, REG_WINNER, REG_MOVE_HINT, REG_TO_CELL = 0x09, 0x0A, 0x0B, 0x0C
REG_BOARD0 = 0x10
REG_TASK, REG_UI_CMD, REG_UI_ARG, REG_SEQ_LEN = 0x20, 0x21, 0x22, 0x23
REG_SEQ_DATA, REG_ESP_STATE, REG_UI_SEQ = 0x24, 0x30, 0x31

CMD_NOP, CMD_PICK, CMD_RESTORE = 0, 1, 2
ST_IDLE, ST_BUSY, ST_DONE, ST_ERR = 0, 1, 2, 3
PHASE_STOP, PHASE_START, PHASE_WAIT_HUMAN, PHASE_HUMAN_DONE = 0, 1, 2, 3
UI_NOP, UI_SELECT, UI_START, UI_NEXT, UI_ABORT = 0, 1, 2, 3, 4
ESP_IDLE, ESP_READY, ESP_RUNNING, ESP_WAIT, ESP_OVER, ESP_DONE = 0, 1, 2, 3, 4, 5

PAGE_MENU, PAGE_T1, PAGE_T23, PAGE_T456 = 0, 1, 2, 3
STEP_NAMES = ("Y1", "Y2", "B1", "B2")
STEP_META = (
    (gv.YELLOW, 1), (gv.YELLOW, 2), (gv.BLUE, 1), (gv.BLUE, 2),
)

_slave = None
regs = bytearray(MEM_SIZE)
_seq = 1
_ui_seq = 1
page = PAGE_MENU
task_id = 0
seq_cells = [0, 0, 0, 0]
seq_step = 0
pressed = None

# game
sensor = None
rois = None
logic_board = [gv.EMPTY] * 9
vision_2d = [[gv.EMPTY] * 3 for _ in range(3)]
_yellow_slot = 1
_blue_slot = 1
_cmd_pending = False
_awaiting_done = False
_restore_pending = False
_pending_from = 0
_pending_to = 0
_last_phase = PHASE_STOP
_last_status = ST_IDLE
_cam_on = False


def ensure_magic():
    regs[REG_MAGIC0] = ord("N")
    regs[REG_MAGIC1] = ord("X")


def push_regs():
    ensure_magic()
    _slave.writeto_mem(0, regs)


def pull_regs():
    global regs
    raw = _slave.readfrom_mem(0, MEM_SIZE)
    regs = bytearray(raw)
    if len(regs) < MEM_SIZE:
        regs.extend(bytearray(MEM_SIZE - len(regs)))
    ensure_magic()


def setup_i2c():
    global _slave, regs, _seq, _ui_seq
    from machine import FPIOA, I2C_Slave
    fpioa = FPIOA()
    try:
        fpioa.set_function(PIN_SCL, FPIOA.IIC2_SCL, pu=1)
        fpioa.set_function(PIN_SDA, FPIOA.IIC2_SDA, pu=1)
    except TypeError:
        fpioa.set_function(PIN_SCL, FPIOA.IIC2_SCL)
        fpioa.set_function(PIN_SDA, FPIOA.IIC2_SDA)
    ids = list(I2C_Slave.list())
    sid = SLAVE_ID if SLAVE_ID in ids else (ids[0] if ids else None)
    if sid is None:
        raise RuntimeError("no I2C slave")
    _slave = I2C_Slave(sid, addr=I2C_ADDR, mem_size=MEM_SIZE)
    regs = bytearray(MEM_SIZE)
    ensure_magic()
    regs[REG_STATUS] = ST_IDLE
    regs[REG_ESP_STATE] = ESP_READY
    regs[REG_TASK] = 0
    _seq = 1
    _ui_seq = 1
    push_regs()
    print("I2C slave OK id=%s" % sid)


def bump_ui():
    global _ui_seq
    _ui_seq = (_ui_seq + 1) & 0xFF
    if _ui_seq == 0:
        _ui_seq = 1


def bump_arm():
    global _seq
    _seq = (_seq + 1) & 0xFF
    if _seq == 0:
        _seq = 1


def issue_ui(cmd, arg=0):
    pull_regs()
    regs[REG_UI_CMD] = cmd
    regs[REG_UI_ARG] = arg
    regs[REG_UI_SEQ] = _ui_seq
    bump_ui()
    push_regs()
    print("[UI] cmd=%u arg=%u" % (cmd, arg))


def write_task(tid):
    pull_regs()
    regs[REG_TASK] = tid
    push_regs()


def write_sequence():
    pull_regs()
    regs[REG_SEQ_LEN] = 4
    for i in range(4):
        color, slot = STEP_META[i]
        cell = seq_cells[i]
        regs[REG_SEQ_DATA + i * 3 + 0] = color
        regs[REG_SEQ_DATA + i * 3 + 1] = slot
        regs[REG_SEQ_DATA + i * 3 + 2] = cell
    push_regs()
    print("[UI] seq cells=", seq_cells)


def issue_pick(cell, color, slot):
    global _cmd_pending, _awaiting_done, _restore_pending
    pull_regs()
    regs[REG_ARG] = cell
    regs[REG_COLOR] = color
    regs[REG_SLOT] = slot
    regs[REG_TO_CELL] = 0
    regs[REG_SEQ] = _seq
    regs[REG_STATUS] = ST_IDLE
    regs[REG_CMD] = CMD_PICK
    bump_arm()
    push_regs()
    _cmd_pending = True
    _awaiting_done = True
    _restore_pending = False
    print("[GAME] PICK c=%d slot=%d cell=%d" % (color, slot, cell))


def issue_restore(frm, to):
    global _cmd_pending, _awaiting_done, _restore_pending, _pending_from, _pending_to
    pull_regs()
    regs[REG_ARG] = frm
    regs[REG_COLOR] = gv.YELLOW
    regs[REG_SLOT] = 0
    regs[REG_TO_CELL] = to
    regs[REG_SEQ] = _seq
    regs[REG_STATUS] = ST_IDLE
    regs[REG_CMD] = CMD_RESTORE
    bump_arm()
    push_regs()
    _pending_from, _pending_to = frm, to
    _cmd_pending = True
    _awaiting_done = True
    _restore_pending = True
    print("[GAME] RESTORE %d->%d" % (frm, to))


# ---------- UI geometry（随 LCD_W/H 自适应） ----------
def menu_rects():
    title_h = 28 if LCD_H <= 240 else 40
    gap_x, gap_y = (6, 6) if LCD_W <= 320 else (30, 30)
    usable_w = LCD_W - 12
    usable_h = LCD_H - title_h - 8
    mw = (usable_w - 2 * gap_x) // 3
    mh = (usable_h - gap_y) // 2
    ox = (LCD_W - (3 * mw + 2 * gap_x)) // 2
    oy = title_h
    rs = []
    for r in range(2):
        for c in range(3):
            n = r * 3 + c + 1
            x = ox + c * (mw + gap_x)
            y = oy + r * (mh + gap_y)
            rs.append((n, x, y, mw, mh))
    return rs


def grid_rects():
    gap = 4 if LCD_W <= 320 else 12
    top = 40 if LCD_H <= 240 else 70
    bot = 44 if LCD_H <= 240 else 70
    s = min((LCD_W - 2 * gap) // 3, (LCD_H - top - bot - 2 * gap) // 3)
    total = 3 * s + 2 * gap
    ox = (LCD_W - total) // 2
    oy = top
    rs = []
    for r in range(3):
        for c in range(3):
            cell = r * 3 + c + 1
            x = ox + c * (s + gap)
            y = oy + r * (s + gap)
            rs.append((cell, x, y, s, s))
    return rs


def btn(x, y, w, h):
    return (x, y, w, h)


def _layout_buttons():
    """按分辨率生成底部按钮热区（320x240 加大便于点中）。"""
    bh = 44 if LCD_H <= 240 else 60
    by = LCD_H - bh - 2
    if LCD_W <= 320:
        bw = 90
        gap = 8
        return {
            "BACK": btn(4, by, bw, bh),
            "CLEAR": btn((LCD_W - bw) // 2, by, bw, bh),
            "START": btn(LCD_W - bw - 4, by, bw, bh),
            "NEXT": btn(LCD_W - bw - 4, by, bw, bh),
        }
    return {
        "BACK": btn(40, by, 160, bh),
        "CLEAR": btn(220, by, 160, bh),
        "START": btn(LCD_W - 220, by, 200, bh),
        "NEXT": btn(LCD_W - 220, by, 200, bh),
    }


_BTNS = None
_media_inited = False
_lcd_bl = None  # 必须全局持有，否则 gc 后 GPIO25 掉电，屏会闪一下就灭


def btns():
    global _BTNS
    if _BTNS is None:
        _BTNS = _layout_buttons()
    return _BTNS


def hit(px, py, box, pad=6):
    """命中检测；pad 放大热区，小屏更易点中。"""
    x, y, w, h = box
    return (x - pad) <= px < (x + w + pad) and (y - pad) <= py < (y + h + pad)


def map_touch_xy(tx, ty):
    """
    《01 触摸功能课程》：Touch 坐标系 → image 坐标系
      x = x
      y = DISPLAY_HEIGHT - y
    """
    x = int(tx)
    y = int(LCD_H) - int(ty)
    if x < 0:
        x = 0
    elif x >= LCD_W:
        x = LCD_W - 1
    if y < 0:
        y = 0
    elif y >= LCD_H:
        y = LCD_H - 1
    return x, y


# 课程 event: 0 none / 1 up / 2 down / 3 move
EVT_NONE, EVT_UP, EVT_DOWN, EVT_MOVE = 0, 1, 2, 3
_last_tap_ms = 0
TAP_DEBOUNCE_MS = 280


def draw_button(img, box, text, fill=(40, 80, 140)):
    x, y, w, h = box
    fs = 16 if LCD_H <= 240 else 28
    img.draw_rectangle(x, y, w, h, color=fill, fill=True)
    img.draw_rectangle(x, y, w, h, color=(220, 220, 220), thickness=1)
    try:
        img.draw_string_advanced(x + 6, y + max(4, (h - fs) // 2), fs, text, color=(255, 255, 255))
    except Exception:
        pass


def _fs(big=False):
    if LCD_H <= 240:
        return 18 if big else 14
    return 36 if big else 24


def render(img):
    img.clear()
    b = btns()
    if page == PAGE_MENU:
        try:
            img.draw_string_advanced(8, 4, _fs(True), "TaskSuite E 1-6", color=(255, 220, 80))
        except Exception:
            pass
        for n, x, y, w, h in menu_rects():
            fill = (60, 60, 100)
            if pressed == ("m", n):
                fill = (100, 140, 60)
            img.draw_rectangle(x, y, w, h, color=fill, fill=True)
            img.draw_rectangle(x, y, w, h, color=(200, 200, 200), thickness=2)
            try:
                ns = _fs(True) + 8
                img.draw_string_advanced(x + w // 2 - ns // 3, y + h // 2 - ns // 2, ns, str(n),
                                         color=(255, 255, 255))
            except Exception:
                pass
    elif page == PAGE_T1:
        pull_regs()
        st = regs[REG_ESP_STATE]
        try:
            img.draw_string_advanced(8, 8, _fs(True), "T1: Y->Cell5", color=(255, 255, 100))
            if st == ESP_RUNNING:
                img.draw_string_advanced(8, 40, _fs(), "Running...", color=(180, 255, 180))
            elif st == ESP_DONE:
                img.draw_string_advanced(8, 40, _fs(), "DONE — BACK", color=(100, 255, 100))
            else:
                img.draw_string_advanced(8, 40, _fs(), "Touch START", color=(200, 200, 200))
        except Exception:
            pass
        if st != ESP_RUNNING:
            draw_button(img, b["START"], "START")
        draw_button(img, b["BACK"], "BACK", (100, 60, 60))
    elif page == PAGE_T23:
        pull_regs()
        st = regs[REG_ESP_STATE]
        try:
            img.draw_string_advanced(8, 4, _fs(True), "T%d Y1Y2B1B2" % task_id, color=(255, 255, 100))
            if st == ESP_RUNNING:
                img.draw_string_advanced(8, 24, _fs(), "Running...", color=(180, 255, 180))
            elif st == ESP_DONE:
                img.draw_string_advanced(8, 24, _fs(), "DONE", color=(100, 255, 100))
            else:
                img.draw_string_advanced(8, 24, _fs(), "%s %s" %
                                         (STEP_NAMES[min(seq_step, 3)], seq_cells),
                                         color=(180, 220, 255))
        except Exception:
            pass
        for cell, x, y, w, h in grid_rects():
            fill = (50, 70, 50)
            for i, c in enumerate(seq_cells):
                if c == cell:
                    fill = (180, 140, 40) if i < 2 else (40, 80, 180)
            if pressed == ("g", cell):
                fill = (120, 180, 80)
            img.draw_rectangle(x, y, w, h, color=fill, fill=True)
            img.draw_rectangle(x, y, w, h, color=(230, 230, 230), thickness=1)
            try:
                ns = min(28, w // 2)
                img.draw_string_advanced(x + w // 2 - ns // 3, y + h // 2 - ns // 2, ns, str(cell),
                                         color=(255, 255, 255))
            except Exception:
                pass
        draw_button(img, b["CLEAR"], "CLR", (90, 90, 50))
        if st != ESP_RUNNING:
            draw_button(img, b["START"], "START")
        draw_button(img, b["BACK"], "BACK", (100, 60, 60))
    elif page == PAGE_T456:
        pull_regs()
        st = regs[REG_ESP_STATE]
        names = {ESP_READY: "ready", ESP_RUNNING: "running", ESP_WAIT: "wait KEY2",
                 ESP_OVER: "GAME OVER", ESP_DONE: "done"}
        try:
            img.draw_string_advanced(8, 8, _fs(True), "Task %d" % task_id, color=(255, 255, 100))
            img.draw_string_advanced(8, 36, _fs(), "state: %s" % names.get(st, str(st)),
                                     color=(200, 220, 255))
            img.draw_string_advanced(8, 58, _fs(), "KEY2=human done", color=(180, 180, 180))
        except Exception:
            pass
        if st == ESP_OVER:
            draw_button(img, b["NEXT"], "NEXT", (40, 120, 60))
        else:
            draw_button(img, b["START"], "START")
        draw_button(img, b["BACK"], "BACK", (100, 60, 60))


def on_tap(px, py):
    global page, task_id, seq_step, seq_cells, pressed
    global logic_board, _yellow_slot, _blue_slot, _last_phase

    b = btns()
    if page == PAGE_MENU:
        for n, x, y, w, h in menu_rects():
            if hit(px, py, (x, y, w, h)):
                task_id = n
                write_task(n)
                issue_ui(UI_SELECT, n)
                if n == 1:
                    page = PAGE_T1
                elif n in (2, 3):
                    seq_cells = [0, 0, 0, 0]
                    seq_step = 0
                    page = PAGE_T23
                else:
                    page = PAGE_T456
                    stop_camera()
                return

    elif page == PAGE_T1:
        if hit(px, py, b["BACK"]):
            issue_ui(UI_ABORT, 0)
            page = PAGE_MENU
            task_id = 0
            return
        if hit(px, py, b["START"]):
            issue_ui(UI_START, 1)
            return

    elif page == PAGE_T23:
        if hit(px, py, b["BACK"]):
            issue_ui(UI_ABORT, 0)
            page = PAGE_MENU
            return
        if hit(px, py, b["CLEAR"]):
            seq_cells = [0, 0, 0, 0]
            seq_step = 0
            return
        if hit(px, py, b["START"]):
            if 0 in seq_cells:
                print("[UI] need 4 cells")
                return
            write_sequence()
            issue_ui(UI_START, task_id)
            return
        if seq_step < 4:
            for cell, x, y, w, h in grid_rects():
                if hit(px, py, (x, y, w, h)):
                    seq_cells[seq_step] = cell
                    seq_step += 1
                    return

    elif page == PAGE_T456:
        if hit(px, py, b["BACK"]):
            stop_camera()
            issue_ui(UI_ABORT, 0)
            page = PAGE_MENU
            return
        pull_regs()
        st = regs[REG_ESP_STATE]
        if st == ESP_OVER and hit(px, py, b["NEXT"]):
            issue_ui(UI_NEXT, task_id)
            reset_game_state()
            start_camera()
            return
        if hit(px, py, b["START"]):
            issue_ui(UI_START, task_id)
            reset_game_state()
            start_camera()
            return


def lcd_backlight_on():
    """
    课程：显示前打开 GPIO25 背光。
    Pin 对象必须长期持有，否则 MicroPython gc 后引脚释放 → 背光灭（闪一下就黑）。
    """
    global _lcd_bl
    try:
        if _lcd_bl is None:
            _lcd_bl = Pin(LCD_BL_PIN, Pin.OUT, pull=Pin.PULL_NONE, drive=7)
        _lcd_bl.value(1)
        print("LCD backlight Pin(%d)=1" % LCD_BL_PIN)
        return _lcd_bl
    except Exception as e:
        print("backlight fail:", e)
        return None


def init_display():
    """
    对齐《01 触摸功能课程》《3.多媒体课程》：
      Display.init(Display.JD9852, width=320, height=240, to_ide=True)
      MediaManager.init()
      Pin(25) 背光 = 1（全程保持）
    """
    global LCD_W, LCD_H, _BTNS, _media_inited
    _BTNS = None
    LCD_W, LCD_H = 320, 240
    try:
        Display.init(Display.JD9852, width=LCD_W, height=LCD_H, to_ide=True)
        print("Display OK JD9852 %dx%d" % (LCD_W, LCD_H))
    except Exception as e:
        print("JD9852 fail:", e)
        try:
            Display.deinit()
        except Exception:
            pass
        try:
            LCD_W, LCD_H = 240, 320
            Display.init(Display.JD9852, width=LCD_W, height=LCD_H, to_ide=True)
            print("Display OK JD9852 %dx%d" % (LCD_W, LCD_H))
        except Exception as e2:
            print("JD9852 portrait fail:", e2)
            LCD_W, LCD_H = 320, 240
            Display.init(Display.VIRT, width=LCD_W, height=LCD_H, fps=30, to_ide=True)
            print("Display VIRT fallback")

    MediaManager.init()
    _media_inited = True
    print("MediaManager.init")
    lcd_backlight_on()


def ensure_media():
    global _media_inited
    if _media_inited:
        return
    MediaManager.init()
    _media_inited = True


def reset_game_state():
    global logic_board, _yellow_slot, _blue_slot, _cmd_pending
    global _awaiting_done, _restore_pending, _last_phase, _last_status
    logic_board = [gv.EMPTY] * 9
    _yellow_slot = 1
    _blue_slot = 1
    _cmd_pending = False
    _awaiting_done = False
    _restore_pending = False
    _last_phase = PHASE_STOP
    _last_status = ST_IDLE


def start_camera():
    global sensor, rois, _cam_on
    if _cam_on or Sensor is None:
        return
    try:
        ensure_media()
        sensor = Sensor(width=gv.DETECT_W, height=gv.DETECT_H)
        sensor.reset()
        sensor.set_framesize(width=gv.DETECT_W, height=gv.DETECT_H)
        sensor.set_pixformat(Sensor.RGB565)
        sensor.run()
        rois = gv.build_rois()
        _cam_on = True
        print("camera on")
    except Exception as e:
        print("camera fail", e)
        _cam_on = False


def stop_camera():
    global sensor, _cam_on
    if not _cam_on:
        return
    try:
        if sensor:
            sensor.stop()
    except Exception:
        pass
    sensor = None
    _cam_on = False


def game_tick():
    """任务4/5/6：PHASE 边沿 + STATUS DONE"""
    global logic_board, vision_2d, _last_phase, _last_status
    global _cmd_pending, _awaiting_done, _restore_pending
    global _yellow_slot, _blue_slot

    if not _cam_on or sensor is None or rois is None:
        return

    try:
        img = sensor.snapshot()
        vision_2d = gv.scan_board(img, rois)
    except Exception:
        return

    pull_regs()
    flat = gv.flat(vision_2d)
    for i in range(9):
        regs[REG_BOARD0 + i] = flat[i]

    phase = regs[REG_PHASE]
    st = regs[REG_STATUS]

    if phase != _last_phase:
        print("[GAME] PHASE %d->%d task=%d" % (_last_phase, phase, task_id))
        if phase == PHASE_START:
            logic_board = [gv.EMPTY] * 9
            _yellow_slot = 1
            _blue_slot = 1
            _cmd_pending = False
            _awaiting_done = False
            regs[REG_WINNER] = gv.WIN_NONE
            regs[REG_CMD] = CMD_NOP
            if task_id == 5:
                print("[GAME] T5 wait human yellow")
            else:
                # T4/T6 machine yellow first cell5
                first = regs[REG_FIRST_CELL]
                if first < 1 or first > 9:
                    first = 5
                logic_board[first - 1] = gv.YELLOW
                issue_pick(first, gv.YELLOW, _yellow_slot)
                _yellow_slot = min(5, _yellow_slot + 1)
        elif phase == PHASE_HUMAN_DONE:
            if not (_awaiting_done or _cmd_pending):
                handle_human_done(flat)
        _last_phase = phase

    if st != _last_status:
        if st == ST_DONE and _awaiting_done:
            print("[GAME] DONE")
            _cmd_pending = False
            _awaiting_done = False
            regs[REG_CMD] = CMD_NOP
            if _restore_pending:
                _restore_pending = False
                if _pending_from >= 1:
                    logic_board[_pending_from - 1] = gv.EMPTY
                if _pending_to >= 1:
                    logic_board[_pending_to - 1] = gv.YELLOW
            else:
                code = gv.game_over_code(logic_board)
                regs[REG_WINNER] = code
        _last_status = st

    push_regs()


def handle_human_done(flat):
    global logic_board, _yellow_slot, _blue_slot

    # T4/T6: restore yellow move first
    if task_id in (4, 6):
        frm, to = gv.detect_color_moved(logic_board, flat, gv.YELLOW)
        if frm:
            issue_restore(frm, to)
            return
        blue = gv.find_new_color(logic_board, flat, gv.BLUE)
        if blue == 0:
            print("[GAME] no blue")
            return
        logic_board[blue - 1] = gv.BLUE
        code = gv.game_over_code(logic_board)
        if code != gv.WIN_NONE:
            regs[REG_WINNER] = code
            push_regs()
            return
        mi = gv.best_move_yellow(logic_board)
        if mi < 0:
            regs[REG_WINNER] = gv.WIN_DRAW
            push_regs()
            return
        logic_board[mi] = gv.YELLOW
        issue_pick(mi + 1, gv.YELLOW, _yellow_slot)
        _yellow_slot = min(5, _yellow_slot + 1)
        return

    # T5: human yellow, AI blue
    if task_id == 5:
        yel = gv.find_new_color(logic_board, flat, gv.YELLOW)
        if yel == 0:
            print("[GAME] no yellow")
            return
        logic_board[yel - 1] = gv.YELLOW
        code = gv.game_over_code(logic_board)
        if code != gv.WIN_NONE:
            regs[REG_WINNER] = code
            push_regs()
            return
        mi = gv.best_move_blue(logic_board)
        if mi < 0:
            regs[REG_WINNER] = gv.WIN_DRAW
            push_regs()
            return
        logic_board[mi] = gv.BLUE
        issue_pick(mi + 1, gv.BLUE, _blue_slot)
        _blue_slot = min(5, _blue_slot + 1)


def try_fire_tap(x, y, ev):
    """课程拍照例：按钮在 down(event==2) 时触发；带去抖防连点。"""
    global _last_tap_ms, pressed
    if ev != EVT_DOWN:
        return
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_tap_ms) < TAP_DEBOUNCE_MS:
        return
    _last_tap_ms = now
    pressed = ("tap",)
    print("[TOUCH] tap xy=(%d,%d) ev=%d" % (x, y, ev))
    try:
        on_tap(x, y)
    except Exception as e:
        print("on_tap err:", e)


def main():
    global pressed, _media_inited, _lcd_bl
    print("======== TaskSuite_E UI ========")
    try:
        setup_i2c()
    except Exception as e:
        print("I2C fail", e)
        while True:
            time.sleep_ms(2000)

    # 课程顺序：Display.JD9852 → MediaManager → 背光 Pin25 → TOUCH(0) → RGB565
    init_display()
    tp = TOUCH(0)  # CST328
    img = image.Image(LCD_W, LCD_H, image.RGB565)

    frame = 0
    print("UI ready LCD=%dx%d touch=TOUCH(0) Y-flip=on" % (LCD_W, LCD_H))

    try:
        while True:
            try:
                os.exitpoint()
            except Exception:
                pass

            if _lcd_bl is not None and (frame & 0x1F) == 0:
                try:
                    _lcd_bl.value(1)
                except Exception:
                    pass

            # 课程：p = tp.read(1)
            pts = ()
            try:
                pts = tp.read(1)
            except Exception:
                pts = ()

            pressed = None
            if pts != ():
                point = pts[0]
                raw_x = point.x
                raw_y = point.y
                ev = getattr(point, "event", EVT_DOWN)
                # 课程：Touch → image 坐标（Y 轴翻转）
                x, y = map_touch_xy(raw_x, raw_y)
                if (frame & 0x0F) == 0:
                    print("[TOUCH] raw=(%d,%d) map=(%d,%d) ev=%d" %
                          (raw_x, raw_y, x, y, ev))
                # down/move 高亮；down/up 触发按键
                if ev == EVT_DOWN or ev == EVT_MOVE:
                    pressed = ("tap",)
                try_fire_tap(x, y, ev)

            if page == PAGE_T456 and _cam_on:
                try:
                    game_tick()
                except Exception as e:
                    print("game_tick err:", e)

            try:
                render(img)
                # 若本帧有触点，再叠十字（render 会 clear，放在 render 后）
                if pts != ():
                    point = pts[0]
                    x, y = map_touch_xy(point.x, point.y)
                    try:
                        img.draw_cross(x, y, color=(255, 60, 60), size=8, thickness=2)
                    except Exception:
                        pass
                Display.show_image(img)
            except Exception as e:
                print("draw err:", e)
                sys.print_exception(e)
                time.sleep_ms(200)

            frame += 1
            if (frame % 60) == 0:
                gc.collect()
            time.sleep_ms(50)  # 课程触摸例约 50ms
    except KeyboardInterrupt:
        print("stop")
    except Exception as e:
        print("main loop fatal:", e)
        sys.print_exception(e)
        try:
            if _lcd_bl is not None:
                _lcd_bl.value(1)
        except Exception:
            pass
        while True:
            time.sleep_ms(1000)
    finally:
        stop_camera()
        try:
            Display.deinit()
        except Exception:
            pass
        try:
            if _media_inited:
                MediaManager.deinit()
        except Exception:
            pass
        _media_inited = False


if __name__ == "__main__":
    main()
