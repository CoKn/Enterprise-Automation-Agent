from agent.application.ports.outbound.llm_interface import LLM
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, PrivateAttr


class OpenAIAdapter(LLM, BaseModel):
    api_key: str
    deployment_name: str
    _client: OpenAI = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self._client = OpenAI(api_key=self.api_key)

    def call(
        self,
        prompt: str,
        system_prompt: str = "You are a helpfull assistant.",
        json_mode: bool = False,
        max_tokens: int = 16384,
        temperature: float = 0,
        top_p: float = 1
    ) -> str:
        response_type = "json_object" if json_mode else "text"
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
            resp = self._client.chat.completions.create(
                messages=messages,
                model=self.deployment_name,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                response_format={"type": response_type},
            )
            return resp.choices[0].message.content
        except OpenAIError as e:
            return f"An OpenAI error occurred: {e}"