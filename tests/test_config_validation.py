from __future__ import annotations

import pytest

from rag_pipeline.api.schemas.queries import QueryRequest
from rag_pipeline.core.config import Settings


def test_hosted_settings_reject_placeholder_access_keys(tmp_path):
    with pytest.raises(ValueError, match="DEMO_ACCESS_KEY"):
        Settings(
            APP_MODE="hosted",
            STORAGE_DIR=tmp_path / "data",
            DATABASE_URL=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}",
            DEMO_ACCESS_KEY="replace_with_a_real_key_12345678901234567890",
            ADMIN_API_KEY="admin-key-123456789012345678901234567890",
        )


def test_query_request_normalizes_question_and_pages():
    request = QueryRequest(question="  What is the total?  ", page_numbers=[3, 1, 3])

    assert request.question == "What is the total?"
    assert request.page_numbers == [1, 3]


def test_query_request_rejects_invalid_page_numbers():
    with pytest.raises(ValueError, match="positive"):
        QueryRequest(question="What is the total?", page_numbers=[0])
