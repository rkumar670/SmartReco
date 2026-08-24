from datetime import timedelta

from app.config import Settings
from app.database import SessionLocal
from app.models import BehaviorEvent, Recommendation, User, utcnow
from app.recommendations import filter_enrolled_products, should_generate, signature


def test_trigger_uses_weighted_events():
    settings = Settings(recommendation_event_threshold=5)
    with SessionLocal() as db:
        user = User(email="trigger@example.com", password_hash="unused")
        db.add(user)
        db.flush()
        db.add_all(
            [
                BehaviorEvent(user_id=user.id, event_type="search", session_id="s1"),
                BehaviorEvent(user_id=user.id, event_type="product_click", session_id="s1"),
            ]
        )
        db.commit()
        assert should_generate(db, user.id, settings)


def test_trigger_respects_cooldown():
    settings = Settings(recommendation_event_threshold=1, recommendation_cooldown_seconds=30)
    with SessionLocal() as db:
        user = User(email="cooldown@example.com", password_hash="unused")
        db.add(user)
        db.flush()
        db.add(BehaviorEvent(user_id=user.id, event_type="search", session_id="s1"))
        db.add(
            Recommendation(
                user_id=user.id,
                title="Recent",
                narrative="Recent recommendation",
                profile_summary="AI",
                behavior_version="v1",
                created_at=utcnow() - timedelta(seconds=5),
            )
        )
        db.commit()
        assert not should_generate(db, user.id, settings)


def test_trigger_runs_after_thirty_second_cooldown():
    settings = Settings(recommendation_event_threshold=1, recommendation_cooldown_seconds=30)
    with SessionLocal() as db:
        user = User(email="expired-cooldown@example.com", password_hash="unused")
        db.add(user)
        db.flush()
        db.add(BehaviorEvent(user_id=user.id, event_type="search", session_id="s1"))
        db.add(
            Recommendation(
                user_id=user.id,
                title="Previous",
                narrative="Previous recommendation",
                profile_summary="AI",
                behavior_version="v1",
                created_at=utcnow() - timedelta(seconds=31),
            )
        )
        db.commit()
        assert should_generate(db, user.id, settings)


def test_signature_changes_for_same_payload_with_new_event_id():
    from app.models import BehaviorEvent

    first = BehaviorEvent(event_id="11111111-1111-1111-1111-111111111111", event_type="search", session_id="s1")
    second = BehaviorEvent(event_id="22222222-2222-2222-2222-222222222222", event_type="search", session_id="s1")
    assert signature([first]) != signature([second])


def test_enrolled_products_are_excluded():
    from app.models import Product

    products = [
        Product(id=1, title="Taken", description="Taken", category="data", price=0),
        Product(id=2, title="Available", description="Available", category="data", price=0),
    ]
    assert [product.id for product in filter_enrolled_products(products, {1})] == [2]
