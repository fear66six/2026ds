# Security Policy

## Supported versions

Security fixes are applied to the current default branch. Historical competition snapshots, generated run artifacts, local hardware configurations, and vendor examples are not separately supported.

## Reporting a vulnerability

For a vulnerability involving credentials, unsafe hardware behavior, arbitrary command execution, firmware flashing, serial-device access, or personal information, use GitHub's private vulnerability reporting feature for this repository when available. Do not open a public Issue containing exploit details, secrets, device serial numbers, private IP addresses, or unsafe motion commands.

For non-sensitive reliability bugs, use the repository's bug-report template.

Please include:

- the affected commit and file or symbol;
- an offline or Mock reproduction where possible;
- the potential impact and safe containment steps;
- whether any physical device was involved.

Maintainers will acknowledge a private report when available, assess its scope, and coordinate a fix before public disclosure. No response-time guarantee is made.

## Hardware safety is part of security

Code that can move a robot, flash a controller, modify GPIO/device-tree state, or energize an electromagnet must remain explicitly gated, time-bounded, and safe on abnormal exit. A software authorization token does not replace physical supervision, collision checks, an emergency stop, or correct electrical protection.
