import hashlib
import math
import re
from collections import Counter
from datetime import timedelta

import logfire
from langgraph.graph import END, START, StateGraph
from langsmith import traceable
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.mesh import MeshClient
from app.models import AgentRun, BehaviorEvent, Enrollment, Product, Recommendation, RecommendationItem, User, UserProfile, utcnow
from app.vectors import ProductVectors

EVENT_WEIGHTS = {"product_view": 1, "product_click": 2, "search": 3, "category_view": 1, "time_spent": 1, "recommendation_impression": 0, "recommendation_click": 3}


def unprocessed_events(db: Session, user_id: int) -> list[BehaviorEvent]:
    return list(db.scalars(select(BehaviorEvent).where(BehaviorEvent.user_id == user_id, BehaviorEvent.processed_at.is_(None)).order_by(BehaviorEvent.occurred_at)))


def signature(events: list[BehaviorEvent]) -> str:
    # Include client id and timestamp so a new event with the same payload still\n    # produces a new behavior version.\n    rows = [(event.event_id, event.event_type, event.product_id, event.search_query, event.category, event.occurred_at.isoformat() if event.occurred_at else "") for event in events]
    return hashlib.sha256(repr(rows).encode()).hexdigest()[:16] if rows else "cold-start"


def scored_event_weights(events: list[BehaviorEvent]) -> dict[int, float]:
    scores = {}
    last_click = {}
    for event in sorted(events, key=lambda item: item.occurred_at):
        weight = EVENT_WEIGHTS[event.event_type]
        if event.event_type == "product_click" and event.product_id:
            previous = last_click.get(event.product_id)
            if previous and event.occurred_at - previous < timedelta(minutes=5):
                weight = 0
            else:
                last_click[event.product_id] = event.occurred_at
        scores[event.id] = weight
    return scores


def should_generate(db: Session, user_id: int, settings: Settings) -> bool:
    events = unprocessed_events(db, user_id)
    latest = db.scalar(select(Recommendation).where(Recommendation.user_id == user_id).order_by(Recommendation.created_at.desc()))
    if latest:
        created_at = latest.created_at
        cutoff = utcnow() - timedelta(seconds=settings.recommendation_cooldown_seconds)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=cutoff.tzinfo)
        if created_at > cutoff:
            return False
    if not latest:
        return True
    return sum(scored_event_weights(events).values()) >= settings.recommendation_event_threshold


def refresh_profile(db: Session, user_id: int, behavior_signature: str) -> UserProfile:
    events = list(db.scalars(select(BehaviorEvent).where(BehaviorEvent.user_id == user_id).order_by(BehaviorEvent.occurred_at.desc()).limit(500)))
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_({e.product_id for e in events if e.product_id})))}
    weights: Counter[str] = Counter()
    now = utcnow()
    event_weights = scored_event_weights(events)
    for event in events:
        occurred = event.occurred_at if event.occurred_at.tzinfo else event.occurred_at.replace(tzinfo=now.tzinfo)
        decay = math.pow(0.5, max(0, (now - occurred).total_seconds()) / (7 * 86400))
        weight = event_weights[event.id] * decay
        signals = [event.search_query, event.category]
        product = products.get(event.product_id)
        if product:
            signals += [product.title, product.track, product.category, *(product.tags or [])]
        for signal in filter(None, signals):
            weights[str(signal).lower()] += weight
    top = dict(weights.most_common(20))
    summary = "; ".join(top) or "General course exploration"
    profile = db.get(UserProfile, user_id) or UserProfile(user_id=user_id)
    profile.summary, profile.interest_weights, profile.behavior_signature = summary, top, behavior_signature
    db.add(profile)
    db.flush()
    return profile


def filter_enrolled_products(products: list[Product], enrolled_ids: set[int]) -> list[Product]:\n    return [product for product in products if product.id not in enrolled_ids]\n\n\ndef lexical_rank(query: str, products: list[Product], limit: int = 15):
    terms = re.findall(r"[a-z0-9]+", query.lower())
    scored = []
    for product in products:
        text = f"{product.title} {product.track} {product.category} {' '.join(product.tags or [])} {product.syllabus} {product.description}".lower()
        score = sum((text.count(term) / (1 + math.log(1 + len(text)))) for term in terms)
        if score:
            scored.append((score, product.rating, product.id))
    return [product_id for _, _, product_id in sorted(scored, reverse=True)[:limit]]


def rrf(*rankings: list[int]) -> list[int]:
    scores: Counter[int] = Counter()
    for ranking in rankings:
        for rank, product_id in enumerate(ranking, 1):
            scores[product_id] += 1 / (60 + rank)
    return [product_id for product_id, _ in scores.most_common()]


