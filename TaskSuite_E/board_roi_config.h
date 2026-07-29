/**
 * 棋盘 ROI：与 k230/cam_yellow_to_cell5.py（IDE 已调 ROI）对齐
 * 来源：BoardMatrixK230Test/k230/board_matrix_5s.py
 *   ORIGIN=(170+0, 110+30)=(170,140)  CELL=95  ROI=60
 */
#ifndef BOARD_ROI_CONFIG_H_
#define BOARD_ROI_CONFIG_H_

#include <Arduino.h>

static const int IMG_W = 640;
static const int IMG_H = 480;

static const float OBS_X     = 200.0f;
static const float OBS_Y     = 0.0f;
static const float OBS_Z     = 160.0f;
static const float OBS_PITCH = -90.0f;
static const float OBS_ROLL  = 0.0f;
static const float OBS_CLAW  = -60.0f;
static const uint16_t OBS_MOVE_MS = 1500;

/* IDE 调好的 ROI（board_matrix_5s.py） */
static const int   ORIGIN_X = 170;
static const int   ORIGIN_Y = 140;  /* BASE 110 + SHIFT_Y 30 */
static const int   CELL_W   = 95;
static const int   CELL_H   = 95;
static const int   ROI_SIZE = 60;
static const float SKEW_X   = 0.0f;
static const float SKEW_Y   = 0.0f;
static const float YAW_DEG  = 0.0f;

static const float PLACE_MARGIN = 0.05f;

enum PieceColor : uint8_t {
    PIECE_EMPTY  = 0,
    PIECE_YELLOW = 1,
    PIECE_BLUE   = 2,
};

struct HsvRange {
    uint8_t h_min, h_max;
    uint8_t s_min, s_max;
    uint8_t v_min, v_max;
};

static const HsvRange HSV_YELLOW = {20, 40, 80, 255, 80, 255};
static const HsvRange HSV_BLUE   = {90, 130, 80, 255, 60, 255};

#endif
