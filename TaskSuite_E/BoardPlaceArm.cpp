#include "BoardPlaceArm.h"
#include "board_place_arm_config.h"
#include "board_place_arm_config_t3.h"

namespace {

uint8_t s_profile = 0;

uint8_t cellIndex(uint8_t cell_id)
{
    if (cell_id < 1) return 0;
    if (cell_id > 9) return 8;
    return (uint8_t)(cell_id - 1);
}

bool rotated() { return s_profile == 1; }

} // namespace

void BoardPlaceArm::setProfile(uint8_t profile)
{
    s_profile = (profile == 1) ? 1 : 0;
}

uint8_t BoardPlaceArm::profile() { return s_profile; }

void BoardPlaceArm::pixelToArm(int u, int v, float& out_x, float& out_y)
{
    if (rotated()) {
        out_x = T3_ARM_REF_X + (float)(u - T3_ARM_REF_U) * T3_MM_PER_PX_U + T3_PLACE_X_OFFSET;
        out_y = T3_ARM_REF_Y + (float)(v - T3_ARM_REF_V) * T3_MM_PER_PX_V + T3_PLACE_Y_OFFSET;
    } else {
        out_x = ARM_REF_X + (float)(u - ARM_REF_U) * MM_PER_PX_U + PLACE_X_OFFSET;
        out_y = ARM_REF_Y + (float)(v - ARM_REF_V) * MM_PER_PX_V + PLACE_Y_OFFSET;
    }
}

void BoardPlaceArm::getCellOffset(uint8_t cell_id, float& dx, float& dy)
{
    const uint8_t idx = cellIndex(cell_id);
    if (rotated()) {
        dx = T3_PLACE_CELL_DX[idx];
        dy = T3_PLACE_CELL_DY[idx];
    } else {
        dx = PLACE_CELL_DX[idx];
        dy = PLACE_CELL_DY[idx];
    }
}

void BoardPlaceArm::getPlacePose(uint8_t cell_id, const BoardRoi& board, ArmPickPose& out)
{
    PixelPoint p = BoardPlacePoint::getPlacePixel(cell_id, board);
    pixelToArm(p.u, p.v, out.x, out.y);

    float dx, dy;
    getCellOffset(cell_id, dx, dy);
    out.x += dx;
    out.y += dy;

    if (rotated()) {
        out.z = T3_PLACE_Z + T3_PLACE_Z_ADJUST;
        out.pitch = T3_PLACE_PITCH;
        out.roll = T3_PLACE_ROLL;
        out.claw = T3_PLACE_CLAW_OPEN;
    } else {
        out.z = PLACE_Z + PLACE_Z_ADJUST;
        out.pitch = PLACE_PITCH;
        out.roll = PLACE_ROLL;
        out.claw = PLACE_CLAW_OPEN;
    }
}

void BoardPlaceArm::printPlaceArm(uint8_t cell_id, const BoardRoi& board)
{
    PixelPoint px = BoardPlacePoint::getPlacePixel(cell_id, board);
    ArmPickPose arm;
    getPlacePose(cell_id, board, arm);
    float dx, dy;
    getCellOffset(cell_id, dx, dy);
    Serial.printf("[PlaceArm] cell%d pixel=(%d,%d) corr=(%.1f,%.1f) -> arm=(%.1f,%.1f,%.1f)\n",
                  cell_id, px.u, px.v, dx, dy, arm.x, arm.y, arm.z);
}

void BoardPlaceArm::printAllPlaceArm(const BoardRoi& board)
{
    Serial.println(F("======== Place Arm (all cells) ========"));
    Serial.printf("profile=%s\n", rotated() ? "ROTATED(T3)" : "DEFAULT");
    Serial.println(F("cell | pixel(u,v) | cell_corr(dx,dy) | arm(x,y,z)"));
    for (uint8_t id = 1; id <= 9; ++id) {
        PixelPoint px = BoardPlacePoint::getPlacePixel(id, board);
        ArmPickPose arm;
        getPlacePose(id, board, arm);
        float dx, dy;
        getCellOffset(id, dx, dy);
        Serial.printf("  %d  | (%3d,%3d) | (%5.1f,%5.1f) | (%.1f,%.1f,%.1f)\n",
                      id, px.u, px.v, dx, dy, arm.x, arm.y, arm.z);
    }
    Serial.println(F("======================================="));
}
