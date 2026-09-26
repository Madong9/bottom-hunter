from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class BaseAgent(ABC, Generic[InputT, OutputT]):
    name: str

    @abstractmethod
    def run(self, agent_input: InputT) -> OutputT:
        """Execute one isolated agent step."""
        raise NotImplementedError
