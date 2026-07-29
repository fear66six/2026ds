#include <stdint.h>
#include "stm32f10x.h"
#include "magnet_control.h"

#define RX_RING_SIZE 128U
#define COMMAND_SIZE 64U

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
    magnet_tick_isr(now);
}

void USART1_IRQHandler(void)
{
    uint32_t status = USART1->SR;

    if ((status & (USART_SR_ORE | USART_SR_NE |
                   USART_SR_FE | USART_SR_PE)) != 0U) {
        volatile uint32_t discarded = USART1->DR;
        (void)discarded;
        g_rx_overflow = 1U;
    } else if ((status & USART_SR_RXNE) != 0U) {
        uint8_t byte = (uint8_t)USART1->DR;
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

    RCC->APB2ENR |= RCC_APB2ENR_AFIOEN |
                    RCC_APB2ENR_IOPAEN |
                    RCC_APB2ENR_USART1EN;

    /* PA9: USART1_TX alternate-function push-pull, 50 MHz. */
    /* PA10: USART1_RX floating input. */
    crh = GPIOA->CRH;
    crh &= ~(((uint32_t)0x0FU << 4) | ((uint32_t)0x0FU << 8));
    crh |= ((uint32_t)0x0BU << 4) | ((uint32_t)0x04U << 8);
    GPIOA->CRH = crh;

    USART1->CR1 = 0U;
    USART1->CR2 = 0U; /* one stop bit */
    USART1->CR3 = 0U; /* no flow control */
    USART1->BRR = (SystemCoreClock + (115200U / 2U)) / 115200U;
    USART1->CR1 = USART_CR1_UE | USART_CR1_TE |
                  USART_CR1_RE | USART_CR1_RXNEIE;

    NVIC_SetPriority(USART1_IRQn, 2U);
    NVIC_EnableIRQ(USART1_IRQn);
}

static void uart_write_char(char value)
{
    while ((USART1->SR & USART_SR_TXE) == 0U) {
        /* SysTick remains enabled, so a timed magnet-on still expires. */
    }
    USART1->DR = (uint16_t)(uint8_t)value;
}

static void uart_write(const char *text)
{
    while (*text != '\0') {
        uart_write_char(*text);
        ++text;
    }
}

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

static int text_equal(const char *left, const char *right)
{
    while ((*left != '\0') && (*right != '\0') && (*left == *right)) {
        ++left;
        ++right;
    }
    return ((*left == '\0') && (*right == '\0')) ? 1 : 0;
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
        (parsed < MAGNET_MIN_TIMEOUT_MS) ||
        (parsed > MAGNET_MAX_TIMEOUT_MS)) {
        return 0;
    }

    *value = parsed;
    return 1;
}

static void command_error(const char *reason)
{
    magnet_force_off();
    uart_write("ERR ");
    uart_write(reason);
    uart_write("\n");
}

static void process_command(char *command)
{
    static const char on_prefix[] = "MAGNET_ON ";
    uint32_t index;
    uint32_t timeout_ms;

    if (text_equal(command, "PING") != 0) {
        uart_write("PONG\n");
        return;
    }

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

    magnet_gpio_init_safe();
    uart1_init();
    if (SysTick_Config(SystemCoreClock / 1000U) != 0U) {
        magnet_force_off();
        while (1) {
            /* Unsafe timing configuration: remain off and do not accept ON. */
        }
    }
    NVIC_SetPriority(SysTick_IRQn, 1U);

    magnet_force_off();

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
                magnet_force_off();
                discarding = 1U;
                length = 0U;
            } else {
                command[length] = (char)byte;
                ++length;
            }
        }
    }
}
