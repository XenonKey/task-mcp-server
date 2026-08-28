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
        raise RuntimeError("Нет авторизации: этот сценарий требует HTTP-транспорт с Cognito")

    if token.client_id != settings.cognito_app_client_id:
        raise ToolError("Токен выпущен для другого клиента")

    return {"Authorization": f"Bearer {token.token}"}


mcp = FastMCP("task-work-service", auth=build_auth_provider())


@mcp.tool()
async def get_all_tasks(status: str | None = None, limit: int = 20):
    """
    Получить список задач с фильтром по статусу и лимитом.

    Args:
        status: Статус задачи. Возможные значения:
            "OPEN", "IN_PROGRESS", "DONE", "APPROVED", "REJECTED".
            Если не указан — вернутся задачи всех статусов.
        limit: Максимальное количество задач в ответе (по умолчанию 20).
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
    Получить список задач текущего пользователя (где он исполнитель).

    Args:
        status: Статус задачи для фильтрации. Возможные значения:
            "OPEN", "IN_PROGRESS", "DONE", "APPROVED", "REJECTED".
            Если не указан — вернутся все задачи пользователя.
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
    Взять задачу в работу. Задача должна быть в статусе OPEN.
    После вызова задача переходит в статус IN_PROGRESS, а исполнителем
    становится текущий пользователь.

    Args:
        task_id: ID задачи в формате UUID.
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
    Отметить задачу как выполненную. Задача должна быть в статусе
    IN_PROGRESS или REJECTED, и текущий пользователь должен быть
    её исполнителем. После вызова задача переходит в статус DONE
    и ожидает подтверждения администратором.

    Args:
        task_id: ID задачи в формате UUID.
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
    Получить список задач, ожидающих проверки администратором
    (задачи в статусе DONE).
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
    Апрувнуть задачу по её ID. Задача должна быть в статусе DONE.
    После апрува задача переходит в статус APPROVED, и в Outbox
    добавляется событие task.completed для начисления награды
    исполнителю через Kafka.

    Args:
        task_id: ID задачи в формате UUID.
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
    Отклонить задачу по её ID. Задача должна быть в статусе DONE.
    После отклонения задача переходит в статус REJECTED — исполнитель
    сможет доработать её и снова вызвать complete_task.

    Args:
        task_id: ID задачи в формате UUID.
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
    Создать новую задачу (только для администратора).

    Args:
        title: Название задачи, должно быть уникальным.
        description: Описание задачи.
        reward: Награда за выполнение задачи.
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
