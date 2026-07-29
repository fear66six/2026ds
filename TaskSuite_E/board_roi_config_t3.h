/**
 * 任务3（旋转盘）ROI 标定 — YAW=45°，与默认 board_roi_config.h 并存
 */
#ifndef BOARD_ROI_CONFIG_T3_H_
#define BOARD_ROI_CONFIG_T3_H_

#include <Arduino.h>

static const int   T3_ORIGIN_X = 208;
static const int   T3_ORIGIN_Y = 95;
static const int   T3_CELL_W   = 83;
static const int   T3_CELL_H   = 88;
static const int   T3_ROI_SIZE = 50;
static const float T3_SKEW_X   = 0.0f;
static const float T3_SKEW_Y   = 0.0f;
static const float T3_YAW_DEG  = 45.0f;
static const float T3_PLACE_MARGIN = 0.05f;

#endif
