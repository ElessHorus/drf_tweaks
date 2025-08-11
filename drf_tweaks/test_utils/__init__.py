from contextlib import contextmanager
from drf_tweaks.test_utils.lock_limiter import (
    query_lock_limiter,
    WouldSelectMultipleTablesForUpdate,
)  # noqa: F401
from drf_tweaks.test_utils.query_counter import (
    query_counter,
    TestQueryCounter,  # noqa: F401
    TooManySQLQueriesException,
)
from rest_framework.test import APIClient, APITestCase


class DatabaseAccessLintingAPIClient(APIClient):

    def __init__(self, with_lock_limiter=True, *args, **kwargs):
        self.with_lock_limiter = with_lock_limiter
        super().__init__(*args, **kwargs)

    def get(self, *args, **kwargs):
        with self.linters():
            return super().get(*args, **kwargs)

    def post(self, *args, **kwargs):
        with self.linters():
            return super().post(*args, **kwargs)

    def put(self, *args, **kwargs):
        with self.linters():
            return super().put(*args, **kwargs)

    def patch(self, *args, **kwargs):
        with self.linters():
            return super().patch(*args, **kwargs)

    @contextmanager
    def linters(self):
        if self.with_lock_limiter:
            with query_counter(), query_lock_limiter():
                yield
        else:
            with query_counter():
                yield


class DatabaseAccessLintingApiTestCase(APITestCase):
    client_class = DatabaseAccessLintingAPIClient


# The QueryCountingAPIClient is here for backwards compatibility;
# choose DatabaseAccessLintingAPIClient instead.
class QueryCountingAPIClient(DatabaseAccessLintingAPIClient):
    def __init__(self, *args, **kwargs):
        super().__init__(with_lock_limiter=False, *args, **kwargs)


class QueryCountingTestCaseMixin:
    client_class = QueryCountingAPIClient


class QueryCountingApiTestCase(QueryCountingTestCaseMixin, APITestCase):
    pass
