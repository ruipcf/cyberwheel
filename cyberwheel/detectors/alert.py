from __future__ import annotations
from ipaddress import IPv4Address, IPv6Address
from typing import Any, List, Dict, Union
from copy import deepcopy
from cyberwheel.network.host import Host
from cyberwheel.network.service import Service
from cyberwheel.red_actions.technique import Technique
IPAddress = Union[IPv4Address, IPv6Address, None]

class Alert():
    FIELD_NAMES = set(['src_host', 'dst_hosts', 'services'])
    def __init__(self, 
                 src_host: Union[None, Host] = None, 
                 techniques: List[Technique]=[], 
                 dst_hosts: List[Host] = [], 
                 services: List[Service]=[],
                 user: str="", 
                 command: str="", 
                 files: List[Any]=[], 
                 other_resources: Dict[str, Any]={}, 
                 os: str="", 
                 os_version: str=""):
        """
        A class for holding information on actions made by a non-blue agent. (Maybe we'll do a green agent at some point?)
        ### Generic
        These components are neither network nor host based data components.
            - src_host: the host that an action is performed on. It either creates network traffic or something is done on the host itself.
            - techniques: the technique(s) that caused this alert to be created (made a red action successful). It's probably a stretch for a detector to know what techniques the red agent is using. This is primarily used for determining the probability of the detector noticing the action. Should be filtered out.
       
        ### Network-based Data Components
            - dst_hosts: the hosts the src_host is communicating with (possibly hosts being attacked)
            - services: the services the hosts are communicating through (possibly services being targeted for an attack)
            - src_ip: the IP of the source host. Also found in src_host, but is here for convenience
            - dst_ips: the IPs of the destination hosts. Also found in each element of dst_hosts, but is here for convenience
            - dst_ports: the ports of the services. Also found in services, but is here for convenience 
        
        ### Host-based Data Components
        These components are related to the host's system itself, like the OS or user. This is rather abstract and unimplemented right now.
            - user: username of the user who executed a command on the host.
            - command: the command/file being executed. Could include things like syscalls and regular executables
            - files: additional files being accessed. I.e log files
            - other_resources: other resources used in an abnormal way that are specifically targeted by an action. I.e. a local database
            - os: the OS of the system
            - os_version: version of the OS
        """
        
        self.src_host = src_host
        self.techniques = techniques 

        self.dst_hosts = dst_hosts
        self.services = services

        if self.src_host is not None: self.src_ip = self.src_host.mac_address
        if self.dst_hosts is not None: self.dst_ips = [h.mac_address for h in self.dst_hosts]
        if self.services is not None: self.dst_ports = [s.port for s in self.services]

        self.user = user
        self.command = command
        self.files = files
        self.other_resources = other_resources
        self.os = os
        self.os_version = os_version

        

    def add_dst_host(self, host: Host) -> None:
        self.dst_hosts.append(host)
        self.dst_ips.append(host.mac_address)

    def add_src_host(self, host: Host) -> None:
        self.src_host = host

    def add_service(self, service: Service) -> None:
        self.services.append(service)
        self.dst_ports.append(service.port)

    def remove_src_host(self) -> None:
        self.src_host = None

    def remove_dst_host(self, host: Host) -> None:
        if host in self.dst_hosts:
            self.dst_hosts.remove(host)

    def remove_service(self, service: Service) -> None:
        if service in self.services:
            self.services.remove(service)

    def add_techniques(self, techniques: List[str])-> None:
        self.techniques.extend(techniques)

    def to_dict(self) -> Dict:
        d = deepcopy(self.__dict__)
        for k in self.__dict__.keys():
            if k not in self.FIELD_NAMES:
                d.pop(k)
        return d

    # TODO Check the performance on this.
    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, Alert):
            return False
        # return True # DELETE 
        src_host = self.src_host == __value.src_host
        dst_hosts = len(self.dst_hosts) == len(__value.dst_hosts)
        if dst_hosts:
            for host in self.dst_hosts:
                if host not in __value.dst_hosts:
                    dst_hosts = False
        services = len(self.services) == len(__value.services)
        if services:
            for service in self.services:
                if service not in __value.services:
                    services = False
        if src_host and dst_hosts and services:
            return True
        return False 

    def __str__(self) -> str:
        return f"Alert: dst_hst: {[str(h) for h in self.dst_hosts]}, services: {[str(s) for s in self.services]}"
