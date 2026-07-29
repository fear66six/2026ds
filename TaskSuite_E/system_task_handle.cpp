#include "system_task_handle.h"
#include "Robot_Arm.h"
#include "CamPickRunner.h"
#include "SuiteI2C.h"
#include "suite_config.h"
#include "board_roi_config.h"
#include <Wire.h>
#include <string.h>

namespace {

CommProtocol_t at32_protocol;
SuiteI2C suite_i2c;  /* 勿命名为 link：与 unistd.h::link() 冲突 */

uint32_t last_bat_ms = 0;
uint32_t last_status_ms = 0;
uint32_t last_i2c_ms = 0;
uint32_t last_servo_fb_ms = 0;
int16_t last_servo_pos[6] = {2048, 2048, 2048, 2048, 2048, 2048};

bool k230_ok = false;
bool job_started = false;
bool job_finished = false;
bool waiting_human = false;
uint8_t active_task = 0;
uint8_t last_job_kind = 0;
uint8_t last_cell = 0;
uint8_t last_color = 0;
uint8_t last_from = 0;
uint8_t progress_steps = 0;
uint32_t ignore_winner_until = 0;
uint32_t human_timer_ms = 0;

SuiteI2C::SeqStep seq_buf[4];
uint8_t seq_len = 0;
uint8_t seq_idx = 0;
bool seq_active = false;

uint8_t local_board[9] = {0};

enum SuitePhase : uint8_t {
    SP_WAIT_K230 = 0,
    SP_MENU,
    SP_TASK_IDLE,   /* 已选任务，等 START */
    SP_RUNNING,
    SP_GAME_OVER,
    SP_DONE,
};
SuitePhase sp = SP_WAIT_K230;

constexpr uint32_t I2C_MS = 80;
constexpr uint32_t BAT_MS = 200;
constexpr uint32_t STATUS_MS = 500;

void update_pose(PacketTypeDef* rx)
{
    if (rx->elements.length < 14) return;
    int16_t raw_x = (int16_t)((rx->elements.args[1] << 8) | rx->elements.args[0]);
    int16_t raw_y = (int16_t)((rx->elements.args[3] << 8) | rx->elements.args[2]);
    int16_t raw_z = (int16_t)((rx->elements.args[5] << 8) | rx->elements.args[4]);
    int16_t raw_pitch = (int16_t)((rx->elements.args[7] << 8) | rx->elements.args[6]);
    int16_t raw_roll = (int16_t)((rx->elements.args[9] << 8) | rx->elements.args[8]);
    int16_t raw_claw = (int16_t)((rx->elements.args[11] << 8) | rx->elements.args[10]);
    arm.current_pose.x = (float)raw_x;
    arm.current_pose.y = (float)raw_y;
    arm.current_pose.z = (float)raw_z;
    arm.current_pose.pitch = (float)raw_pitch / 10.0f;
    arm.current_pose.roll = (float)raw_roll;
    arm.current_pose.claw = (float)raw_claw;
    if (rx->elements.cmd == CMD_GET_CUR_COORDS && rx->elements.length >= 26) {
        for (int i = 0; i < 6; ++i) {
            int idx = 12 + i * 2;
            last_servo_pos[i] =
                (int16_t)((rx->elements.args[idx + 1] << 8) | rx->elements.args[idx]);
        }
        last_servo_fb_ms = millis();
    }
}

void show_oled(const char* a, const char* b = "")
{
    arm.board.oled.set_custom_text(0, "TaskSuite E");
    char tline[20];
    snprintf(tline, sizeof(tline), "T%u", active_task);
    arm.board.oled.set_custom_text(1, a);
    arm.board.oled.set_custom_text(2, b);
    arm.board.oled.set_custom_text(3, k230_ok ? tline : "K230?");
    arm.board.oled.show_custom();
}

void move_observe()
{
    show_oled("Homing...", "");
    arm.set_torque(true);
    arm.move(OBS_X, OBS_Y, 200.0f, OBS_PITCH, OBS_ROLL, OBS_CLAW, 1500);
    delay(1700);
    arm.move(OBS_X, OBS_Y, OBS_Z, OBS_PITCH, OBS_ROLL, OBS_CLAW, OBS_MOVE_MS);
    delay(OBS_MOVE_MS + 200);
    sync_arm_feedback(300);
}

void enter_menu()
{
    cam_pick.setCalibProfile(0);
    sp = SP_MENU;
    active_task = 0;
    waiting_human = false;
    job_started = false;
    job_finished = false;
    seq_active = false;
    progress_steps = 0;
    suite_i2c.setPhase(SuiteI2C::PHASE_STOP);
    suite_i2c.setStatus(SuiteI2C::ST_IDLE);
    suite_i2c.clearWinner();
    suite_i2c.setEspState(SuiteI2C::ESP_READY_MENU);
    show_oled("MENU", "touch 1-6");
    Serial.println(F("[Suite] MENU — wait touch select"));
}

void start_pick(uint8_t color, uint8_t slot, uint8_t cell)
{
    if (job_started && !job_finished) return;
    if (color != PIECE_YELLOW && color != PIECE_BLUE) color = PIECE_YELLOW;
    if (slot < 1 || slot > 5) slot = 1;
    if (cell < 1 || cell > 9) cell = 5;
    waiting_human = false;
    suite_i2c.setStatus(SuiteI2C::ST_BUSY);
    cam_pick.requestPickPlace(color, slot, cell);
    job_started = true;
    job_finished = false;
    last_job_kind = 1;
    last_cell = cell;
    last_color = color;
    Serial.printf("[Suite] PICK color=%u slot=%u cell=%u\n", color, slot, cell);
    show_oled("Picking", "");
}

void start_restore(uint8_t from, uint8_t to, uint8_t color)
{
    if (job_started && !job_finished) return;
    waiting_human = false;
    suite_i2c.setStatus(SuiteI2C::ST_BUSY);
    cam_pick.requestBoardMove(from, to, color);
    job_started = true;
    job_finished = false;
    last_job_kind = 2;
    last_from = from;
    last_cell = to;
    last_color = color;
    Serial.printf("[Suite] RESTORE %u->%u\n", from, to);
    show_oled("Restore", "");
}

void begin_seq_from_ui()
{
    /* 任务3：旋转盘标定；任务2：正放盘 */
    cam_pick.setCalibProfile(active_task == 3 ? 1 : 0);
    seq_len = 0;
    if (!suite_i2c.readSequence(seq_buf, 4, seq_len) || seq_len == 0) {
        Serial.println(F("[Suite] empty sequence"));
        suite_i2c.setEspState(SuiteI2C::ESP_DONE_OK);
        sp = SP_DONE;
        show_oled("No seq", "BACK");
        return;
    }
    seq_idx = 0;
    seq_active = true;
    sp = SP_RUNNING;
    suite_i2c.setEspState(SuiteI2C::ESP_RUNNING);
    Serial.printf("[Suite] SEQ T%u start len=%u\n", active_task, seq_len);
    start_pick(seq_buf[0].color, seq_buf[0].slot, seq_buf[0].cell);
}

void begin_task1()
{
    cam_pick.setCalibProfile(0);
    seq_active = false;
    sp = SP_RUNNING;
    suite_i2c.setEspState(SuiteI2C::ESP_RUNNING);
    start_pick(PIECE_YELLOW, SUITE_TASK1_SLOT, SUITE_TASK1_CELL);
}

void begin_game_task()
{
    /* 4=机先黄 5=人先黄 6=机先黄+复位 */
    cam_pick.setCalibProfile(0);
    memset(local_board, 0, sizeof(local_board));
    waiting_human = false;
    progress_steps = 0;
    job_started = false;
    job_finished = false;
    seq_active = false;
    sp = SP_RUNNING;
    suite_i2c.clearWinner();
    suite_i2c.setStatus(SuiteI2C::ST_IDLE);
    suite_i2c.setEspState(SuiteI2C::ESP_RUNNING);
    ignore_winner_until = millis() + 800;

    if (active_task == 5) {
        suite_i2c.setFirstCell(0);
        suite_i2c.setPhase(SuiteI2C::PHASE_START);
        waiting_human = true;
        suite_i2c.setEspState(SuiteI2C::ESP_WAIT_HUMAN);
        show_oled("T5 human", "KEY2");
        Serial.println(F("[Suite] T5 START human first"));
    } else {
        suite_i2c.setFirstCell(5);
        suite_i2c.setPhase(SuiteI2C::PHASE_START);
        show_oled(active_task == 6 ? "T6 play" : "T4 play", "AI...");
        Serial.printf("[Suite] T%u START machine first\n", active_task);
    }
}

void on_game_over(uint8_t w)
{
    sp = SP_GAME_OVER;
    waiting_human = false;
    suite_i2c.setPhase(SuiteI2C::PHASE_STOP);
    suite_i2c.setEspState(SuiteI2C::ESP_GAME_OVER);
    const char* msg = "DRAW";
    if (w == SuiteI2C::WIN_YELLOW) msg = "Y WIN";
    else if (w == SuiteI2C::WIN_BLUE) msg = "B WIN";
    show_oled("GAME OVER", msg);
    Serial.printf("[Suite] GAME OVER %u — touch Next\n", w);
    arm.board.buzzer.set(150, 100, 3, 2000);
}

void on_job_done()
{
    job_finished = true;
    suite_i2c.setStatus(SuiteI2C::ST_DONE);
    progress_steps++;

    if (last_job_kind == 2) {
        Serial.printf("[Suite] restore done %u->%u\n", last_from, last_cell);
        waiting_human = true;
        suite_i2c.setPhase(SuiteI2C::PHASE_WAIT_HUMAN);
        suite_i2c.setEspState(SuiteI2C::ESP_WAIT_HUMAN);
        show_oled("Restored", "KEY2");
        return;
    }

    if (last_cell >= 1 && last_cell <= 9) {
        local_board[last_cell - 1] = last_color;
    }
    Serial.printf("[Suite] place done cell=%u\n", last_cell);

    if (seq_active) {
        if (seq_idx + 1 < seq_len) {
            seq_idx++;
            delay(400);
            start_pick(seq_buf[seq_idx].color, seq_buf[seq_idx].slot, seq_buf[seq_idx].cell);
            return;
        }
        seq_active = false;
        sp = SP_DONE;
        suite_i2c.setEspState(SuiteI2C::ESP_DONE_OK);
        show_oled("DONE", "touch BACK");
        Serial.println(F("[Suite] sequence complete"));
        arm.board.buzzer.set(120, 80, 3, 2000);
        return;
    }

    if (active_task == 1) {
        sp = SP_DONE;
        suite_i2c.setEspState(SuiteI2C::ESP_DONE_OK);
        show_oled("T1 DONE", "BACK");
        arm.board.buzzer.set(120, 80, 2, 2000);
        return;
    }

    /* 对弈任务 */
    uint8_t w = 0;
    if (suite_i2c.readWinner(w) && w != SuiteI2C::WIN_NONE) {
        on_game_over(w);
        return;
    }
    waiting_human = true;
    suite_i2c.setPhase(SuiteI2C::PHASE_WAIT_HUMAN);
    suite_i2c.setEspState(SuiteI2C::ESP_WAIT_HUMAN);
    show_oled("WAIT", "KEY2");
    arm.board.buzzer.set(100, 70, 2, 2000);
}

void handle_ui()
{
    uint8_t ucmd = 0, uarg = 0;
    if (!suite_i2c.pollUiCommand(ucmd, uarg)) return;

    Serial.printf("[Suite] UI cmd=%u arg=%u\n", ucmd, uarg);

    if (ucmd == SuiteI2C::UI_SELECT_TASK) {
        if (uarg < 1 || uarg > 6) return;
        if (sp == SP_RUNNING && (job_started && !job_finished)) {
            Serial.println(F("[Suite] busy, ignore SELECT"));
            return;
        }
        active_task = uarg;
        sp = SP_TASK_IDLE;
        suite_i2c.setEspState(SuiteI2C::ESP_READY_MENU);
        char b[12];
        snprintf(b, sizeof(b), "T%u ready", active_task);
        show_oled(b, "START");
        Serial.printf("[Suite] selected task %u\n", active_task);
        return;
    }

    if (ucmd == SuiteI2C::UI_ABORT_HOME) {
        enter_menu();
        move_observe();
        return;
    }

    if (ucmd == SuiteI2C::UI_START) {
        if (sp == SP_RUNNING) {
            Serial.println(F("[Suite] running, ignore START"));
            return;
        }
        if (active_task == 0) {
            suite_i2c.readTaskId(active_task);
        }
        if (active_task == 1) {
            begin_task1();
        } else if (active_task == 2 || active_task == 3) {
            begin_seq_from_ui();
        } else if (active_task >= 4 && active_task <= 6) {
            begin_game_task();
        }
        return;
    }

    if (ucmd == SuiteI2C::UI_NEXT_GAME) {
        if (sp == SP_GAME_OVER && active_task >= 4 && active_task <= 6) {
            begin_game_task();
        }
        return;
    }
}

} // namespace

