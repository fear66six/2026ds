# Changelog

Notable public-facing changes are documented here. This project uses calendar dates because competition hardware snapshots do not yet follow a formal release cadence.

## Unreleased

### Added

- Portfolio-oriented Chinese and English project introductions.
- MIT License, third-party notices, contribution and security policies.
- Offline GitHub Actions CI, repository hygiene checks, and Issue/PR templates.
- Stable showcase assets and architecture/development documentation.

### Changed

- Public documentation now separates source-confirmed behavior, engineering decisions, and pending physical verification.
- Pure third-party ARM/ST support files and generated runtime artifacts are excluded from the public source tree.
- Q1 offline tests now match the segmented transfer path and the controller-duration-plus-settle execution contract used by the current executor.

### Removed

- Tracked caches, temporary analysis files, local logs, firmware build reports, and raw run directories from the public repository snapshot.
