#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

/*
 * STM32F103VET6 board pin map for uart magnet firmware.
 *
 * UART status: CONFIRMED by the Stage A PING 20/20 hardware test.
 * The mapping used by that test is:
 *   PA9  = USART1_TX  -> board TXD
 *   PA10 = USART1_RX  <- board RXD
 *
 * Magnet GPIO status: PC0 selected and confirmed by the user from board
 * documentation or continuity measurement, including peripheral conflicts.
 */

#define BOARD_USART                USART1
#define BOARD_USART_IRQn           USART1_IRQn
#define BOARD_USART_IRQHandler     USART1_IRQHandler
#define BOARD_USART_CLK_ENABLE()   (RCC->APB2ENR |= (RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPAEN | RCC_APB2ENR_USART1EN))
#define BOARD_USART_TX_PORT        GPIOA
#define BOARD_USART_RX_PORT        GPIOA
/* PA9 CRH nibble 1, PA10 CRH nibble 2 */
#define BOARD_USART_TX_MODE_SHIFT  4U
#define BOARD_USART_RX_MODE_SHIFT  8U

#define MAGNET_GPIO_PORT           GPIOC
#define MAGNET_GPIO_CLK_ENABLE()   (RCC->APB2ENR |= RCC_APB2ENR_IOPCEN)
#define MAGNET_GPIO_PIN            ((uint32_t)1U << 0)
#define MAGNET_GPIO_CONFIG_REG     (MAGNET_GPIO_PORT->CRL)
/* PC0 uses CRL bits [3:0]. */
#define MAGNET_GPIO_MODE_SHIFT     0U

#define BOARD_UART_CONFIRMED       1
#define BOARD_MAGNET_GPIO_CONFIRMED 1

#endif
