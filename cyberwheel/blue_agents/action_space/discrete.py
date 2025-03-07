from typing import List
from gymnasium import Space
from gymnasium.spaces import Discrete
from gymnasium.core import ActType

from .action_space import ActionSpace, ASReturn
from cyberwheel.network.network_base import Network
from cyberwheel.blue_actions.blue_action import BlueAction

class _ActionRangeChecker():
    def __init__(self, name: str, action: BlueAction, type: str, lower_bound: int, upper_bound: int):
        self.name = name
        self.action = action
        self.type = type
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound

    def check_range(self, index: int) -> bool:
        return index >= self.lower_bound and index < self.upper_bound

class DiscreteActionSpace(ActionSpace):
    def __init__(self, network: Network) -> None:
        super().__init__(network)
        self._action_space_size: int  = 0
        self._action_checkers: List[_ActionRangeChecker] = []
    
    def select_action(self, action: ActType) -> ASReturn:
        try:
            action = int(action)
        except:
            raise TypeError(f"provided action is of type {type(action)} and is unsupported by the chosen ActionSpaceConverter")
        
        for ac in self._action_checkers:
            if not ac.check_range(action):
                continue
            name = ac.name
            if ac.type == "standalone":
                return ASReturn(name, ac.action)
            elif ac.type == "host":
                index = (action - ac.lower_bound) % self.num_hosts
                return ASReturn(name, ac.action, args=[self.hosts[index]])
            elif ac.type == "subnet":
                index = (action - ac.lower_bound) % self.num_subnets
                return ASReturn(name, ac.action, args=[self.subnets[index]])
            elif ac.type == "range":
                index = (action - ac.lower_bound) % (ac.upper_bound - ac.lower_bound)
                return ASReturn(name, ac.action, args=[index])
            else:
                raise TypeError(f"Unknown action type: {ac.type}.")

    def add_action(self, name: str, action: BlueAction, **kwargs):
        action_type = kwargs.get("type", "")

        lower_bound = self._action_space_size
        if action_type == "standalone":
            self._action_space_size += 1
        elif action_type.lower() == "host": 
            self._action_space_size += self.num_hosts
        elif action_type.lower() == "subnet":
            self._action_space_size += self.num_subnets
        elif action_type.lower() == "range":
            range_ = kwargs.get("range", int)
            if range_ <= 0:
                raise ValueError(f"value for range must be > 0")
            self._action_space_size += range_
        else:
            raise ValueError(f"action_type must be 'host', 'subnet', 'standalone', or 'range'")
        upper_bound = self._action_space_size
        self._action_checkers.append(_ActionRangeChecker(name, action, action_type, lower_bound, upper_bound))

    def get_shape(self) -> tuple[int, ...]:
        return (self._action_space_size,)

    def create_action_space(self) -> Space:
        return Discrete(self._action_space_size)