#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config").joinpath("cluster_nodes.json")


@dataclass(frozen=True)
class ClusterNode:
    ip: str
    username: str
    private_key_path: str


def load_cluster_config(config_path: Path) -> tuple[str, str, list[ClusterNode]]:
    if not config_path.exists():
        raise FileNotFoundError(f"Cluster config not found: {config_path}")

    data = json.loads(config_path.read_text(encoding="utf-8"))

    shared_path = data.get("shared_path", "/mnt/nfs/nextflow")
    kubernetes_nfs_path = data.get("kubernetes_nfs_path", "/mnt/nfs")
    nodes_data = data.get("nodes", [])

    if not nodes_data:
        raise ValueError("Config must contain at least one node.")

    nodes = [
        ClusterNode(
            ip=node["ip"],
            username=node.get("username", data.get("ssh_user", "ubuntu")),
            private_key_path=str(Path(node.get("private_key_path", data.get("ssh_key_path", "~/.ssh/cluster_id_rsa"))).expanduser()),
        )
        for node in nodes_data
    ]

    return shared_path, kubernetes_nfs_path, nodes


def get_nfs_server_and_clients(nodes: list[ClusterNode]) -> tuple[ClusterNode, list[ClusterNode]]:
    if not nodes:
        raise ValueError("At least one cluster node is required.")
    return nodes[0], nodes[1:]


def ssh_base_args(private_key_path: str) -> list[str]:
    return [
        "ssh",
        "-i",
        private_key_path,
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
    ]


def scp_base_args(private_key_path: str) -> list[str]:
    return [
        "scp",
        "-i",
        private_key_path,
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
    ]


def run_local(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def run_remote(node: ClusterNode, remote_command: str) -> None:
    command = ssh_base_args(node.private_key_path) + [
        f"{node.username}@{node.ip}",
        remote_command,
    ]
    result = run_local(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Remote command failed on {node.ip}:\n"
            f"COMMAND: {remote_command}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def setup_nfs_server(server: ClusterNode, client_ips: list[str], shared_path: str) -> None:
    print(f"Configuring NFS server on {server.ip} ...")

    run_remote(server, f"sudo mkdir -p {shlex.quote(shared_path)}")
    run_remote(server, f"sudo chown -R nobody:nogroup {shlex.quote(shared_path)}")

    exports_lines = [
        f"{shared_path} {ip}(rw,sync,no_subtree_check,no_root_squash)"
        for ip in client_ips + [server.ip]
    ]
    exports_content = "\n".join(exports_lines) + "\n"

    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp.write(exports_content)
        tmp_path = tmp.name

    try:
        scp_cmd = scp_base_args(server.private_key_path) + [tmp_path, f"{server.username}@{server.ip}:/tmp/cluster.exports"]
        result = run_local(scp_cmd, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to copy exports file to {server.ip}:\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    run_remote(server, "sudo mkdir -p /etc/exports.d")
    run_remote(server, "sudo cp /tmp/cluster.exports /etc/exports.d/cluster.exports")
    run_remote(server, "sudo chmod 644 /etc/exports.d/cluster.exports")
    run_remote(server, "sudo exportfs -ra")
    run_remote(server, "sudo systemctl enable nfs-kernel-server")
    run_remote(server, "sudo systemctl restart nfs-kernel-server")

    print(f"NFS server configured on {server.ip}")


def setup_nfs_client(client: ClusterNode, server_ip: str, shared_path: str) -> None:
    print(f"Configuring NFS client on {client.ip} ...")

    run_remote(client, "sudo apt-get install -y nfs-common")
    run_remote(client, f"sudo mkdir -p {shlex.quote(shared_path)}")
    run_remote(client, f"sudo mount -t nfs {server_ip}:{shared_path} {shared_path} || mount {server_ip}:{shared_path} {shared_path}")

    fstab_entry = f"{server_ip}:{shared_path} {shared_path} nfs defaults,_netdev 0 0"
    escaped_entry = shlex.quote(fstab_entry)
    run_remote(
        client,
        f"grep -qsF {escaped_entry} /etc/fstab || echo {escaped_entry} | tee -a /etc/fstab >/dev/null",
    )

    print(f"NFS client configured on {client.ip}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up NFS for a cluster or generate Kubernetes PV/PVC manifests.")
    parser.add_argument(
        "--kubernetes",
        action="store_true",
        help="Generate Kubernetes PV/PVC manifests instead of configuring hosts directly.",
    )
    parser.add_argument(
        "--output-dir",
        default="k8s-nfs",
        help="Directory for generated Kubernetes manifests.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to the cluster node config file.",
    )
    return parser.parse_args()


def write_kubernetes_manifests(output_dir: str, nfs_server_ip: str) -> None:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    manifest = f"""apiVersion: v1
kind: PersistentVolume
metadata:
  name: nextflow-shared-pv
spec:
  capacity:
    storage: 100Gi
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  mountOptions:
    - hard
    - nfsvers=4.1
  nfs:
    server: {nfs_server_ip}
    path: /mnt/nfs/nextflow
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nextflow-pvc
  namespace: default
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ""
  volumeName: nextflow-shared-pv
  resources:
    requests:
      storage: 100Gi
"""

    (out_path / "nextflow-nfs.yaml").write_text(manifest, encoding="utf-8")
    print(f"Wrote Kubernetes manifest to {out_path / 'nextflow-nfs.yaml'}")


def main() -> int:
    args = parse_args()
    shared_path, _, nodes = load_cluster_config(Path(args.config))

    if args.kubernetes:
        server, _ = get_nfs_server_and_clients(nodes)
        write_kubernetes_manifests(args.output_dir, server.ip)
        return 0

    server, clients = get_nfs_server_and_clients(nodes)

    print(f"NFS server: {server.ip}")
    print(f"NFS clients: {', '.join(client.ip for client in clients) if clients else 'none'}")

    setup_nfs_server(server, [client.ip for client in clients], shared_path)

    for client in clients:
        setup_nfs_client(client, server.ip, shared_path)

    print("NFS setup complete.")
    print(f"Shared path: {shared_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
