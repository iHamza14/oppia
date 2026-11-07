# Copyright 2026 The Oppia Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for scripts/check_backend_tests_to_run.py."""

from __future__ import annotations

import builtins
import io
import os
import subprocess
import tempfile
from typing import Dict, List

from core.tests import test_utils
from scripts import check_backend_tests_to_run


class CheckBackendTestsToRunTests(test_utils.GenericTestBase):
    """Unit tests for scripts/check_backend_tests_to_run.py."""

    def setUp(self) -> None:
        super().setUp()
        self.mock_shards_spec: Dict[str, List[str]] = {
            '1': [
                'core.controllers.profile_test',
                'core.controllers.editor_test',
            ],
            '2': ['core.domain.user_services_test'],
            '3': ['scripts.check_backend_tests_to_run_test'],
        }

    def test_get_git_diff_name_status_files_success(self) -> None:
        class MockProcess:
            def communicate(self) -> tuple[bytes, bytes]:
                return (
                    b'M\tcore/controllers/profile.py\n'
                    b'A\tcore/controllers/profile_test.py\n'
                    b'R100\told_path.py\tcore/domain/user_services.py\n',
                    b'',
                )

        swap_popen = self.swap(
            subprocess, 'Popen', lambda *args, **kwargs: MockProcess()
        )
        with swap_popen:
            diff_files = (
                check_backend_tests_to_run.get_git_diff_name_status_files(
                    'base_sha', 'head_sha'
                )
            )
        self.assertEqual(
            diff_files,
            [
                'core/controllers/profile.py',
                'core/controllers/profile_test.py',
                'core/domain/user_services.py',
            ],
        )

    def test_get_git_diff_name_status_files_failure(self) -> None:
        class MockProcess:
            def communicate(self) -> tuple[bytes, bytes]:
                return b'', b'Git error occurred'

        swap_popen = self.swap(
            subprocess, 'Popen', lambda *args, **kwargs: MockProcess()
        )
        with swap_popen, self.assertRaisesRegex(
            ValueError, 'Git error occurred'
        ):
            check_backend_tests_to_run.get_git_diff_name_status_files(
                'base_sha', 'head_sha'
            )

    def test_is_global_backend_file(self) -> None:
        self.assertTrue(
            check_backend_tests_to_run.is_global_backend_file(
                'requirements.txt'
            )
        )
        self.assertTrue(
            check_backend_tests_to_run.is_global_backend_file(
                'core/storage/base_model.py'
            )
        )
        self.assertTrue(
            check_backend_tests_to_run.is_global_backend_file(
                'core/platform/search/gae_search_services.py'
            )
        )
        self.assertFalse(
            check_backend_tests_to_run.is_global_backend_file(
                'core/controllers/profile.py'
            )
        )
        self.assertFalse(
            check_backend_tests_to_run.is_global_backend_file('README.md')
        )

    def test_load_backend_test_shards(self) -> None:
        shards = check_backend_tests_to_run.load_backend_test_shards()
        self.assertIn('1', shards)
        self.assertIn('5', shards)

    def test_extract_imported_modules_from_ast_non_existent_file(self) -> None:
        imports = check_backend_tests_to_run.extract_imported_modules_from_ast(
            'non_existent_file.py'
        )
        self.assertEqual(imports, set())

    def test_extract_imported_modules_from_ast_syntax_error(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False
        ) as tmp:
            tmp.write('def broken_syntax(:\n')
            tmp_path = tmp.name

        try:
            imports = (
                check_backend_tests_to_run.extract_imported_modules_from_ast(
                    tmp_path
                )
            )
            self.assertEqual(imports, set())
        finally:
            os.remove(tmp_path)

    def test_extract_imported_modules_from_ast_valid(self) -> None:
        code = (
            'import os\n'
            'import sys as system\n'
            'from core.domain import user_services, exp_services\n'
            'from core.controllers import profile\n'
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            imports = (
                check_backend_tests_to_run.extract_imported_modules_from_ast(
                    tmp_path
                )
            )
            self.assertIn('os', imports)
            self.assertIn('sys', imports)
            self.assertIn('core.domain', imports)
            self.assertIn('core.domain.user_services', imports)
            self.assertIn('core.domain.exp_services', imports)
            self.assertIn('core.controllers', imports)
            self.assertIn('core.controllers.profile', imports)
        finally:
            os.remove(tmp_path)

    def test_get_associated_test_module_from_file_non_py(self) -> None:
        self.assertIsNone(
            check_backend_tests_to_run.get_associated_test_module_from_file(
                'README.md'
            )
        )

    def test_get_associated_test_module_from_file_test_file_exists(
        self,
    ) -> None:
        swap_exists = self.swap(os.path, 'exists', lambda path: True)
        with swap_exists:
            res = (
                check_backend_tests_to_run.get_associated_test_module_from_file(
                    'core/controllers/profile_test.py'
                )
            )
        self.assertEqual(res, 'core.controllers.profile_test')

    def test_get_associated_test_module_from_file_test_file_does_not_exist(
        self,
    ) -> None:
        swap_exists = self.swap(os.path, 'exists', lambda path: False)
        with swap_exists:
            res = (
                check_backend_tests_to_run.get_associated_test_module_from_file(
                    'core/controllers/deleted_test.py'
                )
            )
        self.assertIsNone(res)

    def test_get_associated_test_module_from_file_prod_file_test_exists(
        self,
    ) -> None:
        def mock_exists(path: str) -> bool:
            return path == 'core/controllers/profile_test.py'

        swap_exists = self.swap(os.path, 'exists', mock_exists)
        with swap_exists:
            res = (
                check_backend_tests_to_run.get_associated_test_module_from_file(
                    'core/controllers/profile.py'
                )
            )
        self.assertEqual(res, 'core.controllers.profile_test')

    def test_get_associated_test_module_from_file_prod_file_test_not_exists(
        self,
    ) -> None:
        swap_exists = self.swap(os.path, 'exists', lambda path: False)
        with swap_exists:
            res = (
                check_backend_tests_to_run.get_associated_test_module_from_file(
                    'core/controllers/no_test.py'
                )
            )
        self.assertIsNone(res)

    def test_get_affected_backend_test_modules_global_file(self) -> None:
        run_all, targets, changed = (
            check_backend_tests_to_run.get_affected_backend_test_modules(
                ['requirements.txt', 'core/controllers/profile.py'],
                shards_spec=self.mock_shards_spec,
            )
        )
        self.assertTrue(run_all)
        self.assertEqual(
            targets,
            [
                'core.controllers.editor_test',
                'core.controllers.profile_test',
                'core.domain.user_services_test',
                'scripts.check_backend_tests_to_run_test',
            ],
        )
        self.assertEqual(changed, ['core/controllers/profile.py'])

    def test_get_affected_backend_test_modules_non_backend_files(self) -> None:
        run_all, targets, changed = (
            check_backend_tests_to_run.get_affected_backend_test_modules(
                ['README.md', 'core/templates/pages/base.html'],
                shards_spec=self.mock_shards_spec,
            )
        )
        self.assertFalse(run_all)
        self.assertEqual(targets, [])
        self.assertEqual(changed, [])

    def test_get_affected_backend_test_modules_specific_backend_files(
        self,
    ) -> None:
        swap_exists = self.swap(os.path, 'exists', lambda path: True)

        def mock_extract(path: str) -> set[str]:
            if 'profile_test' in path:
                return {'core.controllers.profile', 'core.domain.user_services'}
            return set()

        swap_extract = self.swap(
            check_backend_tests_to_run,
            'extract_imported_modules_from_ast',
            mock_extract,
        )

        with swap_exists, swap_extract:
            run_all, targets, changed = (
                check_backend_tests_to_run.get_affected_backend_test_modules(
                    ['core/domain/user_services.py'],
                    shards_spec=self.mock_shards_spec,
                )
            )

        self.assertFalse(run_all)
        # Both user_services_test (associated test) and profile_test
        # (imports user_services) should be affected.
        self.assertEqual(
            targets,
            [
                'core.controllers.profile_test',
                'core.domain.user_services_test',
            ],
        )
        self.assertEqual(changed, ['core/domain/user_services.py'])

    def test_get_affected_backend_test_modules_exceeds_threshold(self) -> None:
        mock_shards: Dict[str, List[str]] = {
            '1': [f'test_module_{i}_test' for i in range(40)]
        }
        swap_exists = self.swap(os.path, 'exists', lambda path: True)
        swap_threshold = self.swap(
            check_backend_tests_to_run, 'MAX_TESTS_BEFORE_FULL_RUN', 2
        )

        def mock_extract(path: str) -> set[str]:
            return {'core.domain.common'}

        swap_extract = self.swap(
            check_backend_tests_to_run,
            'extract_imported_modules_from_ast',
            mock_extract,
        )

        with swap_exists, swap_threshold, swap_extract:
            run_all, targets, changed = (
                check_backend_tests_to_run.get_affected_backend_test_modules(
                    ['core/domain/common.py'], shards_spec=mock_shards
                )
            )

        self.assertTrue(run_all)
        self.assertEqual(len(targets), 40)
        self.assertEqual(changed, ['core/domain/common.py'])

    def test_output_variable_to_github_workflow_without_env(self) -> None:
        swap_environ = self.swap(os, 'environ', {})
        print_output: List[str] = []
        swap_print = self.swap(
            builtins, 'print', lambda msg, **kwargs: print_output.append(msg)
        )
        with swap_environ, swap_print:
            check_backend_tests_to_run.output_variable_to_github_workflow(
                'TEST_VAR', 'val'
            )
        self.assertEqual(print_output, ['TEST_VAR=val'])

    def test_output_variable_to_github_workflow_with_env(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            swap_environ = self.swap(os, 'environ', {'GITHUB_OUTPUT': tmp_path})
            with swap_environ:
                check_backend_tests_to_run.output_variable_to_github_workflow(
                    'MY_OUTPUT', 'result_123'
                )
            with open(tmp_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('MY_OUTPUT=result_123\n', content)
        finally:
            os.remove(tmp_path)

    def test_main_with_output_all_test_suites(self) -> None:
        output_vars: Dict[str, str] = {}

        def mock_output(var: str, val: str) -> None:
            output_vars[var] = val

        swap_output = self.swap(
            check_backend_tests_to_run,
            'output_variable_to_github_workflow',
            mock_output,
        )
        swap_load = self.swap(
            check_backend_tests_to_run,
            'load_backend_test_shards',
            lambda: self.mock_shards_spec,
        )

        with swap_output, swap_load:
            check_backend_tests_to_run.main(
                args=[
                    '--github_head_ref',
                    'HEAD',
                    '--github_base_ref',
                    'develop',
                    '--output_all_test_suites',
                ]
            )

        self.assertEqual(output_vars['RUN_ALL_TESTS'], 'true')
        self.assertEqual(output_vars['NUM_TESTS'], '4')
        self.assertEqual(output_vars['SHARDS_TO_RUN'], '[1, 2, 3, 4, 5]')

    def test_main_with_diff_results(self) -> None:
        output_vars: Dict[str, str] = {}

        def mock_output(var: str, val: str) -> None:
            output_vars[var] = val

        swap_output = self.swap(
            check_backend_tests_to_run,
            'output_variable_to_github_workflow',
            mock_output,
        )
        swap_load = self.swap(
            check_backend_tests_to_run,
            'load_backend_test_shards',
            lambda: self.mock_shards_spec,
        )
        swap_diff = self.swap(
            check_backend_tests_to_run,
            'get_git_diff_name_status_files',
            lambda left, right: ['core/controllers/profile.py'],
        )
        swap_exists = self.swap(os.path, 'exists', lambda path: True)
        swap_extract = self.swap(
            check_backend_tests_to_run,
            'extract_imported_modules_from_ast',
            lambda path: set(),
        )

        with swap_output, swap_load, swap_diff, swap_exists, swap_extract:
            check_backend_tests_to_run.main(
                args=[
                    '--github_head_ref',
                    'HEAD',
                    '--github_base_ref',
                    'develop',
                ]
            )

        self.assertEqual(output_vars['RUN_ALL_TESTS'], 'false')
        self.assertEqual(output_vars['NUM_TESTS'], '1')
        self.assertEqual(
            output_vars['TEST_TARGETS'], 'core.controllers.profile_test'
        )
        self.assertEqual(
            output_vars['CHANGED_BACKEND_FILES'], 'core/controllers/profile.py'
        )
        self.assertEqual(output_vars['SHARDS_TO_RUN'], '[1]')
