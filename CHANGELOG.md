# Change Log

## [1.6.0] - 2022-04-24

### Added
- Support for a `toolchain-env` key which gets added to dependent tasks' environment
- Support for `generic-worker` toolchain tasks
- Ability to execute commands using powershell in `run_task` transforms
- Implicitly run toolchain scripts ending in `.ps1` with powershell

### Fixed
- Renaming `toolchain-artifact` now rebuilds toolchain tasks

## [1.5.1] - 2022-05-06

### Fixed
- Git checkout cleaning regression
- Add a mechanism to bypass `--require-hashes` when installing pip dependencies in `run-task`
- Decode gzipped artifacts when using `task-id=` or `project=` in the `--parameters` flag
- Stop defaulting to a dummy `TASKCLUSTER_ROOT_URL` and instead raise error
- Some node dependency upgrades in the `index-task` image

## [1.5.0] - 2022-05-02

### Added
- Ability to pass headers alongside requests in the `fetch-content` script

### Fixed
- An encoding error when using out of tree images
- Windows permissions errors in `run-task` script cleanup

## [1.4.0] - 2022-04-22

### Added
- Add ability to run new types of verifications (e.g doc verifications)
- Allow custom `onExitStatus` values for generic-worker based tasks across all platforms

### Changed
- Decision docker images updated to Ubuntu 20.04 and Mercurial 5.3.1
- Pass parameters into verifications functions

### Fixed
- Don't assume Taskcluster is enabled in generic-worker run-task based tasks
- Exception during local generation when generic-worker tasks exist

## [1.3.1] - 2022-03-22

### Added

- Add pyenv to python docker image

### Fixed

- Point generic worker tasks to TC instance instead of proxy URL
- Fixed some tests for local development

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
