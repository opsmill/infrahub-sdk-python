from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .node import InfrahubNode  # noqa: TC001


class RepositoryBranchInfo(BaseModel):
    internal_status: str


class RepositoryData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    repository: InfrahubNode = Field(..., description="InfrahubNode representing a Repository")
    branches: dict[str, str] = Field(
        ...,
        description="Dictionary with the name of the branch as the key and the active commit id as the value",
    )

    branch_info: dict[str, RepositoryBranchInfo] = Field(default_factory=dict)

    def get_staging_branch(self) -> str | None:
        for branch, info in self.branch_info.items():
            if info.internal_status == "staging":
                return branch
        return None
