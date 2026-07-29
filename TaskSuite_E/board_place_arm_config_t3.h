/**
 * 任务3（旋转盘）落子标定 — 与默认 board_place_arm_config.h 并存
 * 常量带 T3_ 前缀，由 BoardPlaceArm 按 profile 选用
 */
#ifndef BOARD_PLACE_ARM_CONFIG_T3_H_
#define BOARD_PLACE_ARM_CONFIG_T3_H_

#include <Arduino.h>

static const float T3_PLACE_Z          = 55.0f;
static const float T3_PLACE_Z_ADJUST   = -35.0f;
static const float T3_PLACE_PITCH      = -90.0f;
static const float T3_PLACE_ROLL       = 0.0f;
static const float T3_PLACE_CLAW_OPEN  = -60.0f;

static const int   T3_ARM_REF_U    = 320;
static const int   T3_ARM_REF_V    = 240;
static const float T3_ARM_REF_X    = 200.0f;
static const float T3_ARM_REF_Y    = 0.0f;
static const float T3_MM_PER_PX_U  = -0.45f;
static const float T3_MM_PER_PX_V  =  0.45f;
static const float T3_PLACE_X_OFFSET = 65.0f;
static const float T3_PLACE_Y_OFFSET = 15.0f;

static const float T3_PLACE_CELL_DX[9] = {
    13.0f, 0.0f, 96.0f,
    0.0f, 0.0f, 0.0f,
    -83.0f, 0.0f, -5.0f,
};
static const float T3_PLACE_CELL_DY[9] = {
    90.0f, 0.0f, -5.0f,
    0.0f, 0.0f, 0.0f,
    18.0f, 0.0f, -80.0f,
};

#endif
