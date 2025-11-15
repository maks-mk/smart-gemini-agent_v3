from typing import Any, Dict, List, Type, Optional
import json

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from ..security import ActionType


async def _apply_guardrails_for_plan_action(
    agent: Any,
    mode: str,
    steps: int = 0,
) -> Optional[Dict[str, Any]]:
    guardrails = getattr(agent, "guardrails", None)
    current_plan = getattr(agent, "current_plan", None)
    if not guardrails or not current_plan:
        return None

    main_goal = getattr(current_plan, "main_goal", "")
    subtasks = getattr(current_plan, "subtasks", []) or []
    params: Dict[str, Any] = {
        "mode": mode,
        "subtasks_total": len(subtasks),
        "main_goal": main_goal,
    }
    if mode == "step" and steps:
        params["steps"] = steps

    validation = await guardrails.validate_action(
        ActionType.EXECUTE_PLAN,
        params,
        context=main_goal,
    )
    if not validation.allowed:
        return {
            "status": "blocked",
            "reason": validation.reason,
            "risk_level": validation.risk_level,
        }
    if validation.requires_confirmation:
        if mode == "step":
            action_description = f"Выполнить до {steps} подзадач плана '{main_goal}'"
        else:
            action_description = (
                f"Выполнить план '{main_goal}' ({len(subtasks)} подзадач)"
            )
        confirmed = await guardrails.request_confirmation(
            action_description=action_description,
            risk_level=validation.risk_level,
        )
        if not confirmed:
            return {
                "status": "cancelled",
                "reason": "Действие не подтверждено",
                "risk_level": validation.risk_level,
            }
    return None


class PlanCreateInput(BaseModel):
    task: str = Field(
        description="Описание сложной задачи, для которой нужно построить план выполнения",
    )


class PlanCreateTool(BaseTool):
    name: str = "plan_create"
    description: str = (
        "Создает план выполнения сложной задачи и сохраняет его как текущий план агента"
    )
    args_schema: Type[BaseModel] = PlanCreateInput
    agent: Any

    def __init__(self, agent: Any, **kwargs: Any) -> None:
        super().__init__(agent=agent, **kwargs)
        self.agent = agent

    def _run(self, task: str) -> str:
        raise NotImplementedError("plan_create поддерживается только в асинхронном режиме")

    async def _arun(self, task: str) -> str:
        planner = getattr(self.agent, "task_planner", None)
        if not planner:
            return "Система планирования отключена"

        plan = await self.agent.create_task_plan(task)
        if not plan:
            return "Не удалось создать план"

        if hasattr(plan, "to_dict"):
            data = plan.to_dict()
        else:
            main_goal = getattr(plan, "main_goal", task)
            subtasks_data: List[Dict[str, Any]] = []
            for t in getattr(plan, "subtasks", []) or []:
                subtasks_data.append(
                    {
                        "id": getattr(t, "id", ""),
                        "description": getattr(t, "description", ""),
                        "status": getattr(getattr(t, "status", None), "value", str(getattr(t, "status", ""))),
                        "priority": getattr(getattr(t, "priority", None), "value", None),
                    }
                )

            data = {
                "task_id": getattr(plan, "task_id", ""),
                "main_goal": main_goal,
                "subtasks": subtasks_data,
            }

        return json.dumps(data, ensure_ascii=False)


class PlanNextInput(BaseModel):
    steps: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Максимальное количество подзадач, которые нужно выполнить за один вызов инструмента",
    )


class PlanNextTool(BaseTool):
    name: str = "plan_next"
    description: str = (
        "Выполняет одну или несколько следующих подзадач текущего плана. "
        "Используется для поэтапного выполнения плана."
    )
    args_schema: Type[BaseModel] = PlanNextInput
    agent: Any

    def __init__(self, agent: Any, **kwargs: Any) -> None:
        super().__init__(agent=agent, **kwargs)
        self.agent = agent

    def _run(self, steps: int = 1) -> str:
        raise NotImplementedError("plan_next поддерживается только в асинхронном режиме")

    async def _arun(self, steps: int = 1) -> str:
        agent = self.agent
        if not getattr(agent, "task_planner", None) or not getattr(agent, "current_plan", None):
            return json.dumps(
                {
                    "status": "error",
                    "reason": "Нет активного плана или планировщик отключен",
                },
                ensure_ascii=False,
            )

        guardrails_result = await _apply_guardrails_for_plan_action(
            agent=agent,
            mode="step",
            steps=steps,
        )
        if guardrails_result is not None:
            return json.dumps(guardrails_result, ensure_ascii=False)

        results: List[Dict[str, Any]] = []
        executed = 0
        for _ in range(steps):
            res = await agent.execute_next_task()
            results.append(res)
            executed += 1
            if "message" in res or "error" in res:
                break
            if res.get("completed") is not True:
                break

        plan_progress: Dict[str, Any] = {}
        current_plan = getattr(agent, "current_plan", None)
        if current_plan and hasattr(current_plan, "get_progress"):
            try:
                plan_progress = current_plan.get_progress()
            except Exception:
                plan_progress = {}

        return json.dumps(
            {
                "status": "ok",
                "executed": executed,
                "results": results,
                "progress": plan_progress,
            },
            ensure_ascii=False,
        )


class PlanRunInput(BaseModel):
    pass


class PlanRunTool(BaseTool):
    name: str = "plan_run"
    description: str = (
        "Выполняет текущий план до завершения. "
        "Используется для автоматического выполнения серии подзадач."
    )
    args_schema: Type[BaseModel] = PlanRunInput
    agent: Any

    def __init__(self, agent: Any, **kwargs: Any) -> None:
        super().__init__(agent=agent, **kwargs)
        self.agent = agent

    def _run(self) -> str:
        raise NotImplementedError("plan_run поддерживается только в асинхронном режиме")

    async def _arun(self) -> str:
        agent = self.agent
        if not getattr(agent, "task_planner", None) or not getattr(agent, "current_plan", None):
            return json.dumps(
                {
                    "status": "error",
                    "reason": "Нет активного плана или планировщик отключен",
                },
                ensure_ascii=False,
            )

        guardrails_result = await _apply_guardrails_for_plan_action(
            agent=agent,
            mode="run",
        )
        if guardrails_result is not None:
            return json.dumps(guardrails_result, ensure_ascii=False)

        result = await agent.run_plan()
        progress = result.get("progress", {})

        return json.dumps(
            {
                "status": "ok" if "error" not in result else "error",
                "completed": result.get("completed_count", 0),
                "failed": result.get("failed_count", 0),
                "progress": progress,
                "error": result.get("error"),
            },
            ensure_ascii=False,
        )
