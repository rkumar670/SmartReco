import json

from langsmith.wrappers import wrap_openai
from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from app.config import Settings
from app.schemas import CareerPathPayload, RecommendationPayload


def parse_recommendation(content: str, products: list[dict]) -> RecommendationPayload:
    try:
        return RecommendationPayload.model_validate_json(content)
    except ValidationError:
        data = json.loads(content)
        candidates = data.get("candidates")
        if not isinstance(candidates, list):
            raise

        products_by_id = {product["id"]: product for product in products}
        products_by_title = {product["title"].strip().lower(): product for product in products}
        items = []
        for candidate in candidates[:5]:
            if not isinstance(candidate, dict):
                continue
            product = products_by_id.get(candidate.get("product_id") or candidate.get("id"))
            if not product and isinstance(candidate.get("title"), str):
                product = products_by_title.get(candidate["title"].strip().lower())
            if not product:
                continue
            reason = candidate.get("reason") or candidate.get("rationale") or candidate.get("description")
            items.append({"product_id": product["id"], "reason": reason or "Selected for your interests"})
        if not items:
            raise
        return RecommendationPayload(
            title=str(data.get("title") or "Courses selected for you"),
            narrative=str(data.get("narrative") or data.get("summary") or "These courses align with your recent learning interests."),
            items=items,
        )


class MeshClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = wrap_openai(OpenAI(base_url=settings.mesh_base_url, api_key=settings.mesh_api_key or "missing"))

    def require_key(self) -> None:
        if not self.settings.mesh_api_key:
            raise RuntimeError("MESH_API_KEY is required for AI operations")

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.require_key()
        try:
            response = self.client.embeddings.create(model=self.settings.mesh_embedding_model, input=texts)
        except OpenAIError as error:
            raise RuntimeError(f"Mesh embedding failed: {error}") from error
        return [item.embedding for item in response.data]

    def recommend(self, profile: str, products: list[dict]) -> RecommendationPayload:
        self.require_key()
        try:
            response = self.client.chat.completions.create(
                model=self.settings.mesh_chat_model,
                temperature=0.4,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Grade and rerank the provided catalog candidates for the behavioral profile. Return exactly one JSON object with the top-level keys title, narrative, and items. Do not return a candidates key. Items must contain product_id and reason and may contain at most five entries. Never invent an ID or product claim."},
                    {"role": "user", "content": f"Behavioral profile:\n{profile}\n\nCatalog candidates:\n{json.dumps(products, ensure_ascii=False)}"},
                ],
            )
        except OpenAIError as error:
            raise RuntimeError(f"Mesh recommendation failed: {error}") from error
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Mesh returned an empty recommendation")
        return parse_recommendation(content, products)

    def career_plan(self, profile: dict, products: list[dict]) -> CareerPathPayload:
        self.require_key()
        try:
            response = self.client.chat.completions.create(
                model=self.settings.mesh_chat_model,
                temperature=0.35,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "You are Cody, a practical career coach. Build a realistic progressive career timeline from the learner's current state to their target role. Return JSON with title, summary, target_role, estimated_months, hero_message, and 3-8 stages. Every stage needs phase, duration, goal, skills, course_ids, project, certifications, and interview_prep. Use only course IDs from the supplied catalogue; never invent courses, certifications, experience, or guarantees. Include foundations, applied projects, credible optional certifications, portfolio work, and role-specific interview preparation.",
                    },
                    {
                        "role": "user",
                        "content": f"Learner profile:\n{json.dumps(profile, ensure_ascii=False)}\n\nVerified catalogue:\n{json.dumps(products, ensure_ascii=False)}",
                    },
                ],
            )
        except OpenAIError as error:
            raise RuntimeError(f"Mesh career plan failed: {error}") from error
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Mesh returned an empty career plan")
        return CareerPathPayload.model_validate_json(content)
