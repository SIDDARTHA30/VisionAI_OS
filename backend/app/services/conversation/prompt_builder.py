from app.prompts.system import DEFAULT_SYSTEM_PROMPT
from app.prompts.developer import DEVELOPER_SYSTEM_PROMPT
from app.prompts.chat import CHAT_SYSTEM_PROMPT
from app.prompts.coding import CODING_SYSTEM_PROMPT
from app.prompts.study import STUDY_SYSTEM_PROMPT


class PromptBuilder:
    """Builder class responsible for loading and resolving system/user prompt templates."""

    def get_system_prompt(self, assistant_type: str = "chat") -> str:
        """Resolve system instruction prompt based on target assistant profile types."""
        clean_type = assistant_type.strip().lower()
        
        if clean_type == "coding":
            return CODING_SYSTEM_PROMPT
        elif clean_type == "developer":
            return DEVELOPER_SYSTEM_PROMPT
        elif clean_type == "study":
            return STUDY_SYSTEM_PROMPT
        elif clean_type == "chat":
            return CHAT_SYSTEM_PROMPT
        else:
            return DEFAULT_SYSTEM_PROMPT
