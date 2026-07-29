/**
 * TaskSuite_E 配置
 */
#ifndef SUITE_CONFIG_H_
#define SUITE_CONFIG_H_

#include <Arduino.h>

static const uint8_t SUITE_KEY1_ID = 1; /* IO2 */
static const uint8_t SUITE_KEY2_ID = 0; /* BOOT IO0 */

static const uint8_t SUITE_TASK1_CELL = 5;
static const uint8_t SUITE_TASK1_SLOT = 1;

static const uint32_t SUITE_BOARD_SETTLE_MS = 800;

#endif
