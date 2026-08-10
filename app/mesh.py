import json

from langsmith.wrappers import wrap_openai
from openai import OpenAI, OpenAIError

from app.config import Settings
from app.schemas import CareerPathPayload, RecommendationPayload


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
                    {"role": "system", "content": "Grade and rerank the provided catalog candidates for the behavioral profile. Return concise grounded JSON with title, narrative, and up to five items. Each item must contain product_id and reason. Never invent an ID or product claim."},
                    {"role": "user", "content": f"Behavioral profile:\n{profile}\n\nCatalog candidates:\n{json.dumps(products, ensure_ascii=False)}"},
                ],
            )
        except OpenAIError as error:
            raise RuntimeError(f"Mesh recommendation failed: {error}") from error
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Mesh returned an empty recommendation")
        return RecommendationPayload.model_validate_json(content)

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
