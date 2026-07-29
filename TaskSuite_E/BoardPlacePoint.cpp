#include "BoardPlacePoint.h"
#include "board_roi_config.h"
#include <math.h>

void BoardPlacePoint::getAnchorNorm(uint8_t cell_id, float& fx, float& fy, float margin)
{
    const float m = (margin > 0.0f && margin < 0.4f) ? margin : PLACE_MARGIN;
    const float outer = 1.0f - m;

    if (cell_id < 1) cell_id = 1;
    if (cell_id > 9) cell_id = 9;

    switch (cell_id) {
        case 5:
            fx = 0.5f;
            fy = 0.5f;
            break;
        /* 角格：ROI 中靠近 5 号 ROI 的角 */
        case 1:  fx = outer; fy = outer; break;  /* 右下 → 朝 5 */
        case 3:  fx = m;    fy = outer; break;  /* 左下 */
        case 7:  fx = outer; fy = m;    break;  /* 右上 */
        case 9:  fx = m;    fy = m;    break;  /* 左上 */
        /* 边格：ROI 中朝向 5 号 ROI 的边的中点 */
        case 2:  fx = 0.5f; fy = outer; break; /* 下边中点 */
        case 4:  fx = outer; fy = 0.5f; break; /* 右边中点 */
        case 6:  fx = m;    fy = 0.5f; break; /* 左边中点 */
        case 8:  fx = 0.5f; fy = m;    break; /* 上边中点 */
        default:
            fx = 0.5f;
            fy = 0.5f;
            break;
    }
}

PixelPoint BoardPlacePoint::fromRoi(const RoiRect& roi, float fx, float fy)
{
    PixelPoint p;
    p.u = roi.x + (int)lroundf(fx * (float)roi.w);
    p.v = roi.y + (int)lroundf(fy * (float)roi.h);
    return p;
}

PixelPoint BoardPlacePoint::getPlacePixel(uint8_t cell_id, const BoardRoi& board)
{
    float fx, fy;
    getAnchorNorm(cell_id, fx, fy, board.placeMargin());
    return fromRoi(board.getRoi(cell_id), fx, fy);
}

PixelPoint BoardPlacePoint::getPlacePixel(uint8_t cell_id, const RoiRect& roi)
{
    float fx, fy;
    getAnchorNorm(cell_id, fx, fy, PLACE_MARGIN);
    return fromRoi(roi, fx, fy);
}

const char* BoardPlacePoint::anchorName(uint8_t cell_id)
{
    switch (cell_id) {
        case 1: case 3: case 7: case 9: return "corner->5";
        case 2: case 4: case 6: case 8: return "edge-mid->5";
        case 5: return "center";
        default: return "?";
    }
}

void BoardPlacePoint::printAll(const BoardRoi& board)
{
    Serial.println(F("======== Board Place Points ========"));
    Serial.printf("PLACE_MARGIN=%.2f (inset from ROI edge)\n", board.placeMargin());
    Serial.println(F("cell | anchor       | place(u,v)"));
    for (uint8_t id = 1; id <= 9; ++id) {
        PixelPoint p = getPlacePixel(id, board);
        Serial.printf("  %d  | %-12s | (%3d,%3d)\n",
                      id, anchorName(id), p.u, p.v);
    }
    Serial.println(F("===================================="));
}
