#include "CamPickRunner.h"
#include "Robot_Arm.h"
#include "system_task_handle.h"
#include "board_roi_config.h"
#include "BoardRoi.h"
#include "BoardPlacePoint.h"
#include "PiecePickRule.h"
#include "BoardPlaceArm.h"
#include "piece_pick_config.h"
#include "board_place_arm_config.h"

CamPickRunner cam_pick;

namespace {
PiecePickRule s_pick;
BoardRoi s_board;
}

void CamPickRunner::begin()
{
    setCalibProfile(0);
    s_pick.reset();
    s_pick.printRule();
}

void CamPickRunner::setCalibProfile(uint8_t profile)
{
    const uint8_t p = (profile == 1) ? 1 : 0;
    s_board.setProfile(p);
    BoardPlaceArm::setProfile(p);
    s_board.rebuild();
    Serial.printf("[CamPick] calib profile=%u (%s)\n",
                  p, p ? "ROTATED T3" : "DEFAULT");
    BoardPlacePoint::printAll(s_board);
    BoardPlaceArm::printAllPlaceArm(s_board);
}

void CamPickRunner::requestPickPlace(uint8_t color, uint8_t slot, uint8_t cell)
{
    if (_busy) return;
    if (color != PIECE_YELLOW && color != PIECE_BLUE) color = PIECE_YELLOW;
    if (slot < 1) slot = 1;
    if (slot > PICK_SLOTS_PER_COLOR) slot = PICK_SLOTS_PER_COLOR;
    if (cell < 1) cell = 1;
    if (cell > 9) cell = 9;
    _mode = MODE_SLOT_PICK;
    _color = color;
    _slot = slot;
    _cell = cell;
    _from_cell = 0;
    _to_cell = cell;
    _start_pending = true;
    _done = false;
    _error = false;
    _phase = PHASE_IDLE;
}

void CamPickRunner::requestBoardMove(uint8_t from_cell, uint8_t to_cell, uint8_t color)
{
    if (_busy) return;
    if (color != PIECE_YELLOW && color != PIECE_BLUE) color = PIECE_YELLOW;
    if (from_cell < 1) from_cell = 1;
    if (from_cell > 9) from_cell = 9;
    if (to_cell < 1) to_cell = 1;
    if (to_cell > 9) to_cell = 9;
    _mode = MODE_BOARD_MOVE;
    _color = color;
    _from_cell = from_cell;
    _to_cell = to_cell;
    _cell = to_cell;
    _slot = 0;
    _start_pending = true;
    _done = false;
    _error = false;
    _phase = PHASE_IDLE;
}

void CamPickRunner::armMove(const ArmPickPose& pose, uint32_t duration_ms)
{
    arm.move(pose.x, pose.y, pose.z, pose.pitch, pose.roll, pose.claw, duration_ms);
    _move_duration_ms = duration_ms;
}

void CamPickRunner::enterPhase(Phase p)
{
    _phase = p;
    _phase_enter_ms = millis();
    _phase_action_started = false;
    Serial.printf("[CamPick] phase -> %u\n", (unsigned)p);
}

