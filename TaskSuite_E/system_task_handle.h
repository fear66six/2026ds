#ifndef __SYSTEM_TASK_HANDLE_H__
#define __SYSTEM_TASK_HANDLE_H__

#include "esp_event.h"
#include "CommProtocol.h"

void register_system_task(esp_event_loop_handle_t *event_loop);
void system_loop_handler(void);
void at32_packet_callback(PacketTypeDef* rx_packet);
void pump_at32_feedback(void);
bool sync_arm_feedback(uint32_t timeout_ms);
bool get_last_servo_positions(int16_t out_pos[6]);

#endif
