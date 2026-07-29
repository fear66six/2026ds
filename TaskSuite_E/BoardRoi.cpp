#include "BoardRoi.h"
#include "BoardPlacePoint.h"
#include "board_roi_config_t3.h"
#include <math.h>

void BoardRoi::setProfile(uint8_t profile)
{
    _profile = (profile == PROFILE_ROTATED) ? PROFILE_ROTATED : PROFILE_DEFAULT;
}

float BoardRoi::placeMargin() const
{
    return (_profile == PROFILE_ROTATED) ? T3_PLACE_MARGIN : PLACE_MARGIN;
}

void BoardRoi::cellToRowCol(uint8_t cell_id, uint8_t& row, uint8_t& col)
{
    if (cell_id < 1) cell_id = 1;
    if (cell_id > 9) cell_id = 9;
    row = (uint8_t)((cell_id - 1) / 3);
    col = (uint8_t)((cell_id - 1) % 3);
}

void BoardRoi::rebuild()
{
    const bool rot = (_profile == PROFILE_ROTATED);
    const int origin_x = rot ? T3_ORIGIN_X : ORIGIN_X;
    const int origin_y = rot ? T3_ORIGIN_Y : ORIGIN_Y;
    const int cell_w   = rot ? T3_CELL_W   : CELL_W;
    const int cell_h   = rot ? T3_CELL_H   : CELL_H;
    const int roi_size = rot ? T3_ROI_SIZE : ROI_SIZE;
    const float skew_x = rot ? T3_SKEW_X   : SKEW_X;
    const float skew_y = rot ? T3_SKEW_Y   : SKEW_Y;
    const float yaw_deg = rot ? T3_YAW_DEG : YAW_DEG;

    const float yaw = yaw_deg * 0.01745329252f;
    const float cy = cosf(yaw);
    const float sy = sinf(yaw);

    const float base_cx0 = (float)origin_x + (float)roi_size * 0.5f;
    const float base_cy0 = (float)origin_y + (float)roi_size * 0.5f;
    const float pivot_u = base_cx0 + (float)cell_w;
    const float pivot_v = base_cy0 + (float)cell_h;

    for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 3; ++c) {
            float u = base_cx0 + (float)c * (float)cell_w + (float)r * skew_x;
            float v = base_cy0 + (float)r * (float)cell_h + (float)c * skew_y;

            if (yaw_deg != 0.0f) {
                const float du = u - pivot_u;
                const float dv = v - pivot_v;
                u = pivot_u + du * cy - dv * sy;
                v = pivot_v + du * sy + dv * cy;
            }

            const int cx = (int)lroundf(u);
            const int cyi = (int)lroundf(v);
            const int half = roi_size / 2;

            RoiRect roi;
            roi.x = cx - half;
            roi.y = cyi - half;
            roi.w = roi_size;
            roi.h = roi_size;

            if (roi.x < 0) roi.x = 0;
            if (roi.y < 0) roi.y = 0;
            if (roi.x + roi.w > IMG_W) roi.x = IMG_W - roi.w;
            if (roi.y + roi.h > IMG_H) roi.y = IMG_H - roi.h;
            if (roi.x < 0) { roi.x = 0; roi.w = IMG_W; }
            if (roi.y < 0) { roi.y = 0; roi.h = IMG_H; }

            rois[r][c] = roi;
            centers[r][c].u = roi.x + roi.w / 2;
            centers[r][c].v = roi.y + roi.h / 2;
        }
    }
}

RoiRect BoardRoi::getRoi(uint8_t cell_id) const
{
    uint8_t r, c;
    cellToRowCol(cell_id, r, c);
    return rois[r][c];
}

PixelPoint BoardRoi::getCenter(uint8_t cell_id) const
{
    uint8_t r, c;
    cellToRowCol(cell_id, r, c);
    return centers[r][c];
}

void BoardRoi::printAll() const
{
    const bool rot = (_profile == PROFILE_ROTATED);
    Serial.println(F("======== Board ROI Calib ========"));
    Serial.printf("profile=%s IMG=%dx%d YAW=%.1f\n",
                  rot ? "ROTATED(T3)" : "DEFAULT",
                  IMG_W, IMG_H,
                  rot ? T3_YAW_DEG : YAW_DEG);
    Serial.println(F("cell | roi(x,y,w,h)        | center(u,v)"));
    for (uint8_t id = 1; id <= 9; ++id) {
        RoiRect roi = getRoi(id);
        PixelPoint ct = getCenter(id);
        Serial.printf("  %d  | (%3d,%3d,%3d,%3d) | (%3d,%3d)\n",
                      id, roi.x, roi.y, roi.w, roi.h, ct.u, ct.v);
    }
    Serial.println(F("================================="));
    BoardPlacePoint::printAll(*this);
}
