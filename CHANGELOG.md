# Change Log

## [1.1.6] - 2022-02-10

### Fixed

- A bug with custom parameter defaults not being set when running 'taskgraph' locally
- Error in non UTF-8 locales + unicode in commit message
- User specified Taskcluster urls in environment are now normalized

### Changed

- Minor refactor to requests session logic in util/taskcluster.py

## [1.1.5] - 2022-02-02

### Fixed

- Set HGPLAIN environment variable for Mercurial commands in util/vcs.py

## [1.1.4] - 2022-02-01

### Fixed

- Fix exception in default parameters when no git remote named "origin"

## [1.1.3] - 2022-01-24

### Fixed

- Used repository root as default in `get_repository` rather than cwd
- Retry vcs commands in run-task if they failed

## [1.1.2] - 2022-01-22

### Fixed

- An import error with Python 3.10

## [1.1.1] - 2022-01-10

### Fixed

- Search ancestor directories when instantiating repo in `get_repository`

## [1.1.0] - 2022-01-03

### Added

- Support specifying defaults to `extend_parameters_schema` utility
- Added `beetmover` payload builder to `task.py` transforms

### Fixed

- Fixed logging error when using `taskgraph --diff`
- Various fixes to `Repository` utility class in `vcs.py`

## [1.0.1] - 2021-10-01

### Changed

- Relaxed lower bound constraints of some dependencies

## [1.0.0] - 2021-10-01

- Initial release
