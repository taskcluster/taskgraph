# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from datetime import datetime
from taskgraph.test import does_not_raise

from taskgraph.cron import (
    taskgraph_cron,
    _format_and_raise_error_if_any,
)


@pytest.mark.parametrize('force_run, run_job_output, expectation', ((
    'nightly', None, does_not_raise(),
), (
    '', None, does_not_raise(),
), (
    'nightly', Exception('Some generic exception'), pytest.raises(Exception),
), (
    'nightly', ValueError('Some value error'), pytest.raises(ValueError),
), (
    '', Exception('Some generic exception'), pytest.raises(RuntimeError),
), (
    '', ValueError('Some value error'), pytest.raises(RuntimeError),
)))
def test_taskgraph_cron(monkeypatch, force_run, run_job_output, expectation):
    monkeypatch.setattr('taskgraph.cron.calculate_head_rev', lambda _, __: 'someheadrev')
    monkeypatch.setattr('taskgraph.cron.calculate_time', lambda _: datetime())
    monkeypatch.setattr('taskgraph.cron.load_jobs', lambda _, root: {'nightly': {}})
    monkeypatch.setattr('taskgraph.cron.should_run', lambda _, __: True)

    def fake_run_job(*args, **kwargs):
        if run_job_output is None:
            return None
        raise run_job_output
    monkeypatch.setattr('taskgraph.cron.run_job', fake_run_job)

    options = {
        'force_run': force_run,
        'head_ref': 'someheadref',
        'head_repository': 'https://some/repo',
        'level': '1',
        'no_create': False,
        'project': 'some-project',
        'repository_type': 'hg',
    }
    with expectation:
        taskgraph_cron(options)


@pytest.mark.parametrize('failed_jobs, expectation, error_message', ((
    [], does_not_raise(), '',
), (
    [('nightly', ValueError('some error message'))],
    pytest.raises(RuntimeError),
    '''Cron jobs [u'nightly'] couldn't be triggered properly. Reason(s):
 * "nightly": "some error message"
See logs above for details.'''
), (
    [
        ('nightly', ValueError('some error message')),
        ('another-cron-job', ValueError('another error message')),
    ],
    pytest.raises(RuntimeError),
    '''Cron jobs [u'nightly', u'another-cron-job'] couldn't be triggered properly. Reason(s):
 * "nightly": "some error message"
 * "another-cron-job": "another error message"
See logs above for details.'''
)))
def test_format_and_raise_error_if_any(failed_jobs, expectation, error_message):
    with expectation as exc_info:
        _format_and_raise_error_if_any(failed_jobs)

    if exc_info:
        assert exc_info.value.args[0] == error_message
