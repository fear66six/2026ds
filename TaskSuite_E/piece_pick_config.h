/**
 * Task08：机方黄子取子标定（槽位由 K230 按落子次序下发）
 */
#ifndef PIECE_PICK_CONFIG_H_
#define PIECE_PICK_CONFIG_H_

#include <Arduino.h>
#include "board_roi_config.h"

static const PieceColor TASK07_PICK_COLOR = PIECE_YELLOW;
static const uint8_t    TASK07_PICK_SLOT  = 1;
static const uint8_t    TASK07_PICK_SLOT2 = 2;

static const float PICK_Z     = 60.0f;
static const float PICK_PITCH = -90.0f;
static const float PICK_ROLL  = 0.0f;
static const float PICK_CLAW_OPEN  = -40.0f;
static const float PICK_CLAW_CLOSE = 20.0f;
static const float PICK_Z_ADJUST   = -45.0f;

static const float PICK_YELLOW_Y = 85.0f;
static const float PICK_BLUE_Y   = -73.0f;

static const float YELLOW_PICK_X[] = {210.0f, 240.0f, 270.0f, 300.0f, 330.0f};
static const float BLUE_PICK_X[]   = {210.0f, 240.0f, 270.0f, 300.0f, 330.0f};
static const uint8_t PICK_SLOTS_PER_COLOR = 5;

static const float PICK_LIFT_Z = 220.0f;

static const PieceColor TASK01_PICK_COLOR = TASK07_PICK_COLOR;
static const uint8_t    TASK01_PICK_SLOT  = TASK07_PICK_SLOT;

#endif
