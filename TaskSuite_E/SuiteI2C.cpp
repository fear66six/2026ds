#include "SuiteI2C.h"
#include <Wire.h>

bool SuiteI2C::writeReg(uint8_t reg, uint8_t val)
{
    Wire1.beginTransmission(ADDR);
    Wire1.write(reg);
    Wire1.write(val);
    return Wire1.endTransmission() == 0;
}

bool SuiteI2C::readReg(uint8_t reg, uint8_t& val)
{
    Wire1.beginTransmission(ADDR);
    Wire1.write(reg);
    if (Wire1.endTransmission(false) == 0 && Wire1.requestFrom((int)ADDR, 1) == 1) {
        val = (uint8_t)Wire1.read();
        return true;
    }
    Wire1.beginTransmission(ADDR);
    Wire1.write(reg);
    if (Wire1.endTransmission(true) != 0) return false;
    delay(2);
    if (Wire1.requestFrom((int)ADDR, 1) != 1) return false;
    val = (uint8_t)Wire1.read();
    return true;
}

bool SuiteI2C::readRegs(uint8_t reg, uint8_t* data, uint8_t len)
{
    Wire1.beginTransmission(ADDR);
    Wire1.write(reg);
    if (Wire1.endTransmission(false) == 0 &&
        Wire1.requestFrom((int)ADDR, (int)len) == (int)len) {
        for (uint8_t i = 0; i < len; ++i) data[i] = (uint8_t)Wire1.read();
        return true;
    }
    Wire1.beginTransmission(ADDR);
    Wire1.write(reg);
    if (Wire1.endTransmission(true) != 0) return false;
    delay(2);
    if (Wire1.requestFrom((int)ADDR, (int)len) != (int)len) return false;
    for (uint8_t i = 0; i < len; ++i) data[i] = (uint8_t)Wire1.read();
    return true;
}

bool SuiteI2C::begin()
{
    Wire1.setClock(100000);
    _last_arm_seq = 0;
    _last_ui_seq = 0;
    setPhase(PHASE_STOP);
    setStatus(ST_IDLE);
    setEspState(ESP_READY_MENU);
    clearWinner();
    return probe();
}

bool SuiteI2C::probe()
{
    uint8_t m0 = 0, m1 = 0;
    if (!readReg(REG_MAGIC0, m0) || !readReg(REG_MAGIC1, m1)) return false;
    return m0 == 'N' && m1 == 'X';
}

bool SuiteI2C::setPhase(uint8_t phase) { return writeReg(REG_PHASE, phase); }
bool SuiteI2C::setFirstCell(uint8_t cell)
{
    /* 0 = 人先手无首落格；1..9 有效；其它回退 5 */
    if (cell != 0 && (cell < 1 || cell > 9)) cell = 5;
    return writeReg(REG_FIRST_CELL, cell);
}
bool SuiteI2C::setStatus(uint8_t st) { return writeReg(REG_STATUS, st); }
bool SuiteI2C::clearWinner() { return writeReg(REG_WINNER, WIN_NONE); }
bool SuiteI2C::setEspState(uint8_t st) { return writeReg(REG_ESP_STATE, st); }

bool SuiteI2C::pollArmCommand(uint8_t& cmd, uint8_t& cell, uint8_t& color,
                              uint8_t& slot, uint8_t& to_cell)
{
    uint8_t c = 0, seq = 0;
    if (!readReg(REG_CMD, c) || c == CMD_NOP) return false;
    if (!readReg(REG_SEQ, seq)) return false;
    if (seq == _last_arm_seq) {
        writeReg(REG_CMD, CMD_NOP);
        return false;
    }
    uint8_t arg = 0, col = 0, sl = 0, to = 0;
    readReg(REG_ARG, arg);
    readReg(REG_COLOR, col);
    readReg(REG_SLOT, sl);
    readReg(REG_TO_CELL, to);
    writeReg(REG_CMD, CMD_NOP);
    _last_arm_seq = seq;
    cmd = c;
    cell = arg;
    color = col;
    slot = sl;
    to_cell = to;
    return true;
}

bool SuiteI2C::readBoard(uint8_t out9[9]) { return readRegs(REG_BOARD0, out9, 9); }
bool SuiteI2C::readWinner(uint8_t& winner) { return readReg(REG_WINNER, winner); }

bool SuiteI2C::pollUiCommand(uint8_t& ui_cmd, uint8_t& ui_arg)
{
    uint8_t c = 0, seq = 0;
    if (!readReg(REG_UI_CMD, c) || c == UI_NOP) return false;
    if (!readReg(REG_UI_SEQ, seq)) return false;
    if (seq == _last_ui_seq) {
        writeReg(REG_UI_CMD, UI_NOP);
        return false;
    }
    uint8_t arg = 0;
    readReg(REG_UI_ARG, arg);
    writeReg(REG_UI_CMD, UI_NOP);
    _last_ui_seq = seq;
    ui_cmd = c;
    ui_arg = arg;
    return true;
}

bool SuiteI2C::readTaskId(uint8_t& task) { return readReg(REG_TASK, task); }

bool SuiteI2C::readSequence(SeqStep* steps, uint8_t max_n, uint8_t& out_n)
{
    uint8_t len = 0;
    if (!readReg(REG_SEQ_LEN, len)) return false;
    if (len > max_n) len = max_n;
    if (len == 0) {
        out_n = 0;
        return true;
    }
    uint8_t raw[12] = {0};
    uint8_t bytes = (uint8_t)(len * 3);
    if (bytes > 12) bytes = 12;
    if (!readRegs(REG_SEQ_DATA, raw, bytes)) return false;
    for (uint8_t i = 0; i < len; ++i) {
        steps[i].color = raw[i * 3 + 0];
        steps[i].slot  = raw[i * 3 + 1];
        steps[i].cell  = raw[i * 3 + 2];
    }
    out_n = len;
    return true;
}
