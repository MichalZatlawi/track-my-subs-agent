"""Unit tests for State Schema, Session Isolation, Persistent Memory, and Context Builder."""

from src.state import (
    AgentState,
    PersistentMemoryStore,
    SessionStore,
    SubscriptionRecord,
    apply_event,
    build_context,
    run_context_comparison,
)


def test_two_conversations_never_mix():
    """Milestone 1 Requirement 4: Prove two separate conversations do not mix state."""
    sessions = SessionStore()
    s_ofri = sessions.create_thread("thread_ofri_1", user_id="user_ofri")
    s_michal = sessions.create_thread("thread_michal_1", user_id="user_michal")

    s_ofri = apply_event(s_ofri, "user", "אני רוצה לבדוק חלופות ל-Netflix")
    s_ofri = apply_event(s_ofri, "assistant", "בודק חלופות ל-Netflix עבורך.")
    sessions.save_thread(s_ofri)

    s_michal = apply_event(s_michal, "user", "אני רוצה לבדוק חלופות לחדר הכושר")
    sessions.save_thread(s_michal)

    loaded_ofri = sessions.get_thread("thread_ofri_1", user_id="user_ofri")
    loaded_michal = sessions.get_thread("thread_michal_1", user_id="user_michal")

    assert len(loaded_ofri.messages) == 2
    assert len(loaded_michal.messages) == 1
    assert "Netflix" in loaded_ofri.messages[0].content
    assert "Netflix" not in loaded_michal.messages[0].content
    assert loaded_ofri.step == 1
    assert loaded_michal.step == 0


def test_cross_user_thread_access_denied():
    sessions = SessionStore()
    sessions.create_thread("thread_private", user_id="user_ofri")
    try:
        sessions.get_thread("thread_private", user_id="user_michal")
        assert False, "Expected PermissionError for cross-user thread access"
    except PermissionError:
        pass


def test_persistent_memory_isolated_by_user_id():
    mem = PersistentMemoryStore()
    mem.upsert_subscription(
        "user_ofri",
        SubscriptionRecord(
            subscription_id="sub_netflix",
            service_name="Netflix",
            amount=69.90,
            category="streaming",
        ),
    )
    mem.add_preference("user_ofri", "מעדיפה חלופות ללא התחייבות")

    assert len(mem.get_subscriptions("user_ofri")) == 1
    assert len(mem.get_subscriptions("user_michal")) == 0
    assert mem.get_preferences("user_michal") == []


def test_sensitive_financial_data_rejected():
    mem = PersistentMemoryStore()
    try:
        mem.add_preference("user_ofri", "כרטיס האשראי שלי הוא 4580-1234-5678-9012")
        assert False, "Expected ValueError when storing credit card number"
    except ValueError:
        pass


def test_immutable_state_and_step_budget():
    s0 = AgentState(thread_id="t1", user_id="u1", max_steps=2)
    s1 = apply_event(s0, "assistant", "step 1")
    assert s0.step == 0  # Original state untouched
    assert s1.step == 1
    s2 = apply_event(s1, "assistant", "step 2")
    assert s2.step == 2
    try:
        apply_event(s2, "assistant", "step 3")
        assert False, "Expected RuntimeError when step budget is exhausted"
    except RuntimeError:
        pass


def test_context_comparison_full_vs_reduced():
    results = run_context_comparison()
    by_id = {r["strategy_id"]: r for r in results}

    assert by_id["full"]["required_info_present"] is True
    assert by_id["last_n"]["required_info_present"] is False
    assert by_id["notes"]["required_info_present"] is True
    assert by_id["notes"]["estimated_tokens"] < by_id["full"]["estimated_tokens"]
