#ifndef MAGNET_CONTROL_H
#define MAGNET_CONTROL_H

#include <stdint.h>

#define MAGNET_MIN_TIMEOUT_MS 50U
#define MAGNET_MAX_TIMEOUT_MS 500U

void magnet_gpio_init_safe(void);
void magnet_force_off(void);
int magnet_turn_on_timed(uint32_t timeout_ms);
uint8_t magnet_get_state(void);
void magnet_tick_isr(uint32_t now_ms);

#endif
