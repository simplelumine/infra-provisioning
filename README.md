# Infrastructure Provisioning (Ansible)

This repository contains the **Ansible Playbooks** used to bootstrap and manage the multi-cloud Kubernetes infrastructure for **Simple Lumine**. It handles the initialization of bare-metal servers, security hardening, Kubernetes (k3s) installation, and Edge Proxy configuration.

## 🏗 Architecture

*   **Orchestration**: Ansible
*   **Kubernetes Distro**: [k3s](https://k3s.io/) (Lightweight, Single Binary)
*   **CNI & Network Security**: [Cilium](https://cilium.io/)
    *   **Encryption**: WireGuard (Transparent Node-to-Node encryption)
    *   **Overlay**: VXLAN
    *   **KubeProxy**: Replaced by Cilium (eBPF)
*   **Operating System**: Debian 11/12 (Bullseye/Bookworm)
*   **Topology**: Multi-Cloud / Multi-Region (connected via Public IP + WireGuard)
*   **Edge/Transit**: Standalone Xray (VLESS-Reality) proxies on premium lines (CN2 GIA).

## 📂 Repository Structure

```text
infra-provisioning/
├── inventory/
│   ├── hosts.example.ini   # Template inventory (Public safe)
│   ├── hosts.ini           # Real inventory (GitIgnored)
│   └── group_vars/
│       └── all/
│           └── secrets.yml # Secrets (UUIDs, Keys) (GitIgnored)
├── roles/
│   ├── common/             # OS setup: Users, SSH Hardening, Fail2Ban, NTP, UFW/iptables
│   ├── k3s_server/         # Control Plane installation (No Flannel, No Traefik)
│   ├── k3s_agent/          # Worker Node joining
│   ├── cilium/             # Cilium CNI installation (Helm)
│   └── edge/               # Xray Proxy installation
└── site.yml                # Main Playbook
```

## 🚀 Getting Started

### Prerequisites

*   **WSL (Windows Subsystem for Linux)** or a generic Linux/macOS terminal.
*   **Ansible** (`sudo apt install ansible sshpass`)
*   **SSH Access**: You must likely ProxyJump through a Bastion host defined in your ssh config or inventory.

### 1. Configure Inventory & Secrets

Copy the example inventory:
```bash
cp inventory/hosts.example.ini inventory/hosts.ini
```

Edit `inventory/hosts.ini` with your real IP addresses.

Create the secrets file:
```bash
mkdir -p inventory/group_vars/all
nano inventory/group_vars/all/secrets.yml
```

Add your sensitive data:
```yaml
xray_clients:
  - id: "your-uuid-here"
    name: "user1"
xray_private_key: "your-private-key-here"
```

### 2. Boostrap a New Cluster (First Run)

For fresh servers (Root access only):

```bash
# Test connectivity
ansible -m ping all -u root

# Run everything
ansible-playbook site.yml -u root
```

### 3. Maintenance Runs

After bootstrapping, `Root` login is disabled. Use the administrative user (`simplelumine`):

```bash
ansible-playbook site.yml
```

### 4. Deploying Edge Nodes / Proxies

To only update the Xray configuration on Edge nodes:

```bash
ansible-playbook site.yml -l edge_nodes
```

## 🛡 Security Features

*   **Firewall**: `iptables-persistent` configured with a strict whitelist.
    *   **Allow**: SSH (22), ICMP, Loopback.
    *   **Cluster**: Allows all traffic from peer Node IPs (Mesh).
    *   **Kube API**: Allowed only from Tailscale Subnet (`100.64.0.0/10`) and peer nodes.
    *   **Deny**: Everything else.
*   **Encryption**: All multi-cloud traffic is wrapped in WireGuard by Cilium.
*   **SSH**: Password auth disabled, Root login disabled, Fail2Ban enabled.
