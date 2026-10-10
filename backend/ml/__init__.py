"""Machine-learning core for agent failure detection and intervention."""

FAILURE_TYPES = ["loop", "tool_thrashing", "hallucinated_tool", "token_waste"]
CLASSES = ["healthy"] + FAILURE_TYPES
