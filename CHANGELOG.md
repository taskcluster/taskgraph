# Change Log

## [1.3.0] - 2022-03-18

### Added

- Decision tasks uploads `run-task` and `fetch-content` scripts as artifacts

### Fixed

- Forward `description` and `if-dependencies` keys to Task constructor

## [1.2.0] - 2022-03-09

### Added

- An ``--exclude-key`` flag to the CLI for removing subsections of tasks
- Concept of [if-dependencies][0] to optimization logic
- Optional description attribute to `Task` objects

[0]: https://taskcluster-taskgraph.readthedocs.io/en/latest/concepts/task-graphs.html#if-dependencies

### Changed

- A minor refactor to optimization logic around logging
- Ability for `run-task` to install Python dependencies after cloning a repo

## [1.1.7] - 2022-02-18

### Fixed

- An exception in default parameters if repo url doesn't contain slashes
- Support `taskgraph test-action-callback` in `run_task` transforms

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
