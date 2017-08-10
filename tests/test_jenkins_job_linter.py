# Copyright (C) 2017  Daniel Watkins <daniel@daniel-watkins.co.uk>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import configparser
import os

import pytest
from click.testing import CliRunner

from jenkins_job_linter import lint_job_xml, lint_jobs_from_directory, main
from jenkins_job_linter.linters import Linter, LintResult

from .mocks import create_mock_for_class, get_config, get_LINTERS_for_linters


class TestLintJobXML:

    def test_all_linters_called_with_tree_and_config(self, mocker):
        linter_mocks = [create_mock_for_class(Linter) for _ in range(3)]
        mocker.patch('jenkins_job_linter.LINTERS',
                     get_LINTERS_for_linters(linter_mocks))
        config = get_config()
        lint_job_xml('job_name', mocker.sentinel.tree, config)
        for linter_mock in linter_mocks:
            assert linter_mock.call_count == 1
            assert linter_mock.call_args == mocker.call(mocker.sentinel.tree,
                                                        config)

    @pytest.mark.parametrize('expected,results', (
        (True, (LintResult.PASS,)),
        (True, (LintResult.PASS, LintResult.PASS)),
        (False, (LintResult.PASS, LintResult.FAIL)),
        (False, (LintResult.PASS, LintResult.FAIL, LintResult.PASS)),
    ))
    def test_result_aggregation(self, mocker, expected, results):
        linter_mocks = []
        for result in results:
            mock = create_mock_for_class(Linter, check_result=result)
            linter_mocks.append(mock)
        mocker.patch('jenkins_job_linter.LINTERS',
                     get_LINTERS_for_linters(linter_mocks))
        assert lint_job_xml('job_name', mocker.sentinel.tree,
                            mocker.MagicMock()) is expected

    def test_linters_can_return_text(self, mocker):
        linter_mock = create_mock_for_class(
            Linter, check_result=LintResult.FAIL, check_msg='msg')
        mocker.patch('jenkins_job_linter.LINTERS',
                     get_LINTERS_for_linters([linter_mock]))
        assert lint_job_xml('job_name', mocker.sentinel.tree,
                            mocker.MagicMock()) is False

    def test_disable_linters_config(self, mocker):
        linters = {
            'disable_me': create_mock_for_class(Linter),
            'not_me': create_mock_for_class(Linter),
        }
        mocker.patch('jenkins_job_linter.LINTERS', linters)
        config = {'job_linter': {'disable_linters': ['disable_me']}}
        lint_job_xml('job_name', mocker.Mock(), config)
        assert 0 == linters['disable_me'].call_count
        assert 1 == linters['not_me'].call_count


class TestLintJobsFromDirectory:

    def test_empty_directory(self, mocker):
        listdir_mock = mocker.patch('jenkins_job_linter.os.listdir')
        listdir_mock.return_value = []
        assert lint_jobs_from_directory('dir', mocker.MagicMock())

    def test_job_name_and_tree_passed_to_lint_job_xml(self, mocker):
        listdir_mock = mocker.patch('jenkins_job_linter.os.listdir')
        listdir_mock.return_value = ['some', 'files']
        et_parse_mock = mocker.patch('jenkins_job_linter.ElementTree.parse')
        lint_job_xml_mock = mocker.patch('jenkins_job_linter.lint_job_xml')
        lint_jobs_from_directory('dir', mocker.MagicMock())
        assert len(listdir_mock.return_value) == lint_job_xml_mock.call_count
        for filename in listdir_mock.return_value:
            assert (
                mocker.call(filename, et_parse_mock.return_value, mocker.ANY)
                in lint_job_xml_mock.call_args_list)

    def test_passed_directory_is_used_for_listing(self, mocker):
        listdir_mock = mocker.patch('jenkins_job_linter.os.listdir')
        listdir_mock.return_value = []
        dirname = 'dir'
        lint_jobs_from_directory(dirname, mocker.MagicMock())
        assert mocker.call(dirname) == listdir_mock.call_args

    def test_constructed_paths_used_for_parsing(self, mocker):
        listdir_mock = mocker.patch('jenkins_job_linter.os.listdir')
        listdir_mock.return_value = ['some', 'files']
        et_parse_mock = mocker.patch('jenkins_job_linter.ElementTree.parse')
        mocker.patch('jenkins_job_linter.lint_job_xml')
        dirname = 'dir'
        lint_jobs_from_directory(dirname, mocker.MagicMock())
        expected_paths = set(
            os.path.join(dirname, f) for f in listdir_mock.return_value)
        assert expected_paths == set(
            [call_args[0][0] for call_args in et_parse_mock.call_args_list])

    def test_filtered_config_passed_to_lint_job_xml(self, mocker):
        mocker.patch('jenkins_job_linter.config.CONFIG_DEFAULTS', {})
        config = configparser.ConfigParser()
        config.read_dict({'jenkins': {},
                          'job_builder': {},
                          'something_else': {},
                          'job_linter': {}})
        listdir_mock = mocker.patch('jenkins_job_linter.os.listdir')
        listdir_mock.return_value = ['some', 'files']
        mocker.patch('jenkins_job_linter.ElementTree.parse')
        lint_job_xml_mock = mocker.patch('jenkins_job_linter.lint_job_xml')
        lint_jobs_from_directory('dirname', config)
        passed_config = lint_job_xml_mock.call_args[0][2]
        assert ['job_linter'] == passed_config.sections()

    def test_config_passed_in_isnt_modified(self, mocker):
        config = configparser.ConfigParser()
        config.read_dict({'jenkins': {},
                          'job_builder': {},
                          'something_else': {},
                          'job_linter': {}})
        expected_sections_after = config.sections()
        listdir_mock = mocker.patch('jenkins_job_linter.os.listdir')
        listdir_mock.return_value = ['some', 'files']
        mocker.patch('jenkins_job_linter.ElementTree.parse')
        mocker.patch('jenkins_job_linter.lint_job_xml')
        lint_jobs_from_directory('dirname', config)
        assert expected_sections_after == config.sections()

    def test_defaults_used(self, mocker):
        listdir_mock = mocker.patch('jenkins_job_linter.os.listdir')
        listdir_mock.return_value = ['some', 'files']
        mocker.patch('jenkins_job_linter.ElementTree.parse')
        lint_job_xml_mock = mocker.patch('jenkins_job_linter.lint_job_xml')
        defaults = {'job_linter': {'test': 'this'}}
        mocker.patch('jenkins_job_linter.config.CONFIG_DEFAULTS', defaults)
        lint_jobs_from_directory('dirname', configparser.ConfigParser())
        passed_config = lint_job_xml_mock.call_args[0][2]
        assert passed_config['job_linter']['test'] == 'this'


