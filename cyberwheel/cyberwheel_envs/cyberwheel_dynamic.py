import copy
from importlib.resources import files
import os
import random
from gymnasium import spaces
import gymnasium as gym
from typing import Dict, Iterable, List
import yaml

from .cyberwheel import Cyberwheel
from cyberwheel.blue_agents import DynamicBlueAgent
from cyberwheel.observation import HistoryObservation
from cyberwheel.detectors.alert import Alert
from cyberwheel.detectors.handler import DetectorHandler
from cyberwheel.network.network_base import Network
from cyberwheel.network.host import Host
from cyberwheel.red_agents import ARTAgent
from cyberwheel.red_agents.strategies import ServerDowntime
from cyberwheel.reward import DecoyReward, StepDetectedReward
from cyberwheel.reward.recurring_reward import RecurringReward
from cyberwheel.reward.restore_reward import RestoreReward


def host_to_index_mapping(network: Network) -> Dict[Host, int]:
    """
    This will help with constructing the obs_vec.
    It will need to be called and save during __init__()
    because deploying decoy hosts may affect the order of
    the list network.get_non_decoy_hosts() returns.
    This might not be the case, but this will ensure the
    original indices are preserved.
    """
    mapping: Dict[Host, int] = {}
    i = 0
    for host in network.get_nondecoy_hosts():
        mapping[host.name] = i
        i += 1
    return mapping


def decoy_alerted(alerts: List[Alert]) -> bool:
    for alert in alerts:
        for dst_host in alert.dst_hosts:
            if dst_host.decoy:
                return True
    return False


