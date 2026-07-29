#ifndef BOARD_ROI_H_
#define BOARD_ROI_H_

#include "board_roi_config.h"

/** 单个 ROI：左上角 + 宽高（像素） */
struct RoiRect {
    int x;
    int y;
    int w;
    int h;
};

/** 像素点 */
struct PixelPoint {
    int u;
    int v;
};

class BoardRoi {
public:
    enum Profile : uint8_t {
        PROFILE_DEFAULT = 0, /* 正放盘 */
        PROFILE_ROTATED = 1, /* 任务3 旋转盘 */
    };

    RoiRect    rois[3][3];
    PixelPoint centers[3][3];

    void setProfile(uint8_t profile);
    uint8_t profile() const { return _profile; }

    /** 按当前 profile 生成 3x3 ROI 与中心 */
    void rebuild();

    /** 格号 1..9 -> 行列 */
    static void cellToRowCol(uint8_t cell_id, uint8_t& row, uint8_t& col);

    /** 格号 1..9 的 ROI / 中心 / 落子像素点 */
    RoiRect    getRoi(uint8_t cell_id) const;
    PixelPoint getCenter(uint8_t cell_id) const;

    float placeMargin() const;

    /** 串口打印全部 ROI、中心与落子点（校准核对用） */
    void printAll() const;

private:
    uint8_t _profile = PROFILE_DEFAULT;
};

#endif /* BOARD_ROI_H_ */
