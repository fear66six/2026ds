#include "PiecePickRule.h"
#include "piece_pick_config.h"

void PiecePickRule::reset()
{
    _yellow_taken = 0;
    _blue_taken = 0;
}

uint8_t PiecePickRule::takenCount(PieceColor color) const
{
    if (color == PIECE_YELLOW) return _yellow_taken;
    if (color == PIECE_BLUE) return _blue_taken;
    return 0;
}

uint8_t PiecePickRule::remainingCount(PieceColor color) const
{
    if (color == PIECE_YELLOW) {
        return (_yellow_taken >= PICK_SLOTS_PER_COLOR) ? 0 : (uint8_t)(PICK_SLOTS_PER_COLOR - _yellow_taken);
    }
    if (color == PIECE_BLUE) {
        return (_blue_taken >= PICK_SLOTS_PER_COLOR) ? 0 : (uint8_t)(PICK_SLOTS_PER_COLOR - _blue_taken);
    }
    return 0;
}

bool PiecePickRule::hasPiece(PieceColor color) const
{
    return remainingCount(color) > 0;
}

bool PiecePickRule::getSlot(PieceColor color, uint8_t index, ArmPickPose& out) const
{
    if (index >= PICK_SLOTS_PER_COLOR) return false;

    if (color == PIECE_YELLOW) {
        out.x = YELLOW_PICK_X[index];
        out.y = PICK_YELLOW_Y;
    } else if (color == PIECE_BLUE) {
        out.x = BLUE_PICK_X[index];
        out.y = PICK_BLUE_Y;
    } else {
        return false;
    }

    out.z = PICK_Z;
    out.pitch = PICK_PITCH;
    out.roll = PICK_ROLL;
    out.claw = PICK_CLAW_OPEN;
    return true;
}

bool PiecePickRule::peekNext(PieceColor color, ArmPickPose& out) const
{
    uint8_t idx = takenCount(color);
    return getSlot(color, idx, out);
}

bool PiecePickRule::takeNext(PieceColor color, ArmPickPose& out)
{
    if (!hasPiece(color)) return false;

    uint8_t idx = takenCount(color);
    if (!getSlot(color, idx, out)) return false;

    if (color == PIECE_YELLOW) _yellow_taken++;
    else if (color == PIECE_BLUE) _blue_taken++;

    return true;
}

bool PiecePickRule::getPickPose(PieceColor color, uint8_t slot_1based, ArmPickPose& out) const
{
    if (slot_1based < 1 || slot_1based > PICK_SLOTS_PER_COLOR) {
        return false;
    }
    return getSlot(color, (uint8_t)(slot_1based - 1), out);
}

void PiecePickRule::printRule() const
{
    Serial.println(F("======== Piece Pick Rule ========"));
    Serial.println(F("YELLOW: Y+ side, pick smaller X first"));
    Serial.println(F("BLUE:   Y- side, pick smaller X first"));
    Serial.printf("PICK_YELLOW_Y=%.1f  PICK_BLUE_Y=%.1f  PICK_Z=%.1f\n",
                  PICK_YELLOW_Y, PICK_BLUE_Y, PICK_Z);
    Serial.println(F("slot | yellow X | blue X"));
    for (uint8_t i = 0; i < PICK_SLOTS_PER_COLOR; ++i) {
        Serial.printf("  %d  | %8.1f | %7.1f\n", i + 1, YELLOW_PICK_X[i], BLUE_PICK_X[i]);
    }
    Serial.println(F("pick order: slot1 -> slot5 (X ascending)"));
    Serial.println(F("================================="));
}

void PiecePickRule::printStatus() const
{
    Serial.printf("[Pick] yellow taken=%u remain=%u | blue taken=%u remain=%u\n",
                  takenCount(PIECE_YELLOW), remainingCount(PIECE_YELLOW),
                  takenCount(PIECE_BLUE), remainingCount(PIECE_BLUE));
}
