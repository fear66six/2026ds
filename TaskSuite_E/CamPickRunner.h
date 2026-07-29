#ifndef CAM_PICK_RUNNER_H_
#define CAM_PICK_RUNNER_H_

#include <Arduino.h>
#include "PiecePickRule.h"

/** 槽→格布置，或棋盘格→格复位 */
class CamPickRunner {
public:
    void begin();
    void update();

    bool isBusy() const { return _busy; }
    bool isDone() const { return _done; }
    bool hasError() const { return _error; }

    /** 0=正放盘（任务1/2/4/5/6）；1=旋转盘（任务3） */
    void setCalibProfile(uint8_t profile);

    /** color: PIECE_YELLOW/BLUE；slot 1..5；cell 1..9 —— 槽位取子落盘 */
    void requestPickPlace(uint8_t color, uint8_t slot, uint8_t cell);

    /** 从棋盘 from_cell 抓起放到 to_cell（挪子复位） */
    void requestBoardMove(uint8_t from_cell, uint8_t to_cell, uint8_t color);

private:
    enum Mode : uint8_t {
        MODE_SLOT_PICK = 0,
        MODE_BOARD_MOVE = 1,
    };

    enum Phase : uint8_t {
        PHASE_IDLE = 0,
        PHASE_PICK_APPROACH,
        PHASE_PICK_DOWN,
        PHASE_PICK_GRAB,
        PHASE_PICK_LIFT,
        PHASE_TRANSIT,
        PHASE_PLACE_APPROACH,
        PHASE_PLACE_DOWN,
        PHASE_PLACE_RELEASE,
        PHASE_PLACE_LIFT,
        PHASE_FINISH,
        PHASE_DONE,
    };

    static constexpr uint32_t PHASE_SETTLE_MS = 180;

    bool _busy = false;
    bool _done = false;
    bool _error = false;
    bool _start_pending = false;
    bool _phase_action_started = false;
    Mode _mode = MODE_SLOT_PICK;
    Phase _phase = PHASE_IDLE;
    uint32_t _phase_enter_ms = 0;
    uint32_t _move_duration_ms = 0;

    ArmPickPose _pick_pose{};
    ArmPickPose _place_pose{};
    uint8_t _color = 1;
    uint8_t _slot = 1;
    uint8_t _cell = 5;
    uint8_t _from_cell = 0;
    uint8_t _to_cell = 0;

    void enterPhase(Phase p);
    void armMove(const ArmPickPose& pose, uint32_t duration_ms);
    bool runPhaseAction();
};

extern CamPickRunner cam_pick;

#endif
