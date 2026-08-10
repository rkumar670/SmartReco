from pathlib import Path

import chromadb

from app.config import Settings
from app.mesh import MeshClient
from app.models import CareerPlan, Enrollment, Product, User


class ProductVectors:
    def __init__(self, settings: Settings, mesh: MeshClient):
        Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=settings.chroma_path)
        self.collection = client.get_or_create_collection("products", metadata={"hnsw:space": "cosine"})
        self.learning_collection = client.get_or_create_collection("learning", metadata={"hnsw:space": "cosine"})
        self.career_collection = client.get_or_create_collection("career_paths", metadata={"hnsw:space": "cosine"})
        self.mesh = mesh

    @staticmethod
    def text(product: Product) -> str:
        tags = ", ".join(product.tags or [])
        return f"{product.title}\nProvider: {product.provider}\nTrack: {product.track}\nLevel: {product.level}\nCategory: {product.category}\nTags: {tags}\nSyllabus: {product.syllabus}\n{product.description}"

    def upsert(self, product: Product) -> None:
        document = self.text(product)
        embedding = self.mesh.embed([document])[0]
        self.collection.upsert(
            ids=[str(product.id)], embeddings=[embedding], documents=[document],
            metadatas=[{"product_id": product.id, "provider": product.provider, "track": product.track, "level": product.level, "category": product.category, "price": product.price, "currency": product.currency, "rating": product.rating, "is_active": product.is_active}],
        )

    def delete(self, product_id: int) -> None:
        self.collection.delete(ids=[str(product_id)])

    def upsert_enrollment(self, enrollment: Enrollment, user: User, product: Product) -> None:
        document = f"Learner {user.id} started {self.text(product)}"
        product_vector = self.collection.get(ids=[str(product.id)], include=["embeddings"])
        embedding = product_vector["embeddings"][0] if product_vector["ids"] else self.mesh.embed([document])[0]
        self.learning_collection.upsert(
            ids=[str(enrollment.id)],
            embeddings=[embedding],
            documents=[document],
            metadatas=[{
                "enrollment_id": enrollment.id,
                "user_id": user.id,
                "product_id": product.id,
                "status": enrollment.status,
                "progress": enrollment.progress,
                "track": product.track,
                "category": product.category,
            }],
        )

    def upsert_career_plan(self, plan: CareerPlan, user: User) -> None:
        document = f"Target role: {plan.target_role}\n{plan.summary}\nStages: {plan.stages}"
        embedding = self.mesh.embed([document])[0]
        self.career_collection.upsert(
            ids=[str(plan.id)],
            embeddings=[embedding],
            documents=[document],
            metadatas=[{"career_plan_id": plan.id, "user_id": user.id, "target_role": plan.target_role, "estimated_months": plan.estimated_months}],
        )

    def search(self, query: str, limit: int = 8, track: str | None = None) -> list[int]:
        embedding = self.mesh.embed([query])[0]
        where = {"$and": [{"is_active": True}, {"track": track}]} if track else {"is_active": True}
        result = self.collection.query(query_embeddings=[embedding], n_results=limit, where=where)
        return [int(product_id) for product_id in result["ids"][0]]
