# Infrastructure Provisioning (Ansible)

This repository contains the **Ansible Playbooks** used to bootstrap and manage the multi-cloud Kubernetes infrastructure for **Simple Lumine**. It handles the initialization of bare-metal servers, security hardening, Kubernetes (k3s) installation, Cilium deployment, and Edge Proxy configuration.

## 🏗 Architecture

- **Orchestration**: Ansible
- **Kubernetes Distro**: [k3s](https://k3s.io/) (Lightweight, Single Binary)
  - **HA Mode**: Etcd (Embedded)
  - **Verification**: Deterministic Leader Logic (`k3s_leader_host`)
- **CNI & Network Security**: [Cilium](https://cilium.io/)
  - **Encryption**: WireGuard (Transparent Node-to-Node encryption)
  - **Overlay**: VXLAN
- **Management Plane**: [Tailscale](https://tailscale.com/) (Global Mesh)
  - **Zero Trust**: All nodes (Control, Worker, Edge) join the mesh.
  - **Security**: OS Firewall allows `tailscale0`; traffic control is enforced via **Tailscale ACLs**.
- **Operating System**: Debian 11/12 (Bullseye/Bookworm)
- **Edge/Transit**: Standalone Xray (VLESS-Reality) proxies.

## 📂 Repository Structure

```text
infra-provisioning/
├── docs/                      # Architectural Decisions & Session Notes
├── inventory/
│   ├── hosts.ini              # Single Consolidated Inventory
│   ├── hosts.example.ini      # Template Inventory
│   └── group_vars/
│       ├── prod_cluster.yml   # Global Cluster Config (Leader, Tailscale Key)
│       ├── lab_cluster.yml    # Lab Cluster Config
│       └── edge_nodes.yml     # Edge Config
├── roles/
│   ├── common/                # Shared Tasks (Tailscale, Firewall, SSH, Swap)
│   ├── control/               # Control Plane (K3s Server, Cilium)
│   ├── worker/                # Worker Node (K3s Agent)
│   └── edge/                  # Edge Node (Xray)
├── bootstrap.yml              # Phase 1: Root Initialization
└── site.yml                   # Phase 2: Main Provisioning
```

## 🚀 Getting Started (WSL Recommended)

### Prerequisites

1.  **Copy the Example Files**:

    ```bash
    cd inventory/group_vars
    cp prod_cluster.example.yml prod_cluster.yml
    cp lab_cluster.example.yml lab_cluster.yml
    cp edge_nodes.example.yml edge_nodes.yml
    ```

2.  **Define the Leader**:
    - In `prod_cluster.yml`, ensure `k3s_leader_host` matches a hostname in `hosts.ini`.
    - This creates a **Deterministic** installation source (Token/Kubeconfig fetch source).

### Phase 1: Bootstrap (Root)

**Goal**: System Reset, SSH Hardening, User Creation.

```bash
# Update everything
ansible-playbook bootstrap.yml -i inventory/bootstrap.ini
```

### Phase 2: Main Provisioning (User)

**Goal**: Install Tailscale (Global), K3s (Cluster), and Xray (Edge).

```bash
# Provision everything
ansible-playbook site.yml

# Provision specific group
ansible-playbook site.yml --limit prod_cluster
```

## 🛡 Security Strategy

- **Global Tailscale**: Every node is part of the Tailscale Mesh.
  - **SSH Access**: Recommended to restrict SSH access solely to the Tailscale IP via `sshd_config`.
  - **ACLs**: Use Tailscale ACLs to prevent Workers from accessing the Control Plane management port.
- **Firewall**:
  - **Tailscale**: Trusted Interface (`tailscale0` allowed).
  - **Public**: Minimal ports open (80/443 for Ingress, UDP for WireGuard/Xray).
