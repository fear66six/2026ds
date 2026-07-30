#include <stdint.h>
#include "stm32f10x.h"
#include "board_config.h"
#ifndef STAGE_PING
#include "magnet_control.h"
#endif

#define RX_RING_SIZE 128U
#define COMMAND_SIZE 64U

#ifndef STAGE_PING
#define MAGNET_MIN_TIMEOUT_MS_LOCAL MAGNET_MIN_TIMEOUT_MS
#define MAGNET_MAX_TIMEOUT_MS_LOCAL MAGNET_MAX_TIMEOUT_MS
#else
#define MAGNET_MIN_TIMEOUT_MS_LOCAL 50U
#define MAGNET_MAX_TIMEOUT_MS_LOCAL 500U
#endif

static volatile uint32_t g_ms_ticks;
static volatile uint8_t g_rx_ring[RX_RING_SIZE];
static volatile uint16_t g_rx_head;
static volatile uint16_t g_rx_tail;
static volatile uint8_t g_rx_overflow;
static uint8_t g_fault;

uint32_t system_millis(void)
{
    return g_ms_ticks;
}

void SysTick_Handler(void)
{
    uint32_t now = g_ms_ticks + 1U;
    g_ms_ticks = now;
#ifndef STAGE_PING
    magnet_tick_isr(now);
#endif
}

void BOARD_USART_IRQHandler(void)
{
    uint32_t status = BOARD_USART->SR;

    if ((status & (USART_SR_ORE | USART_SR_NE |
                   USART_SR_FE | USART_SR_PE)) != 0U) {
        volatile uint32_t discarded = BOARD_USART->DR;
        (void)discarded;
        g_rx_overflow = 1U;
    } else if ((status & USART_SR_RXNE) != 0U) {
        uint8_t byte = (uint8_t)BOARD_USART->DR;
        uint16_t next = (uint16_t)((g_rx_head + 1U) % RX_RING_SIZE);

        if (next == g_rx_tail) {
            g_rx_overflow = 1U;
        } else {
            g_rx_ring[g_rx_head] = byte;
            g_rx_head = next;
        }
    }
}

static void uart1_init(void)
{
    uint32_t crh;

    BOARD_USART_CLK_ENABLE();

    /* PA9: USART1_TX AF push-pull 50 MHz; PA10: USART1_RX floating input. */
    crh = BOARD_USART_TX_PORT->CRH;
    crh &= ~(((uint32_t)0x0FU << BOARD_USART_TX_MODE_SHIFT) |
             ((uint32_t)0x0FU << BOARD_USART_RX_MODE_SHIFT));
    crh |= ((uint32_t)0x0BU << BOARD_USART_TX_MODE_SHIFT) |
           ((uint32_t)0x04U << BOARD_USART_RX_MODE_SHIFT);
    BOARD_USART_TX_PORT->CRH = crh;

    BOARD_USART->CR1 = 0U;
    BOARD_USART->CR2 = 0U;
    BOARD_USART->CR3 = 0U;
    BOARD_USART->BRR = (SystemCoreClock + (115200U / 2U)) / 115200U;
    BOARD_USART->CR1 = USART_CR1_UE | USART_CR1_TE |
                       USART_CR1_RE | USART_CR1_RXNEIE;

    NVIC_SetPriority(BOARD_USART_IRQn, 2U);
    NVIC_EnableIRQ(BOARD_USART_IRQn);
}

static void uart_write_char(char value)
{
    while ((BOARD_USART->SR & USART_SR_TXE) == 0U) {
    }
    BOARD_USART->DR = (uint16_t)(uint8_t)value;
}

static void uart_write(const char *text)
{
    while (*text != '\0') {
        uart_write_char(*text);
        ++text;
    }
}

static int text_equal(const char *left, const char *right)
{
    while ((*left != '\0') && (*right != '\0') && (*left == *right)) {
        ++left;
        ++right;
    }
    return ((*left == '\0') && (*right == '\0')) ? 1 : 0;
}

#ifndef STAGE_PING
static void uart_write_u32(uint32_t value)
{
    char digits[10];
    uint32_t count = 0U;

    do {
        digits[count] = (char)('0' + (value % 10U));
        value /= 10U;
        ++count;
    } while ((value != 0U) && (count < (uint32_t)sizeof(digits)));

    while (count != 0U) {
        --count;
        uart_write_char(digits[count]);
    }
}