class TestMain:

    def test_argument_passed_through(self, mocker):
        runner = CliRunner()
        dirname = 'some_dir'
        lint_jobs_mock = mocker.patch(
            'jenkins_job_linter.lint_jobs_from_directory')

        with runner.isolated_filesystem():
            os.mkdir(dirname)
            runner.invoke(main, [dirname])

        assert 1 == lint_jobs_mock.call_count
        assert mocker.call(dirname, mocker.ANY) == lint_jobs_mock.call_args

    def test_config_parsed_and_passed(self, mocker):
        runner = CliRunner()
        lint_jobs_mock = mocker.patch(
            'jenkins_job_linter.lint_jobs_from_directory')
        dirname = 'dirname'
        config = '[job_linter]\nkey=value'
        with runner.isolated_filesystem():
            os.mkdir(dirname)
            with open('config.ini', 'w') as config_ini:
                config_ini.write(config)
            runner.invoke(main, [dirname, '--conf', 'config.ini'])

        assert 1 == lint_jobs_mock.call_count
        config = lint_jobs_mock.call_args[0][1]
        assert config['job_linter']['key'] == 'value'

    @pytest.mark.parametrize('return_value,exit_code', ((False, 1), (True, 0)))
    def test_exit_code(self, mocker, exit_code, return_value):
        runner = CliRunner()
        lint_jobs_mock = mocker.patch(
            'jenkins_job_linter.lint_jobs_from_directory')
        lint_jobs_mock.return_value = return_value
        dirname = 'some_dir'
        with runner.isolated_filesystem():
            os.mkdir(dirname)
            result = runner.invoke(main, [dirname])
        assert exit_code == result.exit_code

    @pytest.mark.parametrize('func', [
        # Non-existent directory
        lambda dirname: None,
        # Directory is a file
        lambda dirname: open(dirname, 'a').close(),
        # Directory isn't readable ("or" because os.mkdir returns None)
        lambda dirname: os.mkdir(dirname) or os.chmod(dirname, 0o000),
    ])
    def test_bad_directory_input(self, func, mocker):
        runner = CliRunner()
        lint_jobs_mock = mocker.patch(
            'jenkins_job_linter.lint_jobs_from_directory')
        dirname = 'dirname'
        with runner.isolated_filesystem():
            func(dirname)
            result = runner.invoke(main, [dirname])
        assert result.exit_code != 0
        assert lint_jobs_mock.call_count == 0

    @pytest.mark.parametrize('func', [
        # Non-existent conf file
        lambda conf: None,
        # Conf file is a directory
        lambda conf: os.mkdir(conf),
        # File isn't readable ("or" because .close() returns None)
        lambda conf: open(conf, 'a').close() or os.chmod(conf, 0o000),
    ])
    def test_bad_config_input(self, func, mocker):
        runner = CliRunner()
        lint_jobs_mock = mocker.patch(
            'jenkins_job_linter.lint_jobs_from_directory')
        dirname = 'dirname'
        conf = 'conf.ini'
        with runner.isolated_filesystem():
            os.mkdir(dirname)
            func(conf)
            result = runner.invoke(main, [dirname, '--conf', conf])
        assert result.exit_code != 0
        assert lint_jobs_mock.call_count == 0