void CamPickRunner::update()
{
    if (_start_pending && !_busy) {
        _start_pending = false;
        _busy = true;
        _done = false;
        _error = false;

        if (_mode == MODE_BOARD_MOVE) {
            BoardPlaceArm::getPlacePose(_from_cell, s_board, _pick_pose);
            BoardPlaceArm::getPlacePose(_to_cell, s_board, _place_pose);
            /* 抓取时先张开；闭合角用 PICK_CLAW_CLOSE */
            _pick_pose.claw = PICK_CLAW_OPEN;
            Serial.printf("[CamPick] RESTORE cell%u -> cell%u (%.0f,%.0f)->(%.0f,%.0f)\n",
                          _from_cell, _to_cell,
                          _pick_pose.x, _pick_pose.y,
                          _place_pose.x, _place_pose.y);
        } else {
            if (!s_pick.getPickPose((PieceColor)_color, _slot, _pick_pose)) {
                Serial.println(F("[CamPick] invalid pick"));
                _error = true;
                _busy = false;
                return;
            }
            _pick_pose.z += PICK_Z_ADJUST;
            BoardPlaceArm::getPlacePose(_cell, s_board, _place_pose);
            Serial.printf("[CamPick] %s slot%u -> cell%u\n",
                          (_color == PIECE_YELLOW) ? "YELLOW" : "BLUE",
                          _slot, _cell);
        }
        enterPhase(PHASE_PICK_APPROACH);
    }

    if (!_busy || _phase == PHASE_IDLE || _phase == PHASE_DONE) return;

    if (!_phase_action_started) {
        if (!runPhaseAction()) {
            _error = true;
            _busy = false;
            return;
        }
        _phase_action_started = true;
        _phase_enter_ms = millis();
        return;
    }

    if (millis() - _phase_enter_ms < _move_duration_ms + PHASE_SETTLE_MS) return;

    switch (_phase) {
        case PHASE_PICK_APPROACH:  enterPhase(PHASE_PICK_DOWN); break;
        case PHASE_PICK_DOWN:      enterPhase(PHASE_PICK_GRAB); break;
        case PHASE_PICK_GRAB:      enterPhase(PHASE_PICK_LIFT); break;
        case PHASE_PICK_LIFT:      enterPhase(PHASE_TRANSIT); break;
        case PHASE_TRANSIT:        enterPhase(PHASE_PLACE_APPROACH); break;
        case PHASE_PLACE_APPROACH: enterPhase(PHASE_PLACE_DOWN); break;
        case PHASE_PLACE_DOWN:     enterPhase(PHASE_PLACE_RELEASE); break;
        case PHASE_PLACE_RELEASE:  enterPhase(PHASE_PLACE_LIFT); break;
        case PHASE_PLACE_LIFT:     enterPhase(PHASE_FINISH); break;
        case PHASE_FINISH:
            _done = true;
            _busy = false;
            enterPhase(PHASE_DONE);
            arm.board.buzzer.set(100, 80, 3, 2000);
            if (_mode == MODE_BOARD_MOVE) {
                Serial.printf("[CamPick] RESTORE DONE %u->%u\n", _from_cell, _to_cell);
            } else {
                Serial.printf("[CamPick] DONE ->cell%u\n", _cell);
            }
            break;
        default: break;
    }
}

bool CamPickRunner::runPhaseAction()
{
    ArmPickPose p{};
    /* 棋盘抓取抬升用 TRANSIT_Z；槽位抓取用 PICK_LIFT_Z */
    const float lift_z = (_mode == MODE_BOARD_MOVE) ? TRANSIT_Z : PICK_LIFT_Z;

    switch (_phase) {
        case PHASE_PICK_APPROACH:
            p = _pick_pose; p.z = lift_z; p.claw = PICK_CLAW_OPEN;
            armMove(p, MOVE_MS_PICK); return true;
        case PHASE_PICK_DOWN:
            p = _pick_pose; p.claw = PICK_CLAW_OPEN;
            armMove(p, MOVE_MS_PICK); return true;
        case PHASE_PICK_GRAB:
            p = _pick_pose; p.claw = PICK_CLAW_CLOSE;
            armMove(p, 600); return true;
        case PHASE_PICK_LIFT:
            p = _pick_pose; p.z = lift_z; p.claw = PICK_CLAW_CLOSE;
            armMove(p, MOVE_MS_PICK); return true;
        case PHASE_TRANSIT:
            p = _place_pose; p.z = TRANSIT_Z; p.claw = PICK_CLAW_CLOSE;
            armMove(p, MOVE_MS_TRANSIT); return true;
        case PHASE_PLACE_APPROACH:
            p = _place_pose; p.z = TRANSIT_Z; p.claw = PICK_CLAW_CLOSE;
            armMove(p, MOVE_MS_PLACE); return true;
        case PHASE_PLACE_DOWN:
            p = _place_pose; p.claw = PICK_CLAW_CLOSE;
            armMove(p, MOVE_MS_PLACE); return true;
        case PHASE_PLACE_RELEASE:
            p = _place_pose; p.claw = PLACE_CLAW_OPEN;
            armMove(p, 600); return true;
        case PHASE_PLACE_LIFT:
            p = _place_pose; p.z = TRANSIT_Z; p.claw = PLACE_CLAW_OPEN;
            armMove(p, MOVE_MS_PLACE); return true;
        case PHASE_FINISH:
            arm.move(OBS_X, OBS_Y, OBS_Z, OBS_PITCH, OBS_ROLL, OBS_CLAW, OBS_MOVE_MS);
            _move_duration_ms = OBS_MOVE_MS;
            return true;
        default:
            return false;
    }
}