static int parse_timeout(const char *text, uint32_t *value)
{
    uint32_t parsed = 0U;
    uint32_t digits = 0U;

    if (*text == '\0') {
        return 0;
    }

    while (*text != '\0') {
        uint32_t digit;
        if ((*text < '0') || (*text > '9')) {
            return 0;
        }
        digit = (uint32_t)(*text - '0');
        if (parsed > ((UINT32_MAX - digit) / 10U)) {
            return 0;
        }
        parsed = (parsed * 10U) + digit;
        ++digits;
        ++text;
    }

    if ((digits == 0U) ||
        (parsed < MAGNET_MIN_TIMEOUT_MS_LOCAL) ||
        (parsed > MAGNET_MAX_TIMEOUT_MS_LOCAL)) {
        return 0;
    }

    *value = parsed;
    return 1;
}
#endif

static void command_error(const char *reason)
{
#ifndef STAGE_PING
    magnet_force_off();
#endif
    uart_write("ERR ");
    uart_write(reason);
    uart_write("\n");
}

static void process_command(char *command)
{
#ifndef STAGE_PING
    static const char on_prefix[] = "MAGNET_ON ";
    uint32_t index;
    uint32_t timeout_ms;
#endif

    if (text_equal(command, "PING") != 0) {
        uart_write("PONG\n");
        return;
    }

#ifdef STAGE_PING
    /* Stage A accepts only PING; keep output inert. */
    command_error("unknown_command");
    return;
#else
    if (text_equal(command, "GET_STATUS") != 0) {
        uart_write("STATUS MAGNET=");
        uart_write_char((magnet_get_state() != 0U) ? '1' : '0');
        uart_write(" FAULT=");
        uart_write_char((g_fault != 0U) ? '1' : '0');
        uart_write("\n");
        return;
    }

    if (text_equal(command, "MAGNET_OFF") != 0) {
        magnet_force_off();
        g_fault = 0U;
        uart_write("OK OFF\n");
        return;
    }

    if (text_equal(command, "EMERGENCY_OFF") != 0) {
        magnet_force_off();
        g_fault = 0U;
        uart_write("OK OFF\n");
        return;
    }

    index = 0U;
    while ((on_prefix[index] != '\0') &&
           (command[index] == on_prefix[index])) {
        ++index;
    }

    if (on_prefix[index] == '\0') {
        if (parse_timeout(&command[index], &timeout_ms) == 0) {
            command_error("invalid_timeout");
            return;
        }
        if (magnet_turn_on_timed(timeout_ms) == 0) {
            command_error("invalid_timeout");
            return;
        }
        uart_write("OK ON TIMEOUT_MS=");
        uart_write_u32(timeout_ms);
        uart_write("\n");
        return;
    }

    command_error("unknown_command");
#endif
}

static int rx_pop(uint8_t *value)
{
    if (g_rx_tail == g_rx_head) {
        return 0;
    }
    *value = g_rx_ring[g_rx_tail];
    g_rx_tail = (uint16_t)((g_rx_tail + 1U) % RX_RING_SIZE);
    return 1;
}

int main(void)
{
    char command[COMMAND_SIZE];
    uint32_t length = 0U;
    uint8_t discarding = 0U;
    uint8_t byte;

#ifndef STAGE_PING
    magnet_gpio_init_safe();
#endif
    uart1_init();
    if (SysTick_Config(SystemCoreClock / 1000U) != 0U) {
#ifndef STAGE_PING
        magnet_force_off();
#endif
        while (1) {
        }
    }
    NVIC_SetPriority(SysTick_IRQn, 1U);

#ifndef STAGE_PING
    magnet_force_off();
#endif

    while (1) {
        if (g_rx_overflow != 0U) {
            __disable_irq();
            g_rx_tail = g_rx_head;
            g_rx_overflow = 0U;
            __enable_irq();
            length = 0U;
            discarding = 0U;
            g_fault = 1U;
            command_error("rx_overflow");
        }

        while (rx_pop(&byte) != 0) {
            if (byte == (uint8_t)'\r') {
                continue;
            }

            if (byte == (uint8_t)'\n') {
                if (discarding != 0U) {
                    discarding = 0U;
                    length = 0U;
                    g_fault = 1U;
                    command_error("line_too_long");
                } else if (length != 0U) {
                    command[length] = '\0';
                    process_command(command);
                    length = 0U;
                }
                continue;
            }

            if (discarding != 0U) {
                continue;
            }

            if (length >= (COMMAND_SIZE - 1U)) {
#ifndef STAGE_PING
                magnet_force_off();
#endif
                discarding = 1U;
                length = 0U;
            } else {
                command[length] = (char)byte;
                ++length;
            }
        }
    }
}
