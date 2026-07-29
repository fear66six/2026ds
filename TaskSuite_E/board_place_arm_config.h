/**
 * Task08 落子标定（格号由 K230/对局动态下发）
 */
#ifndef BOARD_PLACE_ARM_CONFIG_H_
#define BOARD_PLACE_ARM_CONFIG_H_

#include <Arduino.h>

static const uint8_t TASK07_TARGET_CELL  = 5;
static const uint8_t TASK07_TARGET_CELL2 = 6;
static const uint8_t TASK01_TARGET_CELL  = TASK07_TARGET_CELL;

static const float PLACE_Z          = 55.0f;
static const float PLACE_Z_ADJUST   = -31.0f;
static const float PLACE_PITCH      = -90.0f;
static const float PLACE_ROLL       = 0.0f;
static const float PLACE_CLAW_OPEN  = -25.0f;
static const float PLACE_CLAW_CLOSE = 15.0f;

static const float TRANSIT_Z = 220.0f;

static const int   ARM_REF_U    = 320;
static const int   ARM_REF_V    = 240;
static const float ARM_REF_X    = 200.0f;
static const float ARM_REF_Y    = 0.0f;

static const float MM_PER_PX_U = -0.45f;
static const float MM_PER_PX_V =  0.45f;

static const float PLACE_X_OFFSET = 60.0f;
static const float PLACE_Y_OFFSET = -8.0f;

/* 下标 4=格5，5=格6 —— 放不准优先改这两格 */
static const float PLACE_CELL_DX[9] = {
    7.0f, 32.0f, 63.0f,
    -30.0f, -5.0f, 30.0f,
    -64.0f, -30.0f, 1.0f,
};
static const float PLACE_CELL_DY[9] = {
    63.0f, 32.0f, 3.0f,
    30.0f, 3.0f, -30.0f,
    6.0f, -25.0f, -58.0f,
};

static const uint32_t MOVE_MS_PICK   = 1200;
static const uint32_t MOVE_MS_PLACE  = 1200;
static const uint32_t MOVE_MS_TRANSIT = 1500;

#endif
