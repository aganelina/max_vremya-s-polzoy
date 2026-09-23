from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """База схем API: поля snake_case в Python, camelCase в JSON (как в types.ts)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

def Optional(default: Any = None, **kwargs: Any) -> Any:
    return Field(default=default, exclude_if=lambda v: v is None, **kwargs)
