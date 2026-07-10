"""
engine/task_classifier.py
=========================
Maps a user Intent into a specific Execution Task.
This separates *what* the user wants (Intent) from *how* JARVIS will fulfill it (Task).
"""

from __future__ import annotations

from enum import Enum
from routing.intent_detector import IntentType

class ExecutionTask(str, Enum):
    READ_LOCAL_REGISTRY    = "READ_LOCAL_REGISTRY"
    EXECUTE_LOCAL_COMMAND  = "EXECUTE_LOCAL_COMMAND"
    KNOWLEDGE_RETRIEVAL    = "KNOWLEDGE_RETRIEVAL"
    AI_GENERATION          = "AI_GENERATION"

class TaskClassifier:
    """
    Determines the primary execution task required to fulfill the user's intent.
    """

    @staticmethod
    def classify(intent: IntentType) -> ExecutionTask:
        if intent == IntentType.SYSTEM_IDENTITY:
            return ExecutionTask.READ_LOCAL_REGISTRY
            
        elif intent in (IntentType.LOCAL_COMMAND, IntentType.FILE_SEARCH):
            return ExecutionTask.EXECUTE_LOCAL_COMMAND
            
        elif intent in (IntentType.FACT_QUERY, IntentType.MEMORY_QUERY, IntentType.REASONING_REQUEST):
            # These intents require fetching data before answering
            return ExecutionTask.KNOWLEDGE_RETRIEVAL
            
        elif intent in (IntentType.CONVERSATIONAL, IntentType.CODING_REQUEST, IntentType.VISION_REQUEST, IntentType.UNKNOWN):
            # These can go straight to the AI (or rely on passed-in context)
            return ExecutionTask.AI_GENERATION
            
        return ExecutionTask.AI_GENERATION
