#include "magnet_control.h"
#include "stm32f10x.h"

#define MAGNET_PIN ((uint32_t)1U << 12)

static volatile uint8_t g_magnet_on;
static volatile uint32_t g_magnet_deadline_ms;

extern uint32_t system_millis(void);

void magnet_gpio_init_safe(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_IOPBEN;

    /* Preload ODR low before changing PB12 to push-pull output. */
    GPIOB->BRR = MAGNET_PIN;
    GPIOB->CRH = (GPIOB->CRH & ~((uint32_t)0x0FU << 16)) |
                 ((uint32_t)0x02U << 16);
    GPIOB->BRR = MAGNET_PIN;
    g_magnet_on = 0U;
    g_magnet_deadline_ms = 0U;
}

void magnet_force_off(void)
{
    GPIOB->BRR = MAGNET_PIN;
    g_magnet_on = 0U;
}

int magnet_turn_on_timed(uint32_t timeout_ms)
{
    if ((timeout_ms < MAGNET_MIN_TIMEOUT_MS) ||
        (timeout_ms > MAGNET_MAX_TIMEOUT_MS)) {
        magnet_force_off();
        return 0;
    }

    __disable_irq();
    g_magnet_deadline_ms = system_millis() + timeout_ms;
    g_magnet_on = 1U;
    GPIOB->BSRR = MAGNET_PIN;
    __enable_irq();
    return 1;
}

uint8_t magnet_get_state(void)
{
    uint8_t physical_high = ((GPIOB->ODR & MAGNET_PIN) != 0U) ? 1U : 0U;

    if (physical_high != g_magnet_on) {
        magnet_force_off();
        return 0U;
    }
    return g_magnet_on;
}

void magnet_tick_isr(uint32_t now_ms)
{
    if ((g_magnet_on != 0U) &&
        ((int32_t)(now_ms - g_magnet_deadline_ms) >= 0)) {
        magnet_force_off();
    }
}
