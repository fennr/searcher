"""Compatibility facade for assistant use cases."""

from searcher.use_cases.assistant import generate_answer, get_model_id, repair_command

__all__ = ["generate_answer", "get_model_id", "repair_command"]
