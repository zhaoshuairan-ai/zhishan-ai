"""食安科普与辟谣助手（RAG）的接口与检索测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.models import AssistantEntry
from app.services import assistant_service


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    from app.services import assistant_service

    assistant_service._rate_buckets.clear()
    yield
    assistant_service._rate_buckets.clear()


SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from mock_llm_server import start_server  # noqa: E402

CONFIG_KEYS = (
    "ASSISTANT_MODE",
    "ASSISTANT_AI_FALLBACK",
    "ASSISTANT_GENERAL_ANSWER",
    "ASSISTANT_LLM_BASE_URL",
    "ASSISTANT_LLM_API_KEY",
    "ASSISTANT_LLM_MODEL",
    "ASSISTANT_LLM_TIMEOUT",
    "AI_API_KEY",
    "AI_BASE_URL",
    "AI_MODEL",
    "AI_TIMEOUT",
)


@pytest.fixture(autouse=True)
def restore_config(app):
    original = {key: app.config.get(key) for key in CONFIG_KEYS}
    yield
    for key, value in original.items():
        app.config[key] = value


@pytest.fixture()
def mock_llm():
    servers = []
    server = start_server(port=0, mode="clean")
    servers.append(server)
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}/v1"
    for item in servers:
        item.shutdown()
        item.server_close()


def test_seed_entries_are_loaded(app):
    with app.app_context():
        assert AssistantEntry.query.count() >= 40
        slugs = {entry.slug for entry in AssistantEntry.query.all()}
        assert {"leftover-food", "food-incompatibility", "msg-cancer"} <= slugs


def test_retrieval_matches_examples(app):
    with app.app_context():
        hits = assistant_service.search("隔夜菜到底能不能吃？")
        assert hits and hits[0]["entry"].slug == "leftover-food"
        assert hits[0]["matched"] is True

        hits = assistant_service.search("西瓜和桃子一起吃会中毒吗？")
        assert hits and hits[0]["entry"].slug == "food-incompatibility"

        hits = assistant_service.search("味精致癌吗")
        assert hits and hits[0]["entry"].slug == "msg-cancer"


def test_retrieval_refuses_unknown_question(app):
    with app.app_context():
        hits = assistant_service.search("量子水能养生吗")
        assert not hits or hits[0]["matched"] is False


def test_ask_returns_cited_answer(client, auth):
    resp = client.post("/api/assistant/ask", headers=auth, json={"question": "隔夜菜到底能不能吃？"})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["matched"] is True
    assert data["mode"] in {"retrieval", "ai"}
    assert data["sections"], "检索直答应给出结构化段落"
    assert data["sources"], "回答必须附带来源"
    assert all(source["name"] for source in data["sources"])
    assert data["session_id"] and data["message_id"]
    assert "不构成医疗诊断" in data["disclaimer"]


def test_ask_unknown_question_does_not_fabricate(client, auth):
    resp = client.post("/api/assistant/ask", headers=auth, json={"question": "量子水能养生吗"})
    data = resp.get_json()["data"]
    assert data["matched"] is False
    assert data["sources"] == []
    assert data["sections"] == []
    assert "没有收录" in data["answer"]
    assert data["related"], "未收录时应给出相关候选"


def test_ask_requires_login(client):
    resp = client.post("/api/assistant/ask", json={"question": "隔夜菜能吃吗"})
    assert resp.status_code == 401


def test_ask_rejects_too_short_question(client, auth):
    resp = client.post("/api/assistant/ask", headers=auth, json={"question": "?"})
    assert resp.status_code == 400


def test_session_history_and_delete(client, auth, other_auth):
    first = client.post("/api/assistant/ask", headers=auth, json={"question": "隔夜菜到底能不能吃？"}).get_json()["data"]
    session_id = first["session_id"]
    client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "味精致癌吗", "session_id": session_id},
    )
    sessions = client.get("/api/assistant/sessions", headers=auth).get_json()["data"]["items"]
    assert sessions and sessions[0]["id"] == session_id
    assert sessions[0]["message_count"] == 4

    detail = client.get(f"/api/assistant/sessions/{session_id}", headers=auth).get_json()["data"]["session"]
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant", "user", "assistant"]

    # 他人不可读、不可删
    assert client.get(f"/api/assistant/sessions/{session_id}", headers=other_auth).status_code == 404
    assert client.delete(f"/api/assistant/sessions/{session_id}", headers=other_auth).status_code == 404

    assert client.delete(f"/api/assistant/sessions/{session_id}", headers=auth).status_code == 200
    assert client.get(f"/api/assistant/sessions/{session_id}", headers=auth).status_code == 404


def test_overview_is_public(client):
    resp = client.get("/api/assistant/overview")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["stats"]["entries"] >= 40
    assert data["featured"]
    titles = [item["title"] for item in data["featured"]]
    assert not any("头孢" in title for title in titles)
    soy = next(item for item in data["featured"] if item["slug"] == "zero-additive")
    assert soy["title"] == "零添加的酱油真的更健康吗？"
    assert soy["category_label"] == "食品标签与营销话术"
    assert "disclaimer" in data


def test_ai_mode_grounds_and_drops_hallucinated_sentence(client, auth, app, mock_llm):
    app.config.update(
        ASSISTANT_MODE="ai",
        AI_API_KEY="mock-key",
        AI_BASE_URL=mock_llm,
        AI_MODEL="mock-model",
        AI_TIMEOUT=10,
    )
    data = client.post(
        "/api/assistant/ask", headers=auth, json={"question": "隔夜菜到底能不能吃？"}
    ).get_json()["data"]
    assert data["mode"] == "ai", data
    assert "冷藏保存" in data["answer"]
    # 模拟服务里那句“每天喝三杯咖啡能延寿十年”与资料无关，应被逐句校验丢弃
    assert "延寿" not in data["answer"]
    assert data["ai_check"]["dropped_sentences"] >= 1

    with app.app_context():
        from app.models import ChatMessage

        last = ChatMessage.query.filter_by(role="assistant").order_by(ChatMessage.id.desc()).first()
        assert last is not None and last.mode == "ai"


def test_retrieval_matches_alcohol_seafood(app):
    """补充条目后，口语化问法「酒和海鲜可以一起吃吗」应直接命中。"""
    with app.app_context():
        hits = assistant_service.search("酒和海鲜可以一起吃吗")
        assert hits and hits[0]["entry"].slug == "alcohol-seafood"
        assert hits[0]["matched"] is True


def test_ai_fallback_answers_from_related_entries(client, auth, app, mock_llm):
    """知识库未直接命中时，大模型只在相近条目里「选一条」，答案仍逐字来自条目原文。"""
    app.config.update(
        ASSISTANT_MODE="ai",
        ASSISTANT_AI_FALLBACK="1",
        AI_API_KEY="mock-key",
        AI_BASE_URL=mock_llm,
        AI_MODEL="mock-model",
        AI_TIMEOUT=10,
    )
    data = client.post(
        "/api/assistant/ask", headers=auth, json={"question": "路边烧烤的肉新鲜吗"}
    ).get_json()["data"]
    assert data["coverage"] == "related", data
    assert data["matched"] is True
    assert data["mode"] == "ai_rerank"
    assert data["sections"], "内容应来自条目原文的结构化段落"
    assert data["sources"], "相近条目作答也必须带来源"
    assert data["entry"]["slug"]
    assert data["mode_note"] and "选出" in data["mode_note"]


def test_ai_fallback_refuses_when_model_says_not_covered(client, auth, app):
    """模型判断相近条目也回答不了时，必须回到「未收录」，不能编造。"""
    server = start_server(port=0, mode="refuse")
    try:
        host, port = server.server_address[:2]
        app.config.update(
            ASSISTANT_MODE="ai",
            ASSISTANT_AI_FALLBACK="1",
            ASSISTANT_GENERAL_ANSWER="0",
            AI_API_KEY="mock-key",
            AI_BASE_URL=f"http://{host}:{port}/v1",
            AI_MODEL="mock-model",
            AI_TIMEOUT=10,
        )
        data = client.post(
            "/api/assistant/ask", headers=auth, json={"question": "路边烧烤的肉新鲜吗"}
        ).get_json()["data"]
        assert data["coverage"] == "none"
        assert data["matched"] is False
        assert data["sources"] == []
        assert "未收录" in data["answer"] or "没有收录" in data["answer"]
    finally:
        server.shutdown()
        server.server_close()


def test_food_incompatibility_general_matches(client, auth):
    """「海鲜和水果」这类同类问题由通用「食物相克」条目直接命中。"""
    data = client.post(
        "/api/assistant/ask", headers=auth, json={"question": "海鲜和水果一起吃会中毒吗"}
    ).get_json()["data"]
    assert data["coverage"] == "direct"
    assert data["entry"]["slug"] == "food-incompatibility-general"
    assert data["sources"]


def test_general_answer_when_kb_cannot_cover(client, auth, app):
    """知识库与相近条目都答不了时，允许通用大模型回答，并明确标注未引用本站资料。"""
    server = start_server(port=0, mode="none_rerank")
    try:
        host, port = server.server_address[:2]
        app.config.update(
            ASSISTANT_MODE="ai",
            ASSISTANT_AI_FALLBACK="1",
            ASSISTANT_GENERAL_ANSWER="1",
            AI_API_KEY="mock-key",
            AI_BASE_URL=f"http://{host}:{port}/v1",
            AI_MODEL="mock-model",
            AI_TIMEOUT=10,
        )
        data = client.post(
            "/api/assistant/ask", headers=auth, json={"question": "隔夜木耳还能吃吗"}
        ).get_json()["data"]
        assert data["coverage"] == "general", data
        assert data["mode"] == "ai_general"
        assert data["sources"] == []
        assert data["entry"] is None
        assert "咨询医生" in (data["mode_note"] or "")
        assert "未经" not in (data["mode_note"] or "")
        assert data["answer"]
    finally:
        server.shutdown()
        server.server_close()


def test_assistant_uses_dedicated_llm_config(client, auth, app, mock_llm):
    """科普助手可以单独配置大模型：AI_* 留空，只用 ASSISTANT_LLM_*。"""
    app.config.update(
        ASSISTANT_MODE="ai",
        ASSISTANT_AI_FALLBACK="1",
        ASSISTANT_GENERAL_ANSWER="1",
        ASSISTANT_LLM_BASE_URL=mock_llm,
        ASSISTANT_LLM_API_KEY="dedicated-key",
        ASSISTANT_LLM_MODEL="dedicated-model",
        ASSISTANT_LLM_TIMEOUT=10,
        AI_API_KEY="",
        AI_BASE_URL="http://127.0.0.1:9/v1",
        AI_MODEL="",
        AI_TIMEOUT=1,
    )
    data = client.post(
        "/api/assistant/ask", headers=auth, json={"question": "隔夜菜到底能不能吃？"}
    ).get_json()["data"]
    assert data["mode"] in {"ai", "ai_rerank", "ai_general"}
    assert data["answer"]


def test_ai_mode_falls_back_to_retrieval_on_error(client, auth, app):
    app.config.update(
        ASSISTANT_MODE="ai",
        AI_API_KEY="mock-key",
        AI_BASE_URL="http://127.0.0.1:9/v1",  # 不可达端口
        AI_MODEL="mock-model",
        AI_TIMEOUT=2,
    )
    data = client.post(
        "/api/assistant/ask", headers=auth, json={"question": "隔夜菜到底能不能吃？"}
    ).get_json()["data"]
    assert data["mode"] == "retrieval"
    assert data["mode_note"] and "检索直答" in data["mode_note"]
    assert data["sections"]


def test_follow_up_question_uses_previous_topic(client, auth):
    first = client.post("/api/assistant/ask", headers=auth, json={"question": "隔夜菜到底能不能吃？"}).get_json()["data"]
    session_id = first["session_id"]
    assert first["entry"] is not None
    follow = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "为什么？", "session_id": session_id},
    ).get_json()["data"]
    assert follow["session_id"] == session_id
    assert follow["context_used"] is True
    assert follow["matched"] is True
    assert follow["entry"]["slug"] == first["entry"]["slug"]
    assert "没有收录" not in follow["answer"]


def test_new_topic_in_same_session_is_not_dragged_to_old_context(client, auth):
    first = client.post("/api/assistant/ask", headers=auth, json={"question": "隔夜菜到底能不能吃？"}).get_json()["data"]
    session_id = first["session_id"]
    new_topic = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "阿斯巴甜安全吗", "session_id": session_id},
    ).get_json()["data"]
    assert new_topic["context_used"] is False
    assert new_topic["entry"] is not None
    assert new_topic["entry"]["slug"] != first["entry"]["slug"]

    follow = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "为什么？", "session_id": session_id},
    ).get_json()["data"]
    assert follow["context_used"] is True
    assert follow["entry"]["slug"] == new_topic["entry"]["slug"]


def test_cooking_question_returns_beginner_steps(client, auth):
    resp = client.post("/api/assistant/ask", headers=auth, json={"question": "番茄炒蛋怎么做？"})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["coverage"] == "recipe"
    assert data["mode"] == "recipe"
    assert data["entry"] is None
    assert data["sources"] == []
    labels = [item["label"] for item in data["sections"]]
    assert "食材与调料" in labels
    assert "新手分步做法" in labels
    steps = next(item["text"] for item in data["sections"] if item["label"] == "新手分步做法")
    assert steps.count("\n") >= 4
    assert any(word in steps for word in ("中火", "大火", "分钟"))
    assert "鸡蛋" in data["answer"] and "番茄" in data["answer"]


def test_cooking_follow_up_uses_previous_dish(client, auth):
    first = client.post("/api/assistant/ask", headers=auth, json={"question": "青椒土豆丝怎么做？"}).get_json()["data"]
    assert first["coverage"] == "recipe"
    session_id = first["session_id"]
    follow = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "那具体怎么做？", "session_id": session_id},
    ).get_json()["data"]
    assert follow["coverage"] == "recipe"
    assert follow["context_used"] is True
    assert "土豆" in follow["answer"]


def test_safety_question_with_cooking_words_stays_in_safety_mode(client, auth):
    data = client.post(
        "/api/assistant/ask", headers=auth, json={"question": "隔夜菜怎么做才安全？"}
    ).get_json()["data"]
    assert data["coverage"] != "recipe"


def test_cooking_ai_fallback_still_has_sections(client, auth, monkeypatch):
    from app.services import cooking_service

    monkeypatch.setattr(
        cooking_service,
        "_ai_recipe",
        lambda dish, history: (
            {
                "title": "宫保鸡丁",
                "intro": "2 人份，新手版。",
                "ingredients": ["鸡胸肉 300g", "花生米 50g", "生抽 10ml"],
                "steps": ["鸡胸肉切丁，加生抽腌 10 分钟。", "中火滑炒鸡丁至变白。", "下花生米翻匀出锅。"],
                "tips": ["花生米最后放，保持酥脆。"],
                "safety": ["鸡肉彻底炒熟，花生过敏者不要食用。"],
            },
            None,
        ),
    )
    data = client.post("/api/assistant/ask", headers=auth, json={"question": "宫保鸡丁怎么做？"}).get_json()["data"]
    assert data["coverage"] == "recipe"
    assert data["mode"] == "recipe_ai"
    assert any(item["label"] == "新手分步做法" for item in data["sections"])
    assert "鸡胸肉" in data["answer"]


def test_elliptical_follow_up_keeps_food_topic(client, auth):
    first = client.post("/api/assistant/ask", headers=auth, json={"question": "有什么蘑菇"}).get_json()["data"]
    follow = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "能和酒一起吃吗", "session_id": first["session_id"]},
    ).get_json()["data"]
    assert follow["context_used"] is True
    assert "蘑菇" in (follow.get("retrieval_query") or "")
    assert "头孢" not in follow["answer"]


def test_assistant_recommends_from_pantry_and_returns_plan(client, auth):
    for payload in [
        {"name": "菠菜", "category": "vegetable", "quantity": 1, "unit": "把"},
        {"name": "鸡胸肉", "category": "meat", "quantity": 1, "unit": "块"},
        {"name": "大米", "category": "staple", "quantity": 500, "unit": "g"},
    ]:
        assert client.post("/api/pantry", headers=auth, json=payload).status_code == 201
    data = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "想做一个清淡一点的菜，用我的食材推荐几道"},
    ).get_json()["data"]
    assert data["coverage"] == "pantry_recipe"
    assert data["mode"] == "pantry_agent"
    assert data["pantry_plan_id"]
    assert len(data["pantry_dishes"]) >= 2
    names = [item["name"] for dish in data["pantry_dishes"] for item in dish["ingredients"]]
    assert "菠菜" in names or "鸡胸肉" in names
    assert data["pantry_trace"]


def test_assistant_recommendation_parses_servings(client, auth):
    for payload in [
        {"name": "菠菜", "category": "vegetable", "quantity": 1, "unit": "把"},
        {"name": "鸡胸肉", "category": "meat", "quantity": 1, "unit": "块"},
        {"name": "大米", "category": "staple", "quantity": 500, "unit": "g"},
    ]:
        client.post("/api/pantry", headers=auth, json=payload)
    data = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "做3人份的清淡菜，用我的食材推荐"},
    ).get_json()["data"]
    assert data["coverage"] == "pantry_recipe"
    assert data["pantry_servings"] == 3


def test_cooking_ingredients_use_chinese_household_units(client, auth):
    data = client.post("/api/assistant/ask", headers=auth, json={"question": "番茄炒蛋怎么做"}).get_json()["data"]
    section = next(item for item in data["sections"] if item["label"] == "食材与调料")
    assert "小勺" in section["text"] or "汤勺" in section["text"]
    assert "茶匙" not in section["text"] and "汤匙" not in section["text"] and "盎司" not in section["text"]
    assert "番茄 2 个（约" in section["text"] and "400g" in section["text"]
    assert "（约 2.7" not in section["text"]


def test_inventory_question_returns_jump_action_and_uses_prompt(client, auth, monkeypatch):
    from app.services import assistant_service

    for payload in [
        {"name": "番茄", "category": "vegetable", "quantity": 3, "unit": "个"},
        {"name": "鸡蛋", "category": "egg_dairy", "quantity": 2, "unit": "个"},
        {"name": "牛奶", "category": "egg_dairy", "quantity": 1, "unit": "盒"},
    ]:
        client.post("/api/pantry", headers=auth, json=payload)
    captured = {}

    def fake_chat(messages):
        captured["system"] = messages[0]["content"]
        return '{"answer":"番茄炒蛋充分加热即可；牛奶未胀包、冷藏正常且充分加热后一般可以喝，胀包或异味则丢弃。","action":"jump_to_inventory","action_label":"管理我的冰箱库存","used_items":["番茄","鸡蛋","牛奶"],"safety_notes":["检查牛奶包装是否胀包"]}'

    monkeypatch.setattr(assistant_service, "_allow_ai", lambda: True)
    monkeypatch.setattr(assistant_service, "_chat", fake_chat)
    data = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "冰箱里有点番茄和鸡蛋，做个番茄炒蛋安全吗？我的牛奶快过期了还能喝吗？"},
    ).get_json()["data"]
    assert data["coverage"] == "inventory"
    assert data["action"] == "jump_to_inventory"
    assert data["action_label"] == "管理我的冰箱库存"
    assert {item["name"] for item in data["inventory_items"]} >= {"番茄", "鸡蛋", "牛奶"}
    assert "番茄" in captured["system"] and "鸡蛋" in captured["system"] and "牛奶" in captured["system"]
    assert "jump_to_inventory" in captured["system"]
    assert "番茄炒蛋" in data["answer"]


def test_inventory_fallback_still_returns_action(client, auth):
    for payload in [
        {"name": "番茄", "category": "vegetable", "quantity": 3, "unit": "个"},
        {"name": "鸡蛋", "category": "egg_dairy", "quantity": 2, "unit": "个"},
        {"name": "牛奶", "category": "egg_dairy", "quantity": 1, "unit": "盒"},
    ]:
        client.post("/api/pantry", headers=auth, json=payload)
    data = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "牛奶快过期了还能喝吗？"},
    ).get_json()["data"]
    assert data["coverage"] == "inventory"
    assert data["action"] == "jump_to_inventory"
    assert data["mode"] in {"inventory_ai", "inventory_rule"}
    assert data["answer"]


def test_cooking_answer_can_be_saved_to_recipe_plan(client, auth):
    for payload in [
        {"name": "番茄", "category": "vegetable", "quantity": 3, "unit": "个"},
        {"name": "鸡蛋", "category": "egg_dairy", "quantity": 3, "unit": "个"},
    ]:
        client.post("/api/pantry", headers=auth, json=payload)
    data = client.post("/api/assistant/ask", headers=auth, json={"question": "番茄炒蛋怎么做"}).get_json()["data"]
    assert data["recipe_title"]
    saved = client.post(
        "/api/recipes/from-assistant", headers=auth, json={"message_id": data["message_id"]}
    )
    assert saved.status_code == 201, saved.get_json()
    plan = saved.get_json()["data"]
    assert plan["plan_id"]
    assert plan["servings"] == 2
    assert plan["meals"][0]["name"] == "番茄炒蛋"
    assert any(item["name"] == "番茄" and item["from_pantry"] for item in plan["meals"][0]["ingredients"])
    history = client.get("/api/recipes/history", headers=auth).get_json()["data"]["items"]
    assert any(item["result"].get("plan_id") == plan["plan_id"] for item in history)


def test_second_saved_recipe_appends_to_same_plan(client, auth):
    for payload in [
        {"name": "番茄", "category": "vegetable", "quantity": 3, "unit": "个"},
        {"name": "鸡蛋", "category": "egg_dairy", "quantity": 3, "unit": "个"},
        {"name": "土豆", "category": "vegetable", "quantity": 2, "unit": "个"},
    ]:
        client.post("/api/pantry", headers=auth, json=payload)
    first = client.post("/api/assistant/ask", headers=auth, json={"question": "番茄炒蛋怎么做"}).get_json()["data"]
    one = client.post("/api/recipes/from-assistant", headers=auth, json={"message_id": first["message_id"]}).get_json()["data"]
    second = client.post("/api/assistant/ask", headers=auth, json={"question": "青椒土豆丝怎么做"}).get_json()["data"]
    two = client.post("/api/recipes/from-assistant", headers=auth, json={"message_id": second["message_id"]}).get_json()["data"]
    assert one["plan_id"] == two["plan_id"]
    assert {"番茄炒蛋", "青椒土豆丝"} <= {meal["name"] for meal in two["meals"]}


def test_recipe_recommendation_returns_options_then_summary(client, auth):
    first = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "我买了一条鲤鱼，有什么推荐的做法吗"},
    ).get_json()["data"]
    assert first["coverage"] == "recipe_options"
    assert first["mode"] == "recipe_options"
    assert len(first["recipe_options"]) >= 2
    assert all(option["title"] and option["time"] and option["safety"] for option in first["recipe_options"])
    assert first["sections"] == []

    chosen = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "我选红烧鲤鱼，请给出做法"},
    ).get_json()["data"]
    assert chosen["coverage"] == "recipe"
    assert chosen["recipe_summary"]["title"]
    assert chosen["recipe_summary"]["time"]
    assert chosen["recipe_summary"]["main_ingredients"]
    assert chosen["sections"]


def test_remove_single_meal_from_saved_recipe_plan(client, auth):
    for payload in [
        {"name": "番茄", "category": "vegetable", "quantity": 3, "unit": "个"},
        {"name": "鸡蛋", "category": "egg_dairy", "quantity": 3, "unit": "个"},
        {"name": "土豆", "category": "vegetable", "quantity": 2, "unit": "个"},
    ]:
        client.post("/api/pantry", headers=auth, json=payload)
    first = client.post("/api/assistant/ask", headers=auth, json={"question": "番茄炒蛋怎么做"}).get_json()["data"]
    saved = client.post("/api/recipes/from-assistant", headers=auth, json={"message_id": first["message_id"]}).get_json()["data"]
    second = client.post("/api/assistant/ask", headers=auth, json={"question": "青椒土豆丝怎么做"}).get_json()["data"]
    saved = client.post("/api/recipes/from-assistant", headers=auth, json={"message_id": second["message_id"]}).get_json()["data"]
    assert len(saved["meals"]) == 2
    removed = client.post(
        "/api/recipes/remove-meal",
        headers=auth,
        json={"plan_id": saved["plan_id"], "meal_index": 0},
    ).get_json()["data"]
    assert removed["deleted_plan"] is False
    assert len(removed["result"]["meals"]) == 1
    remaining = removed["result"]["meals"][0]["name"]
    last = client.post(
        "/api/recipes/remove-meal",
        headers=auth,
        json={"plan_id": saved["plan_id"], "meal_index": 0},
    ).get_json()["data"]
    assert last["deleted_plan"] is True
    history = client.get("/api/recipes/history", headers=auth).get_json()["data"]["items"]
    assert not any(item["id"] == saved["plan_id"] for item in history)
    assert remaining


def test_plain_dish_name_returns_dual_recipe_versions(client, auth):
    data = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "麻婆豆腐"},
    ).get_json()["data"]
    assert data["coverage"] == "recipe"
    versions = data["recipe_versions"]
    assert versions["novice"]["steps"]
    assert versions["chef"]["steps"]
    assert len(versions["chef"]["steps"]) >= len(versions["novice"]["steps"])
    assert data["recipe_summary"]["title"]
    assert data["sections"]


def test_saved_recipe_keeps_selected_chef_version(client, auth):
    data = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "麻婆豆腐"},
    ).get_json()["data"]
    chef_steps = data["recipe_versions"]["chef"]["steps"]
    saved = client.post(
        "/api/recipes/from-assistant",
        headers=auth,
        json={"message_id": data["message_id"], "version": "chef"},
    ).get_json()["data"]
    meal = saved["meals"][0]
    assert meal["version"] == "chef"
    assert meal["steps"] == chef_steps[:20]
    assert meal["versions"]["chef"]["steps"]

    novice_steps = data["recipe_versions"]["novice"]["steps"]
    updated = client.post(
        "/api/recipes/from-assistant",
        headers=auth,
        json={"message_id": data["message_id"], "version": "novice"},
    ).get_json()["data"]
    assert updated["plan_id"] == saved["plan_id"]
    assert updated["meals"][0]["version"] == "novice"
    assert updated["meals"][0]["steps"] == novice_steps[:20]


def test_knowledge_intent_stays_on_rag(client, auth):
    data = client.post(
        "/api/assistant/ask",
        headers=auth,
        json={"question": "西瓜和桃子一起吃会中毒吗"},
    ).get_json()["data"]
    assert data["mode"] in {"retrieval", "ai", "ai_rerank"}
    assert data["coverage"] in {"direct", "related"}
    assert data["sources"] or data["entry"]


def test_clear_all_assistant_sessions(client, auth):
    for question in ["麻婆豆腐", "番茄炒蛋怎么做"]:
        client.post("/api/assistant/ask", headers=auth, json={"question": question})
    before = client.get("/api/assistant/sessions", headers=auth).get_json()["data"]["items"]
    assert len(before) >= 2
    cleared = client.delete("/api/assistant/sessions", headers=auth).get_json()["data"]
    assert cleared["deleted"] >= 2
    after = client.get("/api/assistant/sessions", headers=auth).get_json()["data"]["items"]
    assert after == []


def test_recipe_quality_fallback_fills_steps_and_nutrition():
    from app.services.cooking_service import _ensure_recipe_quality

    recipe = {
        "title": "红烧肉",
        "ingredients": ["五花肉 300g", "生抽 15ml", "冰糖 10g", "生姜 3片"],
        "steps": ["把肉切块。", "下锅煮熟。"],
    }
    result = _ensure_recipe_quality(recipe)
    assert len(result["versions"]["novice"]["steps"]) >= 6
    nutrition = result["nutrition"]
    assert nutrition["protein_g"] > 0
    assert nutrition["fat_g"] > 0
    assert nutrition["sodium_mg"] > 0
