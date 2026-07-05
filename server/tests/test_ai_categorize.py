import uuid

from app.services.ai.categorize import suggest_category
from app.services.ai.llm_client import FakeLlmClient

GROCERIES_ID = uuid.uuid4()
DINING_ID = uuid.uuid4()
CATEGORIES = {"Groceries": GROCERIES_ID, "Dining": DINING_ID}


async def test_valid_suggestion_in_vocabulary_is_accepted():
    client = FakeLlmClient('{"category_name": "Groceries", "reasoning": "grocery store"}')
    result = await suggest_category(
        client, merchant="Trader Joe's", amount_cents=-4500, kind="spend", categories=CATEGORIES
    )
    assert result == GROCERIES_ID


async def test_out_of_vocabulary_category_is_rejected():
    # The model invented a category that isn't in the caller's own list.
    client = FakeLlmClient('{"category_name": "Entertainment", "reasoning": "a guess"}')
    result = await suggest_category(
        client, merchant="Trader Joe's", amount_cents=-4500, kind="spend", categories=CATEGORIES
    )
    assert result is None


async def test_malformed_json_is_rejected_not_crashed():
    client = FakeLlmClient("not json at all")
    result = await suggest_category(
        client, merchant="Trader Joe's", amount_cents=-4500, kind="spend", categories=CATEGORIES
    )
    assert result is None


async def test_missing_required_field_is_rejected():
    client = FakeLlmClient('{"category_name": "Groceries"}')  # no "reasoning"
    result = await suggest_category(
        client, merchant="Trader Joe's", amount_cents=-4500, kind="spend", categories=CATEGORIES
    )
    assert result is None


async def test_no_categories_available_never_calls_the_model():
    client = FakeLlmClient('{"category_name": "Groceries", "reasoning": "x"}')
    result = await suggest_category(
        client, merchant="Trader Joe's", amount_cents=-4500, kind="spend", categories={}
    )
    assert result is None
    assert client.prompts_seen == []


async def test_prompt_never_contains_raw_email_only_transaction_facts():
    client = FakeLlmClient('{"category_name": "Groceries", "reasoning": "x"}')
    await suggest_category(
        client, merchant="Trader Joe's", amount_cents=-4500, kind="spend", categories=CATEGORIES
    )
    prompt = client.prompts_seen[0]
    assert "Trader Joe's" in prompt
    assert "45.00" in prompt
    assert "Groceries" in prompt and "Dining" in prompt
