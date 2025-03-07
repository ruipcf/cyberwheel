import json
from typing import Dict, List

from cyberwheel.blue_actions.blue_action import SubnetAction, generate_id, BlueActionReturn
from cyberwheel.network.network_base import Network
from cyberwheel.network.host import Host, HostType
from cyberwheel.network.service import Service
from cyberwheel.network.subnet import Subnet


def get_host_types() -> List[Dict[str, any]]:
    with open("resources/metadata/host_definitions.json", "rb") as f:
        host_defs = json.load(f)
    return host_defs["host_types"]


class DeployDecoyHost(SubnetAction):
    def __init__(self, network: Network, configs: Dict[str, any], **kwargs) -> None:
        super().__init__(network, configs)
        self.define_configs()
        self.define_services()
        self.decoy_list = kwargs.get("decoy_list", [])

    def execute(self, subnet: Subnet, **kwargs) ->  BlueActionReturn:
        name = generate_id()
        if "server" in self.type.lower():
            host_type = HostType(
                name="Server", services=self.services, decoy=True, cve_list=self.cves
            )
        else:
            host_type = HostType(
                name="Workstation",
                services=self.services,
                decoy=True,
                cve_list=self.cves,
            )

        self.host = self.network.create_decoy_host(name, subnet, host_type)
        self.decoy_list.append(name)
        return BlueActionReturn(name, True, 1)

class IsolateDecoyHost(SubnetAction):
    def __init__(self, network: Network, configs: Dict[str, any], **kwargs) -> None:
        super().__init__(network, configs)
        self.define_configs()
        self.define_services()
        self.isolate_data = kwargs.get("isolate_data", [])

    def execute(self, subnet: Subnet, **kwargs) ->  BlueActionReturn:
        name = generate_id()
        host_type = HostType(
            name=name, services=self.services, decoy=True, cve_list=self.cves
        )
        self.host = self.network.create_decoy_host(name, subnet, host_type)
        return BlueActionReturn(name, self.isolate_data.append_decoy(self.host, subnet), 1)
