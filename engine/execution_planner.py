"""
engine/execution_planner.py
===========================
Generates the high-level strategy (ExecutionPlan) for how to fulfill the user's request.
It uses the Intent and the TaskClassifier to determine which sub-planners to invoke.
"""

from __future__ import annotations

from dataclasses import dataclass
from routing.intent_detector import IntentType
from engine.task_classifier import ExecutionTask, TaskClassifier

@dataclass
class ExecutionPlan:
    query: str
    intent: IntentType
    task: ExecutionTask
    requires_local_registry: bool
    requires_local_command: bool
    requires_knowledge: bool
    requires_ai: bool

class ExecutionPlanner:
    """
    Builds the execution strategy without executing anything.
    """

    @staticmethod
    def plan(query: str, intent: IntentType) -> ExecutionPlan:
        task = TaskClassifier.classify(intent)
        
        return ExecutionPlan(
            query=query,
            intent=intent,
            task=task,
            requires_local_registry=(task == ExecutionTask.READ_LOCAL_REGISTRY),
            requires_local_command=(task == ExecutionTask.EXECUTE_LOCAL_COMMAND),
            requires_knowledge=(task == ExecutionTask.KNOWLEDGE_RETRIEVAL),
            # AI is required if it's explicitly an AI task, OR if it's a knowledge retrieval task
            # (since knowledge retrieval usually needs summarization unless facts are direct).
            requires_ai=(task in (ExecutionTask.AI_GENERATION, ExecutionTask.KNOWLEDGE_RETRIEVAL))
        )
