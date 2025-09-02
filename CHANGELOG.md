# Change Log

## [15.1.1] - 2025-09-02

### Fixed

- `task-context` key no longer required for tasks using the `task_context` transforms

## [15.1.0] - 2025-08-29

### Added

- New function `taskgraph.generator.load_tasks_for_kinds` to get multiple kinds in one pass
- Allow the `os-groups` generic-worker feature on linux and mac

### Fixed

- taskgraph build-image regression introduced in 14.6.0

## [15.0.1] - 2025-08-14

### Reverted

- multiprocess kind processing (#746)

## [15.0.0] - 2025-08-13

### Added

- Process kinds in parallel with a pool of processes (#738)
- use `uv` to check python version, when available(#733)

### Changed

- BREAKING CHANGE: Use `primary-dependency-label` attribute to find primary dependency of tasks (#736)

### Fixed

- Fallback to guessing repo root in config.py (#742)

## [14.6.1] - 2025-08-11

### Fixed

- Reverted accidental schema changes to run and toolchain transforms

## [14.6.0] - 2025-08-05

### Added

- `--no-verify` command line flag to disable verifications

### Fixed

- docker-image transforms work with a non-standard `--root`
- accessing `GraphConfig.vcs_root` no longer raises with a non-standard `--root`
- container permission issue when running `taskgraph load-task`
- properly quoted command in `taskgraph load-task`

## [14.5.0] - 2025-06-22

### Added

- add a more descriptive error when a kind cannot be found (#721)
- error out when index routes have a `/` in them (#722)

### Fixed

- handle github submodule checks better in fetch-content (#708)
- make `hash_paths` work when `base_path` is set (#723)
- return dict from 'status_task_batched' when testing (#720)
- retag images when a tag is passed to taskgraph load-image (#713)

## [14.4.1] - 2025-06-04

### Fixed

- file url handling for Thunderbird repos

## [14.4.0] - 2025-06-02

### Added

- support lists in `resolve_keyed_by` (#608)
- improved error message when a kind dependency cannot be found (#696)

### Fixed

- don't decode YAML response before parsing them in get_artifact (#700)

## [14.3.0] - 2025-05-28

### Fixed

- MAX_ROUTES bumped up to actual limit of 64

### Added

- `load-task` command now accepts a `--user` flag to run in container as
- optionally use `orjson` for faster json operations if available

## [14.2.1] - 2025-05-13

### Fixed

- Revert "generic-worker will now verify run-task/fetch-content integrity" from
  14.2.0 for being broken

## [14.2.0] - 2025-05-12

### Fixed

- fix actions scope check on mercurial (#686)

### Changed

- generic-worker will now verify run-task/fetch-content integrity (#666)

### Added

- new 'load-task' command to debug tasks locally (#680)

## [14.1.1] - 2025-04-10

### Fixed

- ensure GraphConfig.root_dir is an absolute path (#673)

## [14.1.0] - 2025-04-07

### Added

- allow task-priority to be keyed by level (#653)
- implement `taskgraph action` command to generate actions.json on the command line (#645)
- pass push.base_revision to in-tree-action hook (#656)
- support for `volume` artifact type (#667)

### Fixed

- bug deleting long path names with forward slashes on Windows (#661)
- replace deprecated datetime.utcnow() with timezone-aware alternative (#652)
- only consider tracked files when building toolchain hashes (#664)

## [14.0.0] - 2025-02-18

### Removed

- BREAKING CHANGE: removed {task_workdir} interpolation in run-task environment variables

## [13.1.0] - 2025-02-13

### Added

- Support for generic-worker's `runAsCurrentUser` feature

### Fixed

- Error handling during docker image builds
- Issue in `get_changed_files()` utility with merge commits in Mercurial
- Deprecation warning in `run-task` with Python 3.12

## [13.0.0] - 2025-01-23

### Added

- automatically interpolate {task_workdir} in environment (#630)
- add caches for common package managers (#623)
- support setting repo wide default values for cache selection (#623)
- support list of caches in `use-caches` key (#623)

### Fixed

- `get_ancestors` now returns tasks keyed by taskid, to avoid missing tasks when multiple tasks exist with the same label in a graph (#633)

### Removed

- unused resource-monitor code (#636)
- `cache-dotcache` key (#623)

## [12.2.0] - 2025-01-15

### Added

- fetch-content: support for downloading a single file and putting it in an archive

### Fixed

- use base repo for project name in github .taskcluster.yml template (#610)
- added False as option in from-deps set-name config (#621)
- fetch-content: use urlopen's context parameter instead of cafile (#618)
- run-task: update our copy of robustcheckout hg extension (#617)
- avoid computing expensive default values when the value is overridden anyways

### Changed

- hash the uncompressed contents of docker context tar (#626)

## [12.1.0] - 2024-11-21

### Added

- fetch-content: log x-cache-status when content size doesn't match expected (#606)

### Fixed

- Don't assume the taskcluster proxy is running on http://taskcluster (#603)
- Do not apply skip-unless-changed for cron triggers (#604)

## [12.0.0] - 2024-10-25

### Added

- New `matrix` transforms added to allow easily splitting tasks
- The `-p/--parameters` flag now supports `index=<index>` as a means of discovering parameters

### Fixed

- BREAKING CHANGE: `target_tasks_method` filter no longer implicitly added if other filters are used
- An OSError when generating docker contexts when many files were involved
- A bug when attempting to find prior actions in Github action tasks
- The `when.files-changed` optimization no longer implicitly adds unrelated `tasks-from` files

### Changed

- BREAKING CHANGE: docker image task labels changed from `build-docker-image` to `docker-image`

## [11.2.4] - 2024-10-16

### Fixed

- Regression to `static-url` fetches when using the `strip_components` or `add_prefix` features

## [11.2.3] - 2024-10-16

### Fixed

- A couple more regressions with the Decision image
  - Cleaned up temporary `uv` lockfile owned by root
  - Added another `--no-cache` flag to a `uv` command
- `run-task` now installs packages to user site dir when installing requirements with `uv`
- Fetch tasks using `static-url` will now properly rename non-archive files

## [11.2.2] - 2024-10-15

### Fixed

- Regression in Decision image where `taskgraph` was no longer on the $PATH
- Decision image no longer contains root owned `uv` cache
- `uv` now included in the `run-task` image

## [11.2.1] - 2024-10-03

### Fixed

- `taskgraph.optimize.register_strategy` can now pass kwargs on to the optimization class

## [11.2.0] - 2024-09-26

### Added

- `taskgraph.config.GraphConfig` now implements a `get(<key>)` method (#577)
- Global tags for `project` and `trust-domain` are now applied to all tasks (#579)

### Fixed

- `run-task` script no longer attempts to chmod `/dev/kvm` if it already has the right permissions (#578)
  - This fixes an issue when using a container with podman

## [11.1.0] - 2024-09-23

### Added

- Use `uv` to install requirements if available (#572)
- Allow 9,999 upstream dependencies on a Task (#575)
  - Taskcluster platform work that enabled this: https://github.com/taskcluster/taskcluster/issues/7151

### Fixed

- Ensure builds don't fail if `/builds` already exists in Dockerfile (#573)
- Add `coreutils` to the `linux` Dockerfile (#573)

## [11.0.0] - 2024-09-04

### Added

- BREAKING CHANGE: removed hardcode python3 path on macOS (#566)
- BREAKING CHANGE: register_action_callback interface has changed (#553)
- Task name is now available in `task_context` (#562)

### Fixed

- get_ancestors ignores 404s to avoid failing when some tasks have already expired (#569)

## [10.0.2] - 2024-07-31

### Fixed

- Error in optimization log message (#554)
- Git file renames now count as changed files for optimization purposes (#555)

## [10.0.1] - 2024-07-23

### Fixed

- Make toolchain and fetch tasks work when there is more than one present, and at least one is defined as a dict (#551)

## [10.0.0] - 2024-07-22

### Added

- BREAKING CHANGE: Bug 1796139 - Pull in fetch-content changes from mozilla-central by @jcristau (#541)
- BREAKING CHANGE: Update image_builder Docker image to version 5.1.0 (#520)
- support fully configured fetches for toolchain and fetch upstreams (#545)

## [9.2.1] - 2024-07-16

### Fixed

- Reverted "fetch-content detects archive type instead of using the file
  extension" change from 9.2.0, for breaking backwards compatibility (#543)

## [9.2.0] - 2024-07-15

### Added

- fetch-content detects archive type instead of using the file extension
- fetch-content validates downloads against server-provided content-length when
  possible, and retries downloads on size or checksum mismatch

### Fixed

- github projects set up by `taskgraph init` now use level 1 for pull request graphs

## [9.1.0] - 2024-07-10

### Added

- Separate log for optimizations that always logs verbosely (#525)
- Retry batched taskcluster requests (#529)
- Allow setting per-task priority (#534)
- Updated ReadOnlyDict vendor (#537)

### Fixed

- Invalid escape in string literal in robustcheckout (#475)
- IndexSearch optimization now logs when it refuses to replace a task (#524)
- Use versioned decision image in cookiecutter .taskcluster.yml files (#528)

## [9.0.0] - 2024-06-11

### Added

- New `taskgraph.util.copy.deepcopy` function to assist deepcopying Task objects efficiently
- Toolchain tasks now support relative script paths

### Fixed

- `taskgraph.util.templates.merge` no longer attempts to merge `by-<attribute>` configs
- Cached task digest now factors in Chain of Trust config
- Updated `verify_routes_notification_filters` to support all valid Taskcluster values

### Removed

- Removed the `taskgraph.util.memoize` utility function

## [8.2.0] - 2024-05-21

### Fixed

- Invalid parameters passed to `IndexSearch` optimization from `docker` utility

### Changed

- `IndexSearch` optimization supports both old and new (from 8.1.0) signatures

## [8.1.0] - 2024-05-08

### Added

- New Taskcluster utility functions to use the new Taskcluster `batch` APIs

### Changed

- Optimization logic uses new `batch` APIs to vastly reduce number of queries made to Taskcluster

## [8.0.1] - 2024-04-24

### Fixed

- Regression to `files-changed` calculation for pull requests (#494)
- Support `**kwargs` in functions wrapped by `taskgraph.util.memoize` (#490)
- Support `--exclude-key` argument when the excluded key may or may not exist (#489)
- Stop requiring REGISTRY and VERSION files for `taskgraph build-image` (#488)

## [8.0.0] - 2024-04-09

### Added

- Ability to use custom name functions in `from_deps` transforms (#484)
- New `from_deps` name function that doesn't strip the dep's kind (#484)
- New cli flag to force using locally generated `files_changed` (#481)

### Fixed

- Support for `artifact-reference` with private artifacts (#485)

### Changed

- Replaced `head_ref` in pull-request cached task routes (#486)
- Created a new `files_changed` parameter (#481)

### Removed

- Removed the `taskgraph.files_changed` module (#481)

## [7.4.0] - 2024-03-26

### Changed

- Don't set 'base_ref' on github-release events (#470)
- Faster yaml loading using the native loader if available (#474)
- Memoize `get_task_definition` and `_get_deps` (#477)

## [7.3.1] - 2024-02-21

### Added

- Create a base docker image containing only run-task


## [7.3.0] - 2024-02-13

### Added

- Support for actions in pull-requests

### Fixed

- Various fixes targeting tarfile reproducibility

## [7.2.1] - 2024-02-08

### Fixed

- Make run-task shebang use /usr/bin/env python3 (#453)

## [7.2.0] - 2024-02-08

### Added

- Improved logging to optimization phase
- Utility function to walk through a task's dependency ancestors

### Fixed

- `taskgraph init` support for github-release events in .taskcluster.yml
- `taskgraph init` .taskcluster.yml passes short refs to run-task
- Check to ensure reserved dependency edge `docker-image` isn't used
- Improved tracebacks when querying json-automationrelevance from hg.mozilla.org fails

## [7.1.2] - 2024-01-31

### Added

- Add a `get_ancestors` helper to find ancestor tasks through the Taskcluster API

## [7.1.1] - 2024-01-24

### Added

- Add a `cache-pull-requests` parameter to `taskcluster/config.yml` to disable caching of tasks on pull requests.

## [7.1.0] - 2024-01-08

### Added

- Add a `task-expires-after` parameter to `taskcluster/config.yml` to set the default value for `expires-after` on level 1 tasks.

## [7.0.3] - 2023-12-21

### Fixed

- Wrong module name being generated in `taskgraph init`
- Exception in `taskgraph test-action-callback` due to wrong default root
- Reverted change causing log spam during optimization phase

## [7.0.2] - 2023-12-19

### Fixed

- Reference to wrong root directory in `taskgraph action-callback`

## [7.0.1] - 2023-12-18

### Fixed

- Ensure pull requests properly use cached tasks
- Print help if no arguments are provided to `taskgraph`
- run-task: pass '--break-system-packages' when installing pip requirements
- Bootstrap Taskgraph 7 with latest decision image
- Update template Dockerfile to work with current alpine:latest base image

## [7.0.0] - 2023-12-05

### Added

- Ability to use dictionary keys with `<task-reference>`
- Body of responses logged on failure in `taskgraph.util.taskcluster`

### Changed

- BREAKING CHANGE: Root directory now considered to be `taskcluster` instead of `taskcluster/ci`
- BREAKING CHANGE: `config.yml` moved from `taskcluster/ci` to `taskcluster`
- BREAKING CHANGE: `taskcluster/ci` renamed to `taskcluster/kinds`
- BREAKING CHANGE: `taskgraph.transforms.job` renamed to `taskgraph.transforms.run`
- BREAKING CHANGE: Renamed `taskgraph.target_tasks._target_task` to `register_target_task`
- BREAKING CHANGE: Switched Decision docker image from Ubuntu 22.04 to Debian 12
- `index-task` docker image upgrade to node v18

### Removed

- BREAKING CHANGE: Dropped support for Python 3.7
- BREAKING CHANGE: Removed `taskgraph.util.decision.make_decision_task`
- BREAKING CHANGE: Removed the `decision-mobile` docker image
- BREAKING CHANGE: Removed `taskgraph.transforms.release_notifications` shim

### Fixed

- BREAKING CHANGE: Stopped hardcoding path to `hg` on MacOS in `run-task`
- Worker caches setup by the `run` transforms now contain the docker image hash if applicable
- `--diff` flag will not fail if only one of the two graph generations failed
- Paths in `taskgraph.util.hash` are normalized for Windows support
- `taskgraph init` template now separates Decision task caches by project

## [6.3.1] - 2023-09-28

### Fixed

- `taskgraph init` no longer derives the project name from local checkout dir
- `run-task` bypasses Git's safe directory feature which breaks caches on multi-user workers
- Fix for `taskgraph load-image` when specifying a name
- `deadline-after` field added to `job_description_schema`

## [6.3.0] - 2023-09-12

### Added

- `--target-kind` flag can be passed to Taskgraph multiple times
- Ability to specify max worker processes when generating graphs in parallel

### Fixed

- `taskgraph.parameters._get_defaults` no longer raises outside of a repository

## [6.2.1] - 2023-08-18

### Fixed

- Exception when running `taskgraph load-image` and `taskgraph build-image`
- Missing Github ssh fingerprints for `ed25519` and `ecdsa-sha2-nistp256` keys in `run-task`
- Improved error message for unsupported repos when running `taskgraph init`
- Stopped assuming `origin` remote in `taskgraph init`
- Suppressed expected stderr logging when running `taskgraph init`

## [6.2.0] - 2023-08-10

### Added

- Don't override all existing dependencies in `from-deps` (allow upstream or downstream transforms to also add them)

### Fixed

- Don't add a `fetches` entry for kinds without artifacts defined in `from-deps`
- Sort fetches by key and artifact to ensure a consistent ordering

## [6.1.0] - 2023-08-04

### Added

- A new `chunking` transform that helps parallelize tasks
- Support for adding `fetches` with `from-deps`
- An option for not overriding task `name` with `from-deps`
- `autoCancelPreviousChecks` is set to `true` when initializing a new GitHub repository with `taskgraph init`

## [6.0.0] - 2023-07-25

### Added

- Support for substituting arbitrary parts of a task definition with `task-context`

### Removed

- `command-context` support in `job` transforms (this can now be implemented with `task-context`)

### Fixed

- Complain when `group_by` functions are attempted to registered twice
- Use `validate_schema` in `from_deps` to avoid breaking `--fast`

## [5.7.0] - 2023-07-20

### Added

- Ability to specify a list of kinds in the `enable_always_target` parameter

### Fixed

- Assertion that payload and index builder names are unique
- Error handling when duplicate `run_using` functions are defined

## [5.6.2] - 2023-07-17

### Fixed

- Relaxed PyYaml dependency constraint to work around a PyYaml issue

## [5.6.1] - 2023-07-14

### Fixed

- Reverted memoize on `load_yaml` utility which causes issues with parallel generations
- Added line to log command used to invoke `run-task`

## [5.6.0] - 2023-07-10

### Added

- Support for overriding the default task deadline in `ci/config.yml`

## [5.5.0] - 2023-07-06

### Added

- Support for Mercurial 6.0+ in `robustcheckout` script
- Added an `all` group for the `from_deps` transforms
- Added support for the `purgeCaches` feature of `generic-worker`

### Fixed

- Added missing line feed to Python version log in `run-task` script
- Return null revision when no common ancestor found in `repo.find_latest_common_revision`
- Added `--force` flag when updating Git submodules in `run-task` script
- Fix ImportError with old versions of Python (fail on version check instead)

## [5.4.0] - 2023-06-13

### Fixed

- Regression in add-new-jobs and retrigger actions, introduced in 5.1.0.

### Changed

- Replaced 'attrs' with 'dataclasses'

## [5.3.0] - 2023-06-08

### Fixed

- Disallow extraneous keys in the `from-deps` config
- `run-task` now fetches tags when necessary after cloning repo

### Added

- New `from-deps.unique-kinds` key to allow depending on multiple tasks of a kind
- New `get_dependencies` and `get_primary_dependency` functions in `taskgraph.util.dependencies`
- `run-task` now logs the Python version it was invoked with

## [5.2.1] - 2023-05-31

### Fixed

- Bug preventing use of custom `group_by` functions with `from_deps` transforms

## [5.2.0] - 2023-05-26

### Added

- New `from_deps` transforms for creating follow-up tasks

### Fixed

- Parallel generation (via multiple params) returns non-zero if one fails

## [5.1.1] - 2023-05-23

### Fixed

- Regression around make index transform running out of order
- Counted `if-dependencies` and `soft-dependencies` towards dependency limit check
- Error messaging when Docker is stopped
- Error messaging when invalid non-existent dependencies are added
- Command line exception when branch name contains a `/`
- Abort long running Git clone / fetch when transfer is too slow

## [5.1.0] - 2023-04-18

### Added

- New `default` loader which implicitly uses the `job` and `task` transforms
- Support for a custom command to invoke `run-task` in the `job.run_task` transforms
- Can omit object (default: `transforms`) when listing transforms in a kind config
- Ability to specify `treeherder: true` which will auto-populate Treeherder metadata
- Added `index-path-regexes` key to `config.yml` which can be used with `make_index_task` morph

### Fixed

- Stop injecting `docker-image` tasks when DONTBUILD is used in commit message

## [5.0.1] - 2023-03-31

### Changed

- `fetch-content` and `robustcheckout` time out on idle http connections

## [5.0.0] - 2023-03-27

### Removed

- Support for python 3.6

### Changed

- Updated github ssh host key (per https://github.blog/2023-03-23-we-updated-our-rsa-ssh-host-key/)

## [4.3.0] - 2023-03-09

### Added

- A `taskgraph init` command to bootstrap projects on Firefox-CI

### Fixed

- DONTBUILD in a commit message now works for Github pushes

### Changed

- `fetch-content` script now uses `unzip -q` to avoid polluting logs

## [4.2.0] - 2023-02-28

### Added

- Python 3.11 is now tested in CI
- Support for `.tgz` file extension in `fetch-content` script
- Extra arguments now forwarded from `job.toolchain` transforms to `job.run_task`
- All calls to `util.yaml.load_yaml` are now memoized
- Support for `command-context.from-file` in `run_task` transforms
- Worker provisioner / type can be formatted with alias and trust-domain in `config.yml`

### Fixed

- `util.vcs.get_commit_message` actually uses its `revision` parameter

## [4.1.1] - 2023-01-05

### Fixed

- `run-task` is able to git-checkout non-default branch
- `util.hash.hash_paths()` takes much less time to run when provided with 10+ patterns.

## [4.1.0] - 2022-12-05

### Added

- `shipping-phase` attribute in `task` and `job` transforms.

## [4.0.0] - 2022-12-02

### Removed

- Support for `disableSeccomp` capability. This was removed in Taskcluster 45.0.0 as it was
  determined to be unnecessary.

## [3.7.0] - 2022-11-25

### Added

- New `rebuild_cached_tasks` action to facilitate regenerating long-lived tasks

### Changed

- Updated `image_builder` Docker image to version 5.0.0

## [3.6.0] - 2022-11-16

### Added
- Support for Matrix, Slack and pulse in notify transforms

### Changed
- Renamed `taskgraph.transforms.release_notifications` to `taskgraph.transforms.notify`
  (including backwards compatible shim)

## [3.5.2] - 2022-11-04

### Fixed
- `taskgraph.parameters._get_defaults` catches `mozilla_repo_urls.errors.UnsupportedPlatformError` in order not to bust `mach` commands

## [3.5.1] - 2022-11-02

### Fixed
- Only depend on zstandard in the 'load-image' extra to avoid large (likely unused) binaries

## [3.5.0] - 2022-10-31

### Added

- Ability to enable/disable the `always_target` attribute via a new `enable_always_target` parameter

## [3.4.0] - 2022-10-28

### Added
- `fetch-content` has improved support for git submodules
- `fetch-content` can fetch private git repositories over ssh
- `fetch-content` can optionally use chain-of-trust artifacts to validate downloads
- `fetch-content` supports repacking tar archives containing symbolic links
- `fetch-content` repacks now use the same format as the original archive
- `fetch-content` can be told to keep the `.git` directory
- `fetch-content` takes care to log git commit ids even when pointed at a branch name
- `fetch-content` uses github's archive generator to speed up cloning
- Support for the disableSeccomp capability in docker-worker v44.22.0

### Fixed
- `taskgraph load-image` CLI command can now run without raising a `ModuleNotFoundError`.

## [3.3.0] - 2022-10-12

### Added
- Ability to override optimization strategies via parameter

### Removed
- Support for pinning hg.mozilla.org fingerprint in `run-task` as it is no longer necessary

### Fixed
- Use proper Treeherder route for `github-pull-request-untrusted`
- Use `parameters_loader` in `generator.load_tasks_for_kind`
- Run initial verifications after calling `register`

## [3.2.1] - 2022-09-22

### Fixed
- `parameters._get_defaults` doesn't fail if `mozilla-repo-urls` didn't manage to parse the URL. Instead, it just provides empty `base_repository`, `head_repository`, and `project`.
- Similarly, `parameters._get_defaults` doesn't try to determine an accurate `base_rev` and `base_ref` anymore. This caused too many issues on developers' laptops. It provides now empty strings too.


## [3.2.0] - 2022-09-13

### Fixed

- `vcs.remote_name` returns the first available remote and warns about it
- `vcs.default_branch` returns the remote branch because the local one may not exist
- `taskgraph.parameters._get_defaults` trims `.git` from project when repository URL ends with `.git`

### Added

- `vcs.default_branch` now takes git-cinnabar into account when guessing default branch.

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
