"""Evidence-bearing models shared by validation and rule results."""

from __future__ import annotations

from typing import Any, Annotated, Optional, Union

from pydantic import BaseModel, ConfigDict, StringConstraints


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
FieldValue = Union[str, int, float, bool, list[Any], dict[str, Any]]


class ConsistencyParticipant(BaseModel):
    """A document field value that participated in a consistency check."""

    model_config = ConfigDict(extra="forbid")

    document_id: NonEmptyString
    field: NonEmptyString
    value: Optional[FieldValue]
