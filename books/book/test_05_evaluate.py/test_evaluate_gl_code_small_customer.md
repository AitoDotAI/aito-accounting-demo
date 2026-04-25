# _evaluate: GL code accuracy (small customer)

Small customers have fewer invoices — accuracy may be lower.

  Customer: CUST-0063 (32 invoices)


test raised exception Aito returned 504 for POST /_evaluate: <!DOCTYPE html PUBLIC '-//W3C//DTD XHTML 1.0 Transitional//EN' 'http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd'>
<html xmlns='http://www.w3.org/1999/xhtml'>

<head>
    <meta content='text/html; charset=utf-8' http-equiv='content-type' />
    <style type='text/css'>
        body {
            font-family: Arial;
            margin-left: 40px;
        }

        img {
            border: 0 none;
        }

        #content {
            margin-left: auto;
            margin-right: auto
 :
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
  File "/home/arau/episto/src/aito-accounting-demo/book/test_05_evaluate.py", line 63, in test_evaluate_gl_code_small_customer
    result = c._request("POST", "/_evaluate", json={
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/arau/episto/src/aito-accounting-demo/src/aito_client.py", line 63, in _request
    raise AitoError(
src.aito_client.AitoError: Aito returned 504 for POST /_evaluate: <!DOCTYPE html PUBLIC '-//W3C//DTD XHTML 1.0 Transitional//EN' 'http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd'>
<html xmlns='http://www.w3.org/1999/xhtml'>

<head>
    <meta content='text/html; charset=utf-8' http-equiv='content-type' />
    <style type='text/css'>
        body {
            font-family: Arial;
            margin-left: 40px;
        }

        img {
            border: 0 none;
        }

        #content {
            margin-left: auto;
            margin-right: auto
 

