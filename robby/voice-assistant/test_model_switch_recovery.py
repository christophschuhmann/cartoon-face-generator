"""Exercise recovery without loading a model or accessing a GPU."""
import ast
import logging
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException


def switch_function(state, switch):
    source = Path(__file__).parent / 'tts-runtime/humaneness-small/small_app.py'
    module = ast.parse(source.read_text())
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'switch_acting_model')
    scope = {'STATE': state, '_switch_acting_model': switch, 'HTTPException': HTTPException,
             'log': logging.getLogger('test.model_switch')}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
    return scope['switch_acting_model']


def test_failed_large_load_restores_small_and_reports_it():
    state = {'phase': 'error'}
    switch = Mock(side_effect=[RuntimeError('load failed'), object()])
    with pytest.raises(HTTPException) as error:
        switch_function(state, switch)('large_17')
    assert error.value.status_code == 503
    assert 'Small RL was restored' in error.value.detail
    assert [call.args for call in switch.call_args_list] == [('large_17',), ('small_rl',)]


def test_rejection_before_loading_does_not_disturb_existing_model():
    state = {'phase': 'ready'}
    switch = Mock(side_effect=HTTPException(409, 'insufficient memory'))
    with pytest.raises(HTTPException) as error:
        switch_function(state, switch)('large_17')
    assert error.value.status_code == 409
    switch.assert_called_once_with('large_17')


def test_reports_failure_if_restoration_also_fails():
    state = {'phase': 'error'}
    switch = Mock(side_effect=[RuntimeError('load failed'), RuntimeError('restore failed')])
    with pytest.raises(HTTPException) as error:
        switch_function(state, switch)('large_17')
    assert error.value.status_code == 503
    assert 'could not be restored' in error.value.detail
    assert switch.call_count == 2
