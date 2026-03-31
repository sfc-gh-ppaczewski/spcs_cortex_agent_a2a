"""
Hotels Booking A2A Agent executor.
"""
from cortex_executor_base import CortexExecutorBase


class HotelsAgentExecutor(CortexExecutorBase):
    _agent_label = "Hotels"
    _fallback_message = "I could not retrieve an answer from the Cortex Agent."
