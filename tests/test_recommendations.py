from datetime import timedelta

from app.config import Settings
from app.database import SessionLocal
from app.models import BehaviorEvent, Recommendation, User, utcnow
from app.recommendations import should_generate


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
