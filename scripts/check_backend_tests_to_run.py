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

"""Checks and outputs which backend tests and shards to run in CI."""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
from typing import Dict, Final, List, Optional, Sequence, Set, Tuple

_PARSER: Final = argparse.ArgumentParser(
    description="""
Checks and outputs which backend tests to run in the CI.
"""
)

_PARSER.add_argument(
    '--github_head_ref',
    type=str,
    required=True,
    help='Head ref or commit SHA for diff check.',
)

_PARSER.add_argument(
    '--github_base_ref',
    type=str,
    required=True,
    help='Base ref or commit SHA for diff check.',
)

_PARSER.add_argument(
    '--output_all_test_suites',
    action='store_true',
    help='Force outputting all backend test suites and shards.',
)

SHARDS_SPEC_PATH: Final = os.path.join(
    os.getcwd(), 'scripts', 'backend_test_shards.json'
)

# Threshold for number of affected tests above which running all 5 shards in
# parallel is faster than running tests sequentially on a single runner.
MAX_TESTS_BEFORE_FULL_RUN: Final = 30

# Files whose modification requires running all backend test shards.
RUN_ALL_TESTS_FILES: Final[Tuple[str, ...]] = (
    'requirements.txt',
    'requirements_dev.txt',
    'dependencies.json',
    'scripts/run_backend_tests.py',
    'scripts/backend_test_shards.json',
    'scripts/check_backend_tests_to_run.py',
    'core/tests/gae_suite.py',
    'core/tests/test_utils.py',
    'core/constants.py',
    'core/feconf.py',
    '.github/workflows/backend_unit_tests.yml',
)

# Directories whose modification requires running all backend test shards.
RUN_ALL_TESTS_DIRECTORIES: Final[Tuple[str, ...]] = (
    'core/storage/',
    'core/platform/',
)


def get_git_diff_name_status_files(left: str, right: str) -> List[str]:
    """Returns the list of files modified between two commits.

    Args:
        left: str. The left commit or base ref.
        right: str. The right commit or head ref.

    Returns:
        list(str). The list of filepaths modified.

    Raises:
        ValueError. If there is an error with the git command.
    """
    git_cmd = ['git', 'diff', '--name-status', left, right, '--']

    task = subprocess.Popen(
        git_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    out, err = task.communicate()
    if not err:
        file_list: List[str] = []
        for line in out.splitlines():
            tokens = line.decode('utf-8').split('\t')
            if len(tokens) >= 2:
                file_list.append(tokens[-1].strip())
        return file_list
    else:
        raise ValueError(err.decode('utf-8'))


def is_global_backend_file(file_path: str) -> bool:
    """Returns whether modifying the given file requires running all tests.

    Args:
        file_path: str. The path of the modified file.

    Returns:
        bool. True if modifying this file triggers all backend tests.
    """
    if file_path in RUN_ALL_TESTS_FILES:
        return True
    for directory in RUN_ALL_TESTS_DIRECTORIES:
        if file_path.startswith(directory):
            return True
    return False


def load_backend_test_shards() -> Dict[str, List[str]]:
    """Loads backend test shards from backend_test_shards.json.

    Returns:
        dict(str, list(str)). Maps shard names to lists of dotted test modules.
    """
    with open(SHARDS_SPEC_PATH, 'r', encoding='utf-8') as f:
        shards: Dict[str, List[str]] = json.load(f)
        return shards


def extract_imported_modules_from_ast(file_path: str) -> Set[str]:
    """Extracts all imported module names from a Python source file.

    Args:
        file_path: str. Path to the Python file.

    Returns:
        set(str). Set of module names imported by the file.
    """
    if not os.path.exists(file_path):
        return set()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=file_path)
    except Exception:
        return set()

    imported: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
                for alias in node.names:
                    imported.add(f'{node.module}.{alias.name}')
    return imported


def get_associated_test_module_from_file(file_path: str) -> Optional[str]:
    """Gets the dotted test module corresponding to a Python file.

    Args:
        file_path: str. Path to the file.

    Returns:
        str | None. The dotted test module name, or None if no test exists.
    """
    if not file_path.endswith('.py'):
        return None

    if file_path.endswith('_test.py'):
        if os.path.exists(file_path):
            return file_path[:-3].replace('/', '.')
        return None

    test_path = file_path[:-3] + '_test.py'
    if os.path.exists(test_path):
        return test_path[:-3].replace('/', '.')

    return None


