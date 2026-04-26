# prediction_log: write + read



test raised exception missing snapshot for request https://shared.aito.ai/db/aito-accounting-demo/api/v1/data/prediction_log - ab02137ae8723150b83c0550b84f81011a43bf58. try running booktest with '-s' flag to capture the missing snapshot:
Traceback (most recent call last):
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/booktest/core/testrun.py", line 105, in run_case
    rv = await maybe_async_call(case, [t], {})
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/booktest/utils/coroutines.py", line 11, in maybe_async_call
    return await func(*args2, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/booktest/snapshots/httpx.py", line 422, in wrapper
    return await maybe_async_call(func , args, kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/booktest/utils/coroutines.py", line 13, in maybe_async_call
    return func(*args2, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/book/test_06_template_and_log.py", line 105, in test_prediction_log_round_trip
    c._request("POST", "/data/prediction_log", json=payload)
  File "/home/arau/episto/src/aito-accounting-demo/src/aito_client.py", line 50, in _request
    response = httpx.request(
               ^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/httpx/_api.py", line 118, in request
    return client.request(
           ^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/httpx/_client.py", line 837, in request
    return self.send(request, auth=auth, follow_redirects=follow_redirects)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/httpx/_client.py", line 926, in send
    response = self._send_handling_auth(
               ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/httpx/_client.py", line 954, in _send_handling_auth
    response = self._send_handling_redirects(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/httpx/_client.py", line 991, in _send_handling_redirects
    response = self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/httpx/_client.py", line 1027, in _send_single_request
    response = transport.handle_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/booktest/snapshots/httpx.py", line 299, in mocked_handle_request
    return self.handle_request(transport, request)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/booktest/snapshots/httpx.py", line 273, in handle_request
    return self.snapshot_request(transport, request)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/booktest/snapshots/httpx.py", line 263, in snapshot_request
    key, rv = self.lookup_request_snapshot(request)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/.venv/lib/python3.12/site-packages/booktest/snapshots/httpx.py", line 257, in lookup_request_snapshot
    raise AssertionError(f"missing snapshot for request {request.url} - {key.hash}. "
AssertionError: missing snapshot for request https://shared.aito.ai/db/aito-accounting-demo/api/v1/data/prediction_log - ab02137ae8723150b83c0550b84f81011a43bf58. try running booktest with '-s' flag to capture the missing snapshot

