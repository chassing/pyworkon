from typing import Any

from action_completer import ActionCompleter as _ActionCompleter


class ActionCompleter(_ActionCompleter):
    async def run_action_async(self, prompt_result: str, *args, **kwargs) -> Any:
        """Run the related action from the given prompt result.
        Args:
            prompt_result (str): The result of the completer's prompt call
        Returns:
            Any: Whatever the return value of the related action callable is
        """

        func = self.get_partial_action(prompt_result)
        return await func(*args, **kwargs)


completer = ActionCompleter(fuzzy_tolerance=50)