void at32_packet_callback(PacketTypeDef* rx_packet)
{
    if (rx_packet->elements.id != 0x5A) return;
    switch (rx_packet->elements.cmd) {
        case CMD_GET_CUR_COORDS:
        case CMD_IKINE_RESULT_GET:
            update_pose(rx_packet);
            break;
        default:
            break;
    }
}

void pump_at32_feedback(void)
{
    while (servo.uart->available()) {
        uint8_t c = servo.uart->read();
        at32_protocol.parsing(&c, 1);
    }
}

bool sync_arm_feedback(uint32_t timeout_ms)
{
    arm.update_status();
    uint32_t start = millis();
    uint32_t prev = last_servo_fb_ms;
    while (millis() - start < timeout_ms) {
        pump_at32_feedback();
        if (last_servo_fb_ms != 0 && last_servo_fb_ms != prev) return true;
        delay(2);
    }
    return last_servo_fb_ms != 0;
}

bool get_last_servo_positions(int16_t out_pos[6])
{
    if (last_servo_fb_ms == 0) return false;
    memcpy(out_pos, last_servo_pos, sizeof(last_servo_pos));
    return true;
}

void register_system_task(esp_event_loop_handle_t *event_loop)
{
    (void)event_loop;
    setCpuFrequencyMhz(240);
    Serial.begin(115200);
    servo.begin(Serial1, 1000000, 16, 17);
    arm.begin();
    arm.set_torque(true);
    at32_protocol.begin();
    at32_protocol.register_success_callback(at32_packet_callback);
    delay(500);
    move_observe();
    cam_pick.begin();
    Wire1.setClock(100000);
    delay(50);
    k230_ok = suite_i2c.begin();
    Serial.printf("[I2C] K230 %s\n", k230_ok ? "OK" : "FAIL");
    Serial.println(F("======== TaskSuite_E ========"));
    if (k230_ok) enter_menu();
    else {
        sp = SP_WAIT_K230;
        show_oled("No K230", "run UI");
    }
}

