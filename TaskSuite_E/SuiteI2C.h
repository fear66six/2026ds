#ifndef SUITE_I2C_H_
#define SUITE_I2C_H_

#include <Arduino.h>

/**
 * TaskSuite_E：对局抓放寄存器(0x00..) + UI 任务寄存器(0x20..)
 * Wire1 SDA=21 SCL=22，地址 0x5F，magic NX，从机 mem≥64
 */
class SuiteI2C {
public:
    static constexpr uint8_t ADDR = 0x5F;
    static constexpr uint8_t REG_MEM_SIZE = 64; /* 勿用 MEM_SIZE：与 lwIP MEM_SIZE 宏冲突 */

    enum Cmd : uint8_t {
        CMD_NOP             = 0,
        CMD_PICK_PLACE_CELL = 1,
        CMD_RESTORE         = 2,
    };

    enum Status : uint8_t {
        ST_IDLE = 0,
        ST_BUSY = 1,
        ST_DONE = 2,
        ST_ERR  = 3,
    };

    enum Phase : uint8_t {
        PHASE_STOP        = 0,
        PHASE_START       = 1,
        PHASE_WAIT_HUMAN  = 2,
        PHASE_HUMAN_DONE  = 3,
        PHASE_ABORT       = 4,
    };

    enum Winner : uint8_t {
        WIN_NONE   = 0,
        WIN_YELLOW = 1,
        WIN_BLUE   = 2,
        WIN_DRAW   = 3,
    };

    enum UiCmd : uint8_t {
        UI_NOP         = 0,
        UI_SELECT_TASK = 1,
        UI_START       = 2,
        UI_NEXT_GAME   = 3,
        UI_ABORT_HOME  = 4,
    };

    enum EspState : uint8_t {
        ESP_IDLE       = 0,
        ESP_READY_MENU = 1,
        ESP_RUNNING    = 2,
        ESP_WAIT_HUMAN = 3,
        ESP_GAME_OVER  = 4,
        ESP_DONE_OK    = 5,
    };

    struct SeqStep {
        uint8_t color;
        uint8_t slot;
        uint8_t cell;
    };

    bool begin();
    bool probe();

    /* ---- 对局/抓放 ---- */
    bool setPhase(uint8_t phase);
    bool setFirstCell(uint8_t cell);
    bool setStatus(uint8_t st);
    bool clearWinner();
    bool pollArmCommand(uint8_t& cmd, uint8_t& cell, uint8_t& color,
                        uint8_t& slot, uint8_t& to_cell);
    bool readBoard(uint8_t out9[9]);
    bool readWinner(uint8_t& winner);

    /* ---- UI ---- */
    bool setEspState(uint8_t st);
    bool pollUiCommand(uint8_t& ui_cmd, uint8_t& ui_arg);
    bool readTaskId(uint8_t& task);
    bool readSequence(SeqStep* steps, uint8_t max_n, uint8_t& out_n);

private:
    enum Reg : uint8_t {
        REG_MAGIC0     = 0x00,
        REG_MAGIC1     = 0x01,
        REG_CMD        = 0x02,
        REG_ARG        = 0x03,
        REG_COLOR      = 0x04,
        REG_SLOT       = 0x05,
        REG_STATUS     = 0x06,
        REG_SEQ        = 0x07,
        REG_PHASE      = 0x08,
        REG_FIRST_CELL = 0x09,
        REG_WINNER     = 0x0A,
        REG_MOVE_HINT  = 0x0B,
        REG_TO_CELL    = 0x0C,
        REG_BOARD0     = 0x10,

        REG_TASK       = 0x20,
        REG_UI_CMD     = 0x21,
        REG_UI_ARG     = 0x22,
        REG_SEQ_LEN    = 0x23,
        REG_SEQ_DATA   = 0x24, /* 12 bytes */
        REG_ESP_STATE  = 0x30,
        REG_UI_SEQ     = 0x31,
    };

    uint8_t _last_arm_seq = 0;
    uint8_t _last_ui_seq = 0;

    bool writeReg(uint8_t reg, uint8_t val);
    bool readReg(uint8_t reg, uint8_t& val);
    bool readRegs(uint8_t reg, uint8_t* data, uint8_t len);
};

#endif
