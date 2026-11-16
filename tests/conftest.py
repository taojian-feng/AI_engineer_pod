import os
import tempfile

os.environ["LLM_PROVIDER"] = "fake"
os.environ["ACCESS_CODE"] = "test-code"
os.environ["SANDBOX"] = "local"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

import pytest  # noqa: E402

from app import llm, tracing  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    llm.fake_reset()
    tracing.current_session.set("test-session")
    yield
    llm.fake_reset()
