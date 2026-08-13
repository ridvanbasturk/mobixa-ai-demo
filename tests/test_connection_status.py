from services.bedrock_client import (
    CONNECTION_STATUS_ERROR,
    CONNECTION_STATUS_SUCCESS,
    CONNECTION_STATUS_UNTESTED,
    ModelCallResult,
    next_connection_status,
)


def test_successful_call_marks_success():
    result = ModelCallResult(model_id="m", api_call_success=True)
    assert next_connection_status(CONNECTION_STATUS_UNTESTED, result) == CONNECTION_STATUS_SUCCESS


def test_auth_error_marks_connection_error():
    result = ModelCallResult(model_id="m", api_call_success=False, error_category="auth")
    assert next_connection_status(CONNECTION_STATUS_SUCCESS, result) == CONNECTION_STATUS_ERROR


def test_connection_error_marks_connection_error():
    result = ModelCallResult(model_id="m", api_call_success=False, error_category="connection")
    assert next_connection_status(CONNECTION_STATUS_UNTESTED, result) == CONNECTION_STATUS_ERROR


def test_rate_limit_error_does_not_change_status():
    result = ModelCallResult(model_id="m", api_call_success=False, error_category="rate_limit")
    assert next_connection_status(CONNECTION_STATUS_SUCCESS, result) == CONNECTION_STATUS_SUCCESS
    assert next_connection_status(CONNECTION_STATUS_UNTESTED, result) == CONNECTION_STATUS_UNTESTED


def test_json_parse_failure_after_successful_api_call_still_marks_success():
    # api_call_success is set even if JSON parsing later fails (result.success == False)
    result = ModelCallResult(model_id="m", api_call_success=True, success=False, error="JSON ayrıştırılamadı")
    assert next_connection_status(CONNECTION_STATUS_UNTESTED, result) == CONNECTION_STATUS_SUCCESS
