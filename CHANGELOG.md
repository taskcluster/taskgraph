# Change Log

## [3.2.0] - TBD

### Fixed

- `vcs.remote_name` returns the first available remote and warns about it

## [3.1.0] - 2022-09-06

### Added
- SSH repositories are now supported in action tasks

## [3.0.1] - 2022-08-30

### Changed
- `run-task` doesn't pull tags from git `head_repository`

### Fixed
- `util.time.json_time_from_now()` and `util.time.current_json_time()` now always returns milliseconds instead of sometimes rounding it up
- Trimmed `.git` from tc-treeherder route's project

## [3.0.0] - 2022-08-23

### Changed
- BREAKING CHANGE: `TransformConfig.kind_dependencies_tasks` is now a dictionary keyed by task label.
- BREAKING CHANGE: `vcs.head_ref` was renamed into `vcs.head_rev` to clarify that the function returns a revision. This also matches `--head-rev`.
- BREAKING CHANGE: Similarly, `vcs.base_ref` was renamed into `vcs.base_rev`.
- `run-task` now clones all git-submodules at the same time as cloning the base/head repository.
- `run-task` now checks out a revision as a named branch that matches `${PROJECT}_HEAD_REF`
- `head_ref` parameter now points to a named branch and if needed, falls back to the revision hash

### Added
- `vcs.get_changed_files()` which returns a list of files that are changed in this repository's working copy.
- `vcs.get_outgoing_files()` which returns a list of changed files compared to upstream.
- `vcs.remote_name` that tracks the name of the remote repository (e.g.: `default` on `hg` or `origin` on `git`)
- `base_ref` parameter that points to the reference (e.g.: a branch) on the base repository
- `vcs.find_latest_common_revision()` which finds the common ancestor between a provided `base_ref` and the current `head_rev`
- `vcs.does_revision_exist_locally()` to find out if a changeset/commit exists in the locally cloned repository
- `base_rev` parameter that points to the most common ancestor between the ancestors of `head_rev` and `base_ref`
- `@register_morph` decorator which does what the name implies.

### Fixed
- Regression in 2.0.0: action tasks that created new tasks are now green again. ([#99](https://github.com/taskcluster/taskgraph/pull/99)/[#100](https://github.com/taskcluster/taskgraph/pull/100))

## [2.0.0] - 2022-08-01

### Changed

- BREAKING CHANGE: `taskgraph.util.taskcluster.status_task` now returns the status object rather than the string state.
- BREAKING CHANGE: Replacement optimization strategies now take a `deadline` argument.
- BREAKING CHANGE: Replaces `Either` base optimization strategy with an `Any` composite strategy.
- BREAKING CHANGE: `taskgraph.util.WHITELISTED_SCHEMA_IDENTIFIERS` is now `taskgraph.util.EXCEPTED_SCHEMA_IDENTIFIERS`.
- BREAKING CHANGE: The `default` target tasks method now filters out tasks that define a `shipping_phase`.

### Added
- A new `taskgraph.util.taskcluster.state_task` returns the string state (like status_task used to).
- The ability to register custom optimization strategies.
- Added `release_notifications` transforms, enabling tasks to send e-mail notifications. It is usually
  used in the context of releases when you want to inform a group of people about the completion of
  a phase of a release. Notifications can contain data about what project/version reached a given
  phase.
- New parameters: `version`, `next_version`, `build_number`. As of now, they are be used by
  `release_notification` to send e-mails that can contain such data.

## [1.7.1] - 2022-06-22

### Fixed
- Allow JSON-e in schema identifiers

## [1.7.0] - 2022-06-22

### Added
- `run-task` script sets a `TASK_WORKDIR` env pointing to the task specific working directory
- Add `defer` and `enforce_single_match` arguments in `util.schema.resolve_keyed_by`

### Fixed
- Misspelling in job transforms causing utility file to be unnecessarily imported
- Added `if-dependencies` to `job_description_schema` allowing it to be used with job transforms

### Changed
- Refactored logic for importing sibling modules into new `util.python_path.import_sibling_modules`

### Perf
- Skip schema validation when `taskgraph.fast` is set
- Improved performance of `schema.optionally_keyed_by` function

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