class DynamicCyberwheel(gym.Env, Cyberwheel):
    metadata = {"render.modes": ["human"]}

    def __init__(
        self,
        network_config="15-host-network.yaml",
        decoy_host_file="decoy_hosts.yaml",
        host_def_file="host_definitions.yaml",
        detector_config="example_detector_handler.yaml",
        min_decoys=0,
        max_decoys=1,
        blue_reward_scaling=10,
        reward_function="default",
        red_agent="art_agent",
        evaluation=False,
        blue_config="dynamic_blue_agent.yaml",
        network=None,
        service_mapping={},
        deterministic=True,
        seed_file="runs/seed_log.txt",
        **kwargs,
    ):
        """
        The DynamicCyberwheel class is used to define the Cyberwheel environment. It allows you to use a YAML
        file to configure the actions, rewards, and logic of the blue agent. Given various configurations, it
        will initiate the environment with the red agent, blue agent, reward functions, and network state.
        Important member variables:

        * `network_config`: optional
            - The name (not filepath) of the network configuration file.
            - Default: 15-host-network.yaml

        * `decoy_host_file`: optional
            - The name (not filepath) of the decoy configuration file.
            - Default: decoy_hosts.yaml

        * `host_def_file`: optional
            - The name (not filepath) of the host configuration file.
            - Default: host_definitions.yaml
        
        * `detector_config`: optional
            - The name (not filepath) of the detector configuration file.
            - Default: detector.yaml

        * `min_decoys`: optional
            - The minimum number of decoys the blue agent should deploy. This range is not used for the default reward function.
            - Default: 0

        * `max_decoys`: optional
            - The maximum number of decoys the blue agent should deploy. This range is not used for the default reward function.
            - Default: 1      
            
        * `blue_reward_scaling`: optional
            - The scaling factor for the blue agent's rewards.
            - Default: 10

        * `reward_function`: optional
            - The reward function used in the environment. Options: 'default' | 'step_detected'
            - The default reward function uses the RecurringReward class.
            - Default: default
        
        * `red_agent`: optional
            - The red agent used in the environment. Currently only using the ART Agent
            - Default: 'art_agent'
        
        * `evaluation`: optional
            - boolean for if the environment should log information for evaluation script or not.
            - Default: False

        * `blue_config`: optional
            - The name (not filepath) of the blue agent configuration file.
            - Default: blue_agent_config.yaml

        * `network`: optional
            - The Network object to use throughout the environment. This prevents long start-up times when training with multiple environments.
            - If not passed, it will build the network with the config file passed.
            - Default: None

        * `service_mapping`: optional
            - The host -> valid_action mapping from the exploitable services on the Network.
            - If not passed, it will build the mapping when defining the red agent.
            - Default: {}

        * `deterministic`: optional
            - A boolean flag indicating whether the environment should operate in a deterministic mode. If set to True,
              the environment will use predefined seeds for reproducibility, allowing consistent behavior across runs.
              When False, the environment will generate new seeds for randomness and log them for reproducibility.
            - Default: True

        * `seed_file`: optional
            - The filename used to store and/or load seeds when in deterministic mode. This log file ensures consistent
              behavior by providing stored seeds for reproducibility across different runs.
            - Default: "runs/seed_log.txt"

        """
        network_conf_file = files("cyberwheel.resources.configs.network").joinpath(
            network_config
        )
        decoy_conf_file = files("cyberwheel.resources.configs.decoy_hosts").joinpath(
            decoy_host_file
        )
        host_conf_file = files(
            "cyberwheel.resources.configs.host_definitions"
        ).joinpath(host_def_file)

        super().__init__(config_file_path=network_conf_file, network=network)
        self.total = 0
        self.max_steps = kwargs.get("num_steps", 100)
        self.current_step = 0

        # Create action space. Decoy action for each decoy type for each subnet.
        # Length = num_decoy_host_types * num_subnets
        with open(decoy_conf_file, "r") as f:
            self.decoy_info = yaml.safe_load(f)

        with open(host_conf_file, "r") as f:
            self.host_defs = yaml.safe_load(f)["host_types"]

        self.decoy_types = list(self.decoy_info.keys())

        num_hosts = len(self.network.get_hosts())

        self.observation_space = spaces.Box(0, 1, shape=(2 * num_hosts,), dtype=float)
        self.alert_converter = HistoryObservation(
            self.observation_space.shape, host_to_index_mapping(self.network)
        )
        self.red_agent_choice = red_agent
        self.service_mapping = service_mapping

        self.red_strategy = kwargs.get("red_strategy", ServerDowntime)

        self.deterministic = deterministic
        self.seed_log = []  # List to track generated seeds for reproducibility  
        self.seed_file = seed_file

        if self.deterministic:
            self.load_seeds_from_file()


        self.red_agent = ARTAgent(
            self._get_random_user_host(), network=self.network, service_mapping=self.service_mapping, red_strategy=self.red_strategy
        )

        self.blue_conf_file = files("cyberwheel.resources.configs.blue_agent").joinpath(
            blue_config
        )
        self.blue_agent = DynamicBlueAgent(self.blue_conf_file, self.network)
        self.action_space = self.blue_agent.create_action_space()
        # self.blue_agent = DecoyBlueAgent(self.network, self.decoy_info, self.host_defs)

        detector_conf_file = files("cyberwheel.resources.configs.detector").joinpath(detector_config)
        self.detector = DetectorHandler(detector_conf_file)

        self.reward_function = reward_function

        if reward_function == "step_detected":
            self.reward_calculator = StepDetectedReward(blue_rewards=self.blue_agent.get_reward_map(), max_steps=self.max_steps)
        else:
            self.reward_calculator = RecurringReward(self.red_agent.get_reward_map(), self.blue_agent.get_reward_map())

        self.evaluation = evaluation

    def step(self, action):
        """
        Steps through environment.
        1. Blue agent runs action
        2. Red agent runs action
        3. Calculate reward based on red/blue actions and network state
        4. Convert Alerts from Detector into observation space
        5. Return obs and related metadata
        """
        blue_agent_result = self.blue_agent.act(action)
        self.reward_calculator.handle_blue_action_output(blue_agent_result.name, blue_agent_result.id, blue_agent_result.success, blue_agent_result.recurring)
        red_action_name = (
            self.red_agent.act().get_name()
        )  # red_action includes action, and target of action
        action_metadata = self.red_agent.history.history[-1]

        red_action_type = action_metadata["action"]
        red_action_src = action_metadata["src_host"]
        red_action_dst = action_metadata["target_host"]
        red_action_success = action_metadata["success"]

        self.reward_calculator.handle_red_action_output(red_action_name, self.red_agent.history.mapping[red_action_dst].decoy)

        red_action_result = (
            self.red_agent.history.recent_history()
        )

        alerts = self.detector.obs([red_action_result.detector_alert])
        obs_vec = self._get_obs(alerts)
        
        if self.reward_function == "step_detected":
            reward = self.reward_calculator.calculate_reward(
                blue_agent_result.name, blue_agent_result.success, self.red_agent.history.mapping[red_action_dst].decoy, self.current_step
            )
        else:
            reward = self.reward_calculator.calculate_reward(
                red_action_name, blue_agent_result.name, red_action_success, blue_agent_result.success, self.red_agent.history.mapping[red_action_dst].decoy
            )
        self.total += reward

        done = self.current_step >= self.max_steps
        self.current_step += 1

        info = {}
        if self.evaluation:
            info = {
                "red_action": red_action_type,
                "red_action_src": red_action_src,
                "red_action_dst": red_action_dst,
                "red_action_success": red_action_success,
                "blue_action": blue_agent_result.name,
                "network": self.blue_agent.network,
                "history": self.red_agent.history,
                "killchain": self.red_agent.killchain,
            }
        self.detector.reset()
        return (
            obs_vec,
            reward,
            done,
            False,
            info,
        )

    def _get_obs(self, alerts: List[Alert]) -> Iterable:
        return self.alert_converter.create_obs_vector(alerts)

    def _reset_obs(self) -> Iterable:
        return self.alert_converter.reset_obs_vector()
    
    def _get_random_user_host(self):
        """
        Generates a random seed based on deterministic mode. If deterministic,
        seeds are loaded from the log file. If non-deterministic, new seeds are generated
        and written to the log file.
        """
        if self.deterministic:
            if self.seed_log:
                # Use the next seed from the log
                seed = self.seed_log.pop(0)
            else:
                raise ValueError("No more seeds available in the seed log.")
        else:
            # Generate a new random seed and log it
            seed = random.randint(0, 10000)
            self.seed_log.append(seed)
            self.save_seeds_to_file()

        random.seed(seed)
        return self.network.get_random_user_host()
    
    def save_seeds_to_file(self):
        if not self.deterministic:  # Only save new seeds if non-deterministic
            path = files("cyberwheel").joinpath(self.seed_file)
            with open(path, 'w') as file:
                for seed in self.seed_log:
                    file.write(f"{seed}\n")

    def load_seeds_from_file(self):
        path = files("cyberwheel").joinpath(self.seed_file)
        if os.path.exists(path):
            with open(path, 'r') as file:
                self.seed_log = [int(line.strip()) for line in file.readlines()]
        else:
            # Create the file if it doesn't exist
            with open(path, 'w') as file:
                pass  # Creating an empty file for seed logging
            self.seed_log = []  # Initialize with an empty seed log

        
    def reset(self, seed=None, options=None):
        self.total = 0
        self.current_step = 0
        self.network.reset()

        self.red_agent.reset(
            self._get_random_user_host(), network=self.network
        )

        self.blue_agent.reset()
        
        self.alert_converter = HistoryObservation(
            self.observation_space.shape, host_to_index_mapping(self.network)
        )
        self.reward_calculator.reset()
        return self._reset_obs(), {}

    # if you open any other processes close them here
    def close(self):
        pass
