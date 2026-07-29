#ifndef BOARD_PLACE_ARM_H_
#define BOARD_PLACE_ARM_H_

#include "BoardPlacePoint.h"
#include "PiecePickRule.h"

class BoardPlaceArm {
public:
    static void setProfile(uint8_t profile);
    static uint8_t profile();

    static void pixelToArm(int u, int v, float& out_x, float& out_y);
    static void getCellOffset(uint8_t cell_id, float& dx, float& dy);
    static void getPlacePose(uint8_t cell_id, const BoardRoi& board, ArmPickPose& out);
    static void printPlaceArm(uint8_t cell_id, const BoardRoi& board);
    static void printAllPlaceArm(const BoardRoi& board);
};

#endif
