# Infrastructure Provisioning (Ansible)

This repository contains the **Ansible Playbooks** used to bootstrap and manage the multi-cloud Kubernetes infrastructure for **Simple Lumine**. It automates the entire lifecycle: from bare-metal initialization and security hardening to Kubernetes (K3s) clustering and Edge acceleration.

## 🏗 Architecture (Updated 2025-12)

### Core Cluster (K3s)
- **Distro**: [K3s](https://k3s.io/) (Lightweight Kubernetes).
- **HA Mode (Configurable)**:
    - **Production**: Uses **Embedded Etcd** (`k3s_etcd_mode: true`) for High Availability.
    - **Lab/Dev**: Uses **SQLite** (`k3s_etcd_mode: false`) for minimal resource footprint.
- **Control Plane**: Deterministic Leader election logic verified via `k3s_leader_host` variable.

### Network & Security
- **CNI**: [Cilium](https://cilium.io/) configured with:
    - **VXLAN Overlay**: independent of underlying provider network.
    - **WireGuard Encryption**: Transparent Node-to-Node encryption.
- **Management Mesh**: [Tailscale](https://tailscale.com/).
    - All nodes (WAN/LAN) join a unified Zero Trust mesh.
    - SSH and Management traffic are restricted to `tailscale0`.

### Edge Acceleration Layer
- **Components**: [Caddy](https://caddyserver.com/) + Xray.
- **Routing Strategy**: Hybrid Model.
    - **Global**: Cloudflare -> Cluster Public IP.
    - **China**: DMIT Edge (CN2GIA) -> Cluster Public IP (Direct High-Speed).
- **Technology**:
    - **Caddy**: L7 Reverse Proxy with Host Header Injection to bypass Cloudflare hairpinning. Load Balances across multiple Worker nodes.
    - **Xray**: VLESS-Reality for specialized caching/transit.

## 📂 Repository Structure

```text
infra-provisioning/
├── docs/                      # Design Notes & Decisions
├── inventory/
│   ├── hosts.ini              # Consolidated Inventory
│   └── group_vars/
│       ├── prod_cluster.yml   # Prod Config (HA=True)
│       ├── lab_cluster.yml    # Lab Config (HA=False)
│       └── edge_nodes.yml     # Edge Config
├── roles/
│   ├── common/                # Shared: Bootstrap, Tailscale, Firewall
│   ├── k3s_control/           # K3s Server (Control Plane)
│   ├── k3s_worker/            # K3s Agent (Worker Nodes)
│   ├── cilium/                # CNI Installation
│   ├── caddy/                 # Edge Proxy (HTTP/3)
│   └── xray/                  # Transit Proxy
├── bootstrap.yml              # Phase 1: Root Initialization & Hardening
└── site.yml                   # Phase 2: Main Provisioning
```

## 🚀 Deployment Guide

### 1. Pre-requisites
Ensure `inventory/hosts.ini` is populated. See `inventory/hosts.example.ini`.

### 2. Configuration
Adjust `inventory/group_vars` to match your cluster needs:
- Set `k3s_etcd_mode` in `prod_cluster.yml` or `lab_cluster.yml`.
- Set `k3s_leader_host` to define the bootstrap node.

### 3. Execution

**Phase 1: Bootstrap** (Runs as root, creates user, locks down SSH)
```bash
ansible-playbook -i inventory/bootstrap.ini bootstrap.yml
```

**Phase 2: Provisioning** (Runs as ecosystem user)
```bash
ansible-playbook -i inventory/hosts.ini site.yml
```

### Quick Command Reference (Cheat Sheet)

**Playbook Execution**
```bash
export TARGET=HOST

# Phase 1: Bootstrap (Initial Setup)
ansible $TARGET -i inventory/bootstrap.ini -m ping

ansible-playbook bootstrap.yml -i inventory/bootstrap.ini --limit $TARGET -v

# Phase 2: Full Site Provisioning
ansible $TARGET -i inventory/hosts.ini -m ping

ansible-playbook site.yml -i inventory/hosts.ini --limit $TARGET -v

# other
ansible-playbook site.yml -i inventory/hosts.ini --limit $TARGET -vvv 
ansible-playbook site.yml -i inventory/hosts.ini -l $TARGET --tags caddy
```
