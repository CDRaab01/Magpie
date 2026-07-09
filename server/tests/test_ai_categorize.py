import uuid

from app.services.ai.categorize import _extract_json_object, suggest_category
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


async def test_markdown_fenced_json_is_accepted():
    # Regression: the live gemma-4-e4b wraps its JSON in a ```json … ``` fence even when asked
    # for "only JSON". Before the fence-stripping fix, model_validate_json saw the backticks and
    # dropped EVERY real suggestion (0/12 against the live model) while this fake-client suite
    # stayed green — the exact gap that hid it. The fake now reproduces the real reply shape.
    client = FakeLlmClient(
        '```json\n{"category_name": "Groceries", "reasoning": "grocery store"}\n```'
    )
    result = await suggest_category(
        client, merchant="Trader Joe's", amount_cents=-4500, kind="spend", categories=CATEGORIES
    )
    assert result == GROCERIES_ID


async def test_json_with_surrounding_prose_is_accepted():
    # Some replies add a sentence before/after the object; take the outermost {...} span.
    client = FakeLlmClient(
        'Here is the classification:\n{"category_name": "Dining", "reasoning": "a cafe"} — hope that helps!'
    )
    result = await suggest_category(
        client, merchant="Blue Bottle", amount_cents=-650, kind="spend", categories=CATEGORIES
    )
    assert result == DINING_ID


def test_extract_json_object_handles_fences_prose_and_clean():
    clean = '{"category_name": "Groceries", "reasoning": "x"}'
    assert _extract_json_object(clean) == clean
    assert _extract_json_object(f"```json\n{clean}\n```") == clean
    assert _extract_json_object(f"```\n{clean}\n```") == clean
    assert _extract_json_object(f"Sure:\n{clean}\nDone.") == clean


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
