#ifndef STM32F10X_CONF_H
#define STM32F10X_CONF_H

/*
 * This project uses CMSIS register definitions directly and intentionally does
 * not include peripheral-driver headers.  Keep assert_param available because
 * the vendor device header expects the standard configuration hook.
 */
#define assert_param(expr) ((void)0U)

#endif
