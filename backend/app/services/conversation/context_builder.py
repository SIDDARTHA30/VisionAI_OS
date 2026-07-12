from typing import Dict, List
from app.models.conversation import Message


class ContextBuilder:
    """Builder class responsible for extracting and formatting message history context for LLM generation."""

    def build_context(
        self, 
        messages: List[Message], 
        max_input_tokens: int = 16384
    ) -> List[Dict[str, str]]:
        """Map historical messages to LLM-ready [{role, content}] schema and enforce token bounds."""
        formatted_messages = []
        
        # Format messages
        for msg in messages:
            # Map role
            formatted_messages.append({
                "role": msg.role,
                "content": msg.content
            })
            
        # Context slicing estimation: ~4 characters per token
        total_estimated_tokens = 0
        sliced_messages = []
        
        # Traverse messages backwards to prioritize recent context
        for msg_dict in reversed(formatted_messages):
            estimated_tokens = len(msg_dict["content"]) // 4
            if total_estimated_tokens + estimated_tokens > max_input_tokens:
                break
            total_estimated_tokens += estimated_tokens
            sliced_messages.insert(0, msg_dict)
            
        return sliced_messages
