#ifndef __GLOBAL_H__
#define __GLOBAL_H__

#include <stdint.h>
#include <stddef.h>

// 蓝牙模式枚举
enum BluetoothMode {
    BT_MODE_BLE = 0,      // BLE模式（Nordic UART）
    BT_MODE_PS3 = 1       // 经典蓝牙模式（PS3手柄）
};

#define GET_LOW_BYTE(A) ((uint8_t)(A))
#define GET_HIGH_BYTE(A) ((uint8_t)((A) >> 8))
#define BYTE_TO_HW(A, B) ((((uint16_t)(A)) << 8) | (uint8_t)(B))

#define CMD_FIRMWARE_VERSION_CHECK  1
#define CMD_CHECK_BAT_LEVEL_CHECK   2
#define CMD_ACTION_GROUP_RUN        3
#define CMD_ACTION_GROUP_STOP       4
#define CMD_ACTION_GROUP_DOWNLOAD   5
#define CMD_FKINE_RESULT_GET        6
#define CMD_IKINE_RESULT_GET        7
#define CMD_COORDINATE_SET          8
#define CMD_BUZZER_SET              9
#define CMD_OLED_SET                10 
#define CMD_GET_CUR_COORDS          11
#define CMD_OLED_ICON               12
#define CMD_SET_SINGLE_MOTOR        13  // 单电机控制 (十进制 13)
#define CMD_STOP_ALL_MOTOR          14  // 停止所有电机 (十进制 14)
#define CMD_SET_MOTOR_SPEED         15  // 同时设置4个电机速度

#define CMD_CONVEYOR_SET      16   // 传送带速度设置
#define CMD_STEPPER_RESET     17   // 步进电机复位
#define CMD_STEPPER_DIV       18   // 步进电机速度设置 (新增)
#define CMD_STEPPER_RUN       19   // 步进电机运行(步数)

#define CMD_ACTION_GROUP_ERASE      23
#define CMD_BUTTON_EVENT      22 
#define CMD_SET_ESPNOW_CHANNEL      30 
#define CMD_SET_GLOBAL_ACC          31 
#define CMD_ESPNOW_SYNC_CTRL        33  

#define CMD_MECANUM_CONTROL         34  // 改为 34 (0x22)
#define CMD_TANK_CONTROL            35  // 改为 35 (0x23)

#define CMD_SET_PEER_MAC            36 

#define CMD_COLOR_TRACK             40 
#define CMD_FACE_TRACK              41
#define CMD_SELF_LEARN_TRACK        42

#define CMD_APRILTAG_TRACK          43
#define CMD_APRILTAG_GRAB           44
#define CMD_APRILTAG_SET_OFFSET     45  
#define CMD_COLOR_GRAB              46
#define CMD_LLM_CONTROL             47

#define CMD_GARBAGE_GRAB            48
#define CMD_CALIBRATION             49

#define CMD_ARM_MOVE_INC            50  
#define CMD_ARM_SERVO_SINGLE        51
 
#define CMD_SET_SERVO_ID            52
#define CMD_SET_SERVO_MODE          53
#define CMD_ARM_RESET               54
#define CMD_READ_ALL_SERVOS         55
#define CMD_SET_MOVE_ACC            56

#define CMD_SET_POS_OFFSET          57  // 写入偏差 (位置矫正)
#define CMD_GET_POS_OFFSET          58  // 读取偏差
#define CMD_SET_PID_PARAM           59  // 写入闭环PID及最小启动力
#define CMD_GET_PID_PARAM           60  // 读取闭环PID及最小启动力
#define CMD_SET_TORQUE      61
#define CMD_SET_BT_MODE     62  // 设置蓝牙模式（BLE/PS3）
#define CMD_SET_KINEMATICS_PARAM    63  // 写入运动学参数
#define CMD_GET_KINEMATICS_PARAM    64  // 读取运动学参数

#define CMD_GET_REAL_JOINT_ANGLES   65
#define CMD_GET_REAL_TCP_POSE       66
#define CMD_ARM_HOME                67

// LeRobot 模式：args[0]=1 开启，args[0]=0 关闭
// 开启后从机串口只输出二进制帧（舵机位置），关闭后恢复正常
#define CMD_LEROBOT_MODE            68

// PC 串口示教同步：args = 6 * int16 主机关节位置（小端）
// 从机侧直接复用 ESP-NOW 同步时的同一套关节映射逻辑
#define CMD_PC_SYNC_TEACH           69
#define CMD_SYNC_WRITE_SERVOS       70
#define CMD_SERVO_READ_OVERLOAD     71
#define CMD_SERVO_WRITE_OVERLOAD    72
#define CMD_SERVO_READ_BAUD         73
#define CMD_SERVO_WRITE_BAUD        74
#define CMD_SERVO_READ_MAX_TORQUE   75
#define CMD_SERVO_WRITE_MAX_TORQUE  76
#define CMD_SERVO_READ_ANGLE_LIMIT  77
#define CMD_SERVO_WRITE_ANGLE_LIMIT 78
#define CMD_SET_COORD_LIMITS        79
#define CMD_GET_COORD_LIMITS        80



#endif