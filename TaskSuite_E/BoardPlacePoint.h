#ifndef BOARD_PLACE_POINT_H_
#define BOARD_PLACE_POINT_H_

#include <Arduino.h>
#include "BoardRoi.h"

/**
 * 落子像素点（相对各格 ROI）：
 * - 5 号：ROI 中心
 * - 1,3,7,9：ROI 内朝向 5 号区域的角点
 * - 2,4,6,8：ROI 内朝向 5 号区域的边中点
 */
class BoardPlacePoint {
public:
    /** 返回 ROI 内归一化落子锚点 (fx,fy)，范围约 [0,1] */
    static void getAnchorNorm(uint8_t cell_id, float& fx, float& fy, float margin = 0.05f);

    static PixelPoint fromRoi(const RoiRect& roi, float fx, float fy);
    static PixelPoint getPlacePixel(uint8_t cell_id, const BoardRoi& board);
    static PixelPoint getPlacePixel(uint8_t cell_id, const RoiRect& roi);

    static const char* anchorName(uint8_t cell_id);
    static void printAll(const BoardRoi& board);
};

#endif
