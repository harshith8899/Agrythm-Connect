import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _drop_postgres_test_schemas():
    """With GATE0_TEST_DATABASE_URL set, every test runs on Postgres in its own schema; remove them all at the end."""
    yield
    if os.environ.get("GATE0_TEST_DATABASE_URL"):
        from weathercall import db
        db.drop_test_schemas()
