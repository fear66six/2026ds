# Safety constraints

- PB12 is preloaded and driven low at the beginning of `SystemInit`, before
  clock-tree reconfiguration, and is driven low again at application startup.
- Only the explicit timed `MAGNET_ON` command can set PB12 high.
- The allowed duration is 50-500 ms and expiration uses wrap-safe 32-bit tick
  subtraction.
- Reset does not restore prior state.
- Parser errors, RX ring overflow, UART framing/parity/noise/overrun errors, and
  SysTick configuration failure keep or force the output off.
- No automatic-on, periodic-on, PWM, USB CDC, or PC13 MOSFET control exists.
- `GET_STATUS` cross-checks software state against the physical PB12 ODR bit and
  forces off if they disagree.

The active-high MOSFET behavior is a project decision supplied by the user, not
confirmed by the vendor sample (which uses PC13). Verify the real module input
logic and idle voltage without a load before connecting the electromagnet.

