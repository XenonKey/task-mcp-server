import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from pydantic import BaseModel

from cognito_auth import build_auth_provider
from config import settings


def _auth_headers() -> dict[str, str]:
    token = get_access_token()
    if token is None:
        raise RuntimeError("Not authenticated: this requires the HTTP transport with Cognito")

    if token.client_id != settings.cognito_app_client_id:
        raise ToolError("Token was issued for a different client")

    return {"Authorization": f"Bearer {token.token}"}


mcp = FastMCP("task-work-service", auth=build_auth_provider())


@mcp.tool()
async def get_all_tasks(status: str | None = None, limit: int = 20):
    """
    Get a list of tasks, filtered by status and limit.

    Args:
        status: Task status. Possible values:
            "OPEN", "IN_PROGRESS", "DONE", "APPROVED", "REJECTED".
            If not specified, tasks of all statuses are returned.
        limit: Maximum number of tasks in the response (default 20).
    """

    class TaskFilter(BaseModel):
        status: str | None = None
        limit: int = 20

    filter_ = TaskFilter(status=status, limit=limit)
    params = filter_.model_dump(exclude_none=True)

    async with httpx.AsyncClient() as client:
        response = await client.get(settings.task_api_base, params=params, headers=_auth_headers())
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def list_my_tasks(status: str | None = None, limit: int = 20):
    """
    Get the list of tasks for the current user (where they're the performer).

    Args:
        status: Task status to filter by. Possible values:
            "OPEN", "IN_PROGRESS", "DONE", "APPROVED", "REJECTED".
            If not specified, all of the user's tasks are returned.
    """
    raw_params = {"status_filter": status, "limit": limit}
    params = {k: v for k, v in raw_params.items() if v is not None}

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.task_api_base}/my",
            params=params,
            headers=_auth_headers(),
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def claim_task(task_id: str):
    """
    Claim a task. The task must be in OPEN status.
    After this call the task moves to IN_PROGRESS, and the current user
    becomes its performer.

    Args:
        task_id: Task ID (UUID).
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.task_api_base}/{task_id}/claim",
            headers=_auth_headers(),
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def complete_task(task_id: str):
    """
    Mark a task as done. The task must be in IN_PROGRESS or REJECTED
    status, and the current user must be its performer. After this call
    the task moves to DONE and waits for admin approval.

    Args:
        task_id: Task ID (UUID).
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.task_api_base}/{task_id}/complete",
            headers=_auth_headers(),
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_tasks_to_review():
    """
    Get the list of tasks awaiting admin review (tasks in DONE status).
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.task_api_base}/to_review",
            headers=_auth_headers(),
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def approve_task(task_id: str):
    """
    Approve a task by its ID. The task must be in DONE status.
    After approval the task moves to APPROVED, and a task.completed
    event is added to the Outbox to pay out the reward to the performer
    via Kafka.

    Args:
        task_id: Task ID (UUID).
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.task_api_base}/{task_id}/approve",
            headers=_auth_headers(),
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def reject_task(task_id: str):
    """
    Reject a task by its ID. The task must be in DONE status.
    After rejection the task moves to REJECTED — the performer can
    rework it and call complete_task again.

    Args:
        task_id: Task ID (UUID).
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.task_api_base}/{task_id}/reject",
            headers=_auth_headers(),
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def create_task(title: str, description: str, reward: float):
    """
    Create a new task (admin only).

    Args:
        title: Task title, must be unique.
        description: Task description.
        reward: Reward for completing the task.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.task_api_base,
            json={"title": title, "description": description, "reward": reward},
            headers=_auth_headers(),
        )
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000, stateless_http=True)