def get_affected_backend_test_modules(
    changed_files: Sequence[str],
    shards_spec: Optional[Dict[str, List[str]]] = None,
) -> Tuple[bool, List[str], List[str]]:
    """Calculates affected backend test modules from changed files.

    Args:
        changed_files: sequence(str). List of changed files.
        shards_spec: dict | None. Shards mapping (loaded from disk if None).

    Returns:
        tuple(bool, list(str), list(str)). A tuple of:
        - run_all_tests: bool. True if all backend tests should run.
        - test_targets: list(str). List of dotted test modules to run.
        - changed_backend_files: list(str). List of changed backend files.
    """
    if shards_spec is None:
        shards_spec = load_backend_test_shards()

    all_test_modules: List[str] = sorted(
        [module for shard_list in shards_spec.values() for module in shard_list]
    )
    all_test_modules_set: Set[str] = set(all_test_modules)

    # Check for global backend file changes.
    for changed_file in changed_files:
        if is_global_backend_file(changed_file):
            return (
                True,
                all_test_modules,
                [f for f in changed_files if f.endswith('.py')],
            )

    # Collect existing Python files modified.
    changed_backend_files = [
        f for f in changed_files if f.endswith('.py') and os.path.exists(f)
    ]

    # If no backend Python files were modified, no backend tests need to run.
    if not changed_backend_files:
        return False, [], []

    affected_test_targets: Set[str] = set()
    changed_modules: Set[str] = set()

    for file_path in changed_backend_files:
        module_name = file_path[:-3].replace('/', '.')
        changed_modules.add(module_name)

        associated_test = get_associated_test_module_from_file(file_path)
        if associated_test and associated_test in all_test_modules_set:
            affected_test_targets.add(associated_test)

    # Build reverse dependency mapping from test files to their imports.
    test_file_to_imports: Dict[str, Set[str]] = {}
    for test_module in all_test_modules:
        test_path = test_module.replace('.', '/') + '.py'
        test_file_to_imports[test_module] = extract_imported_modules_from_ast(
            test_path
        )

    # Find test files that import any of the changed modules.
    for test_module, imported_modules in test_file_to_imports.items():
        if test_module in affected_test_targets:
            continue
        for changed_module in changed_modules:
            if changed_module in imported_modules:
                affected_test_targets.add(test_module)
                break

    # If the number of affected tests exceeds threshold, fall back to all tests.
    if len(affected_test_targets) > MAX_TESTS_BEFORE_FULL_RUN:
        return True, all_test_modules, changed_backend_files

    return (
        False,
        sorted(affected_test_targets),
        sorted(changed_backend_files),
    )


def output_variable_to_github_workflow(
    output_variable: str, output_value: str
) -> None:
    """Outputs a variable to the GitHub workflow.

    Args:
        output_variable: str. The name of the output variable.
        output_value: str. The value of the output variable.
    """
    if 'GITHUB_OUTPUT' not in os.environ:
        print(f'{output_variable}={output_value}')
        return

    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as f:
        print(f'{output_variable}={output_value}', file=f)


def main(args: Optional[List[str]] = None) -> None:
    """Checks and outputs the backend test suites to run in the CI."""
    parsed_args = _PARSER.parse_args(args)

    shards_spec = load_backend_test_shards()
    all_test_modules = sorted(
        [module for shard_list in shards_spec.values() for module in shard_list]
    )

    if parsed_args.output_all_test_suites:
        print('Outputting all backend test suites.')
        output_variable_to_github_workflow('RUN_ALL_TESTS', 'true')
        output_variable_to_github_workflow(
            'NUM_TESTS', str(len(all_test_modules))
        )
        output_variable_to_github_workflow(
            'TEST_TARGETS', ','.join(all_test_modules)
        )
        output_variable_to_github_workflow('CHANGED_BACKEND_FILES', '')
        output_variable_to_github_workflow('SHARDS_TO_RUN', '[1, 2, 3, 4, 5]')
        return

    changed_files = get_git_diff_name_status_files(
        parsed_args.github_base_ref, parsed_args.github_head_ref
    )
    print(f'Changed files ({len(changed_files)}): {changed_files}')

    run_all_tests, test_targets, changed_backend_files = (
        get_affected_backend_test_modules(changed_files, shards_spec)
    )

    # Determine which shards contain the affected test targets.
    affected_shards: Set[int] = set()
    for shard_name, modules in shards_spec.items():
        if run_all_tests or any(m in test_targets for m in modules):
            affected_shards.add(int(shard_name))

    print(f'Run all backend tests: {run_all_tests}')
    print(f'Total affected backend tests: {len(test_targets)}')
    print(f'Affected test targets: {test_targets}')
    print(f'Affected shards: {sorted(affected_shards)}')
    print(f'Changed backend files: {changed_backend_files}')

    output_variable_to_github_workflow(
        'RUN_ALL_TESTS', 'true' if run_all_tests else 'false'
    )
    output_variable_to_github_workflow('NUM_TESTS', str(len(test_targets)))
    output_variable_to_github_workflow('TEST_TARGETS', ','.join(test_targets))
    output_variable_to_github_workflow(
        'CHANGED_BACKEND_FILES', ','.join(changed_backend_files)
    )
    output_variable_to_github_workflow(
        'SHARDS_TO_RUN', json.dumps(sorted(affected_shards))
    )


if __name__ == '__main__':  # pragma: no cover
    main()
