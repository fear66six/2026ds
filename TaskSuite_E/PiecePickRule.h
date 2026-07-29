#ifndef PIECE_PICK_RULE_H_
#define PIECE_PICK_RULE_H_

#include <Arduino.h>
#include "board_roi_config.h"

struct ArmPickPose {
    float x;
    float y;
    float z;
    float pitch;
    float roll;
    float claw;
};

/**
 * 取子顺序管理：
 * - 黄：Y > 0 一侧，按 X 从小到大取
 * - 蓝：Y < 0 一侧，按 X 从小到大取
 */
class PiecePickRule {
public:
    void reset();

    /** 是否还能再取该颜色棋子 */
    bool hasPiece(PieceColor color) const;

    /** 取下一颗（X 最小优先），成功后内部计数 +1；失败返回 false */
    bool takeNext(PieceColor color, ArmPickPose& out);

    /** 指定第几颗（slot 1..N，1=X 最小），只读坐标 */
    bool getPickPose(PieceColor color, uint8_t slot_1based, ArmPickPose& out) const;

    /** 仅查询下一颗位置，不消耗计数 */
    bool peekNext(PieceColor color, ArmPickPose& out) const;

    uint8_t takenCount(PieceColor color) const;
    uint8_t remainingCount(PieceColor color) const;

    void printRule() const;
    void printStatus() const;

private:
    uint8_t _yellow_taken = 0;
    uint8_t _blue_taken = 0;

    bool getSlot(PieceColor color, uint8_t index, ArmPickPose& out) const;
};

#endif