void system_loop_handler(void)
{
    pump_at32_feedback();
    arm.board.buzzer.update();
    arm.board.button.update();
    cam_pick.update();

    if (job_started && !job_finished && sp == SP_RUNNING) {
        if (cam_pick.isDone()) on_job_done();
        else if (cam_pick.hasError()) {
            job_finished = true;
            suite_i2c.setStatus(SuiteI2C::ST_ERR);
            show_oled("ERR", "");
        }
    }

    uint32_t now = millis();
    if (now - last_i2c_ms >= I2C_MS) {
        last_i2c_ms = now;
        if (!k230_ok) {
            k230_ok = suite_i2c.probe();
            if (k230_ok && sp == SP_WAIT_K230) enter_menu();
        } else {
            handle_ui();

            if (sp == SP_RUNNING && active_task >= 4 && active_task <= 6 &&
                !cam_pick.isBusy() && !(job_started && !job_finished)) {
                uint8_t cmd = 0, cell = 0, color = 0, slot = 0, to = 0;
                if (suite_i2c.pollArmCommand(cmd, cell, color, slot, to)) {
                    if (cmd == SuiteI2C::CMD_PICK_PLACE_CELL) start_pick(color, slot, cell);
                    else if (cmd == SuiteI2C::CMD_RESTORE && active_task == 6)
                        start_restore(cell, to, color);
                    else if (cmd == SuiteI2C::CMD_RESTORE)
                        start_restore(cell, to, color); /* T4 也支持复位 */
                }
                if (progress_steps > 0 && millis() >= ignore_winner_until) {
                    uint8_t w = 0;
                    if (suite_i2c.readWinner(w) && w != SuiteI2C::WIN_NONE) on_game_over(w);
                }
            }
        }
    }

    /* KEY2：仅任务4/5/6 对局中 */
    if (arm.board.button.is_clicked(SUITE_KEY2_ID)) {
        if (sp == SP_RUNNING && waiting_human && active_task >= 4 && active_task <= 6 &&
            !cam_pick.isBusy()) {
            human_timer_ms = millis();
            progress_steps++;
            job_started = false;
            job_finished = false;
            suite_i2c.setPhase(SuiteI2C::PHASE_WAIT_HUMAN);
            delay(15);
            suite_i2c.setPhase(SuiteI2C::PHASE_HUMAN_DONE);
            show_oled("Think", "AI");
            Serial.println(F("[KEY2] human done"));
        }
    }

    /* KEY1：对局中不再开局（改由触控 NEXT_GAME）；仅调试提示 */
    if (arm.board.button.is_clicked(SUITE_KEY1_ID)) {
        if (sp == SP_GAME_OVER) {
            Serial.println(F("[KEY1] 请用触控屏「再来一局」"));
        } else if (sp == SP_MENU) {
            Serial.println(F("[KEY1] 请用触控屏选任务"));
        }
    }

    if (now - last_bat_ms >= BAT_MS) {
        last_bat_ms = now;
        arm.board.bat.update();
    }
    if (now - last_status_ms >= STATUS_MS) {
        last_status_ms = now;
        arm.update_status();
    }
}