def diversify(ids: list[int], products: dict[int, Product], limit: int = 8) -> list[int]:
    selected = []
    while ids and len(selected) < limit:
        best = max(ids, key=lambda pid: 1 / (1 + ids.index(pid)) - 0.6 * sum(products[pid].track == products[sid].track for sid in selected))
        selected.append(best)
        ids.remove(best)
    return selected


@traceable(name="smartreco_recommendation", run_type="chain")
def generate_recommendation(db: Session, user: User, settings: Settings, mesh: MeshClient, vectors: ProductVectors) -> Recommendation:
    events = unprocessed_events(db, user.id)
    behavior_signature = signature(events)
    latest = db.scalar(select(Recommendation).where(Recommendation.user_id == user.id).order_by(Recommendation.created_at.desc()))
    if latest and latest.behavior_version == behavior_signature:
        for event in events:
            event.processed_at = utcnow()
        db.commit()
        return latest

    path = "cold_start" if not events or sum(scored_event_weights(events).values()) == 0 else "personalized"
    run = AgentRun(user_id=user.id, behavior_signature=behavior_signature, path=path)
    db.add(run)
    db.commit()

    def prepare(_state: dict) -> dict:
        profile = refresh_profile(db, user.id, behavior_signature)
        products = list(db.scalars(select(Product).where(Product.is_active.is_(True))))
        enrolled_ids = set(db.scalars(select(Enrollment.product_id).where(Enrollment.user_id == user.id)))
        products = filter_enrolled_products(products, enrolled_ids)
        if not products:
            raise ValueError("No eligible products remain for this learner")
        if path == "cold_start":
            ids = [p.id for p in sorted(products, key=lambda p: (p.rating, -p.price, -p.id), reverse=True)[:8]]
        else:
            tracks = {product.track for product in products if product.track}
            preferred_track = next((term for term in profile.interest_weights if term in tracks), None)
            eligible_ids = {p.id for p in products}
            vector_ids = [product_id for product_id in vectors.search(profile.summary, limit=15, track=preferred_track) if product_id in eligible_ids]
            ids = diversify(rrf(vector_ids, lexical_rank(profile.summary, products)), {p.id: p for p in products})
        by_id = {p.id: p for p in products}
        candidates = [by_id[pid] for pid in ids if pid in by_id]
        return {"profile": profile.summary, "products": candidates}

    def grade(state: dict) -> dict:
        candidates = [{"id": p.id, "title": p.title, "description": p.description, "category": p.category, "track": p.track, "level": p.level, "rating": p.rating, "price": p.price} for p in state["products"]]
        if not candidates:
            raise ValueError("Retrieval returned no published products")
        payload = mesh.recommend(state["profile"], candidates)
        valid_ids = {p["id"] for p in candidates}
        items = [item for item in payload.items if item.get("product_id") in valid_ids]
        if not items:
            raise ValueError("Mesh returned no valid catalog product IDs")
        return {"profile": state["profile"], "title": payload.title, "narrative": payload.narrative, "items": items}

    builder = StateGraph(dict)
    builder.add_node("retrieve_and_diversify", prepare)
    builder.add_node("llm_grade_and_copy", grade)
    builder.add_edge(START, "retrieve_and_diversify")
    builder.add_edge("retrieve_and_diversify", "llm_grade_and_copy")
    builder.add_edge("llm_grade_and_copy", END)
    try:
        result = builder.compile().invoke({})
        recommendation = Recommendation(user_id=user.id, title=result["title"], narrative=result["narrative"], profile_summary=result["profile"], behavior_version=behavior_signature)
        db.add(recommendation)
        db.flush()
        for rank, item in enumerate(result["items"], 1):
            db.add(RecommendationItem(recommendation_id=recommendation.id, product_id=item["product_id"], reason=str(item.get("reason", "Selected for your interests")), rank=rank))
        processed_at = utcnow()
        for event in events:
            event.processed_at = processed_at
        run.recommendation_id, run.status, run.completed_at = recommendation.id, "completed", processed_at
        run.details = {"candidate_count": len(result["items"]), "profile": result["profile"]}
        db.commit()
        db.refresh(recommendation)
        logfire.info("recommendation generated", user_id=user.id, recommendation_id=recommendation.id, path=path)
        return recommendation
    except (RuntimeError, ValueError) as error:
        run.status, run.error, run.completed_at = "failed", str(error), utcnow()
        db.commit()
        raise
