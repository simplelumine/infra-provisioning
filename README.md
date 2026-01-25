# Infrastructure Provisioning (Ansible)

This repository contains the **Ansible Playbooks** used to bootstrap and manage the multi-cloud Kubernetes infrastructure for **Simple Lumine**. It automates the entire lifecycle: from bare-metal initialization and security hardening to Kubernetes (K3s) clustering and Edge acceleration.

## 🏗 Architecture

### Core Cluster (K3s)
- **Distro**: [K3s](https://k3s.io/) (Lightweight Kubernetes).
- **HA Mode (Configurable)**:
    - **Production**: Uses **Embedded Etcd** (`k3s_etcd_mode: true`) for High Availability.
    - **Lab/Dev**: Uses **SQLite** (`k3s_etcd_mode: false`) for minimal resource footprint.
- **Control Plane**: Deterministic Leader election logic verified via `k3s_leader_host` variable.

### Network & Security
- **CNI**: [Cilium](https://cilium.io/) (VXLAN, WireGuard).
- **Mesh**: [Tailscale](https://tailscale.com/) for secure node-to-node communication.
- **Firewall**: `firewall` role manages `iptables` rules.
- **Proxy**: [Xray](https://github.com/XTLS/Xray-core) for transit and edge routing.
- **Edge**: [Caddy](https://caddyserver.com/) for HTTP/3 reverse proxying.

### Monitoring
- **Metrics**: `node_exporter` deployed on Edge nodes.

## 📂 Repository Structure

```text
infra-provisioning/
├── inventory/
│   ├── bootstrap.ini          # Initial bootstrapping inventory
│   ├── cluster.ini            # Main Kubernetes Cluster inventory
│   ├── edge.ini               # Edge nodes inventory
│   ├── sandbox.ini            # Testing/Sandbox inventory
│   └── group_vars/            # Group-specific variables
├── roles/
│   ├── bootstrap/             # OS Upgrade & Hardening
│   ├── caddy/                 # Edge Proxy
│   ├── cilium/                # CNI Installation
│   ├── common/                # Shared Configs (NTP, users, etc.)
│   ├── derp/                  # Tailscale DERP Server
│   ├── docker/                # Docker installation (Optional)
│   ├── firewall/              # Security Rules
│   ├── k3s_control/           # K3s Server
│   ├── k3s_worker/            # K3s Agent
│   ├── k8s_prereqs/           # Kernel modules & sysctl
│   ├── node_exporter/         # Prometheus Metrics
│   ├── tailscale/             # Mesh Networking
│   └── xray/                  # Transit Proxy
├── bootstrap.yml              # Initial Setup Playbook
└── site.yml                   # Main Provisioning Playbook
```

## 🚀 Deployment Guide

### 1. Bootstrap Phase
Run this only once for new server initialization (create users, secure SSH).

```bash
ansible-playbook -i inventory/bootstrap.ini bootstrap.yml
```

### 2. Provisioning Phase
Run the main playbook against specific environments.

**Cluster Provisioning:**
```bash
ansible-playbook -i inventory/cluster.ini site.yml
```

**Edge Provisioning:**
```bash
ansible-playbook -i inventory/edge.ini site.yml
```

**Sandbox/Test:**
```bash
ansible-playbook -i inventory/sandbox.ini site.yml
```

### Quick Command Reference (Cheat Sheet)

```bash
# Export target host for single-node operations
export TARGET=target-node-id

# --- Phase 1: Bootstrap (Root Access) ---
# Check connectivity
ansible $TARGET -i inventory/bootstrap.ini -m ping

# Run bootstrap for a single host
ansible-playbook bootstrap.yml -i inventory/bootstrap.ini --limit $TARGET -v

# Run bootstrap for ALL new hosts
ansible-playbook bootstrap.yml -i inventory/bootstrap.ini -v

# --- Phase 2: Cluster Provisioning ---
# Check connectivity
ansible all -i inventory/cluster.ini -m ping

# Provision all cluster nodes
ansible-playbook site.yml -i inventory/cluster.ini -v

# Provision specific node (e.g. after maintenance)
ansible-playbook site.yml -i inventory/cluster.ini --limit $TARGET -v

# --- Edge Nodes & Maintenance ---
# Update Firewall rules only
ansible-playbook site.yml -i inventory/edge.ini --tags "firewall" -v

# Update Tailscale/Mesh config only
ansible-playbook site.yml -i inventory/edge.ini --tags "tailscale" -v

# Debugging: Start from a specific task
ansible-playbook site.yml -i inventory/edge.ini --limit $TARGET --start-at-task="Install Caddy" -v
```
