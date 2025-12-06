# Infrastructure Provisioning (Ansible)

This repository contains the **Ansible Playbooks** used to bootstrap and manage the multi-cloud Kubernetes infrastructure for **Simple Lumine**. It handles the initialization of bare-metal servers, security hardening, Kubernetes (k3s) installation, Cilium deployment, and Edge Proxy configuration.

## 🏗 Architecture

- **Orchestration**: Ansible
- **Kubernetes Distro**: [k3s](https://k3s.io/) (Lightweight, Single Binary)
- **CNI & Network Security**: [Cilium](https://cilium.io/)
  - **Encryption**: WireGuard (Transparent Node-to-Node encryption)
  - **Overlay**: VXLAN
  - **KubeProxy**: Replaced by Cilium (eBPF)
  - **Hubble**: Disabled by default (managed via GitOps)
- **Networking**: [Tailscale](https://tailscale.com/) (Mesh VPN for Management & Overlay)
- **Operating System**: Debian 11/12 (Bullseye/Bookworm)
- **Edge/Transit**: Standalone Xray (VLESS-Reality) proxies acting as Cluster Gateways.

## 📂 Repository Structure

```text
infra-provisioning/
├── docs/                      # Architectural Decisions & Session Notes
├── inventory/
│   ├── hosts.ini              # Real Inventory (Host definitions ONLY)
│   ├── hosts.example.ini      # Template Inventory
│   └── group_vars/
│       ├── prod_cluster.yml   # (Private) Prod Keys & Vars
│       ├── lab_cluster.yml    # (Private) Lab Keys & Vars
│       └── edge_nodes.yml     # (Private) Edge Keys & Xray Vars
├── roles/
│   ├── bootstrap/             # "Day 0" Root Initialization (Split Tasks)
│   │   ├── tasks/             # logical steps: init, update, user, ssh, reboot
│   │   ├── templates/         # sshd_config.j2
│   │   └── handlers/          # service restart handlers
│   ├── control/               # Control Plane (K3s Server, Cilium, Tailscale)
│   ├── worker/                # Worker Node (K3s Agent, Firewall)
│   └── edge/                  # Edge Node (Xray, Tailscale, Firewall)
├── bootstrap.yml              # Phase 1: Root Initialization
└── site.yml                   # Phase 2: Main Provisioning
```

## 🚀 Getting Started (WSL Recommended)

### Prerequisites (Configuration)

Before running any playbooks, you must create the real configuration files from the examples. These files are git-ignored to protect your secrets.

1.  **Copy the Example Files**:

    ```bash
    cd inventory/group_vars
    cp prod_cluster.example.yml prod_cluster.yml
    cp lab_cluster.example.yml lab_cluster.yml
    cp edge_nodes.example.yml edge_nodes.yml
    ```

2.  **Fill in the Secrets**:
    - Edit `prod_cluster.yml` / `lab_cluster.yml` / `edge_nodes.yml`.
    - **Tailscale Auth Key**: Generate keys in Tailscale Console -> Settings -> Keys.
      - Recommend using **Tags** (`tag:prod`, `tag:lab`, `tag:edge`) when generating keys for automatic ACLs.
    - **Xray UUID/Keys**: Fill in for Edge nodes.

---

### Phase 1: Bootstrap (The "Root" Phase)

**Goal**: Transform a fresh cloud server into a secure, standardized base.
**User**: `root` (Password Auth initially).

**Key Actions**:
- **System Reset**: Forces `apt upgrade` to replace all vendor configs with standard maintainer versions (`force-confnew`).
- **Security Hardening**: Replaces `sshd_config` with our secure template (Key-Only Auth).
- **User Setup**: Creates the admin user with passwordless Sudo.

**Steps**:

1.  Edit `inventory/bootstrap.ini` with your server IPs and Root passwords.
2.  Run the bootstrap playbook:
    ```bash
    # Bootstrap a single server
    ansible-playbook bootstrap.yml -i inventory/bootstrap.ini --limit <server_ip>

    # Run the entire bootstrap (updates everything)
    ansible-playbook bootstrap.yml -i inventory/bootstrap.ini

    # Or limit to specific groups
    ansible-playbook bootstrap.yml --limit prod_cluster
    ```

---

### Phase 2: Main Provisioning (The "User" Phase)

**Goal**: Deploy applications, Install K3s/Tailscale, and Apply Security Hardening.
**User**: `{{ admin_user }}` (Key Auth).

1.  **Verify Access**: Try `ssh <admin_user>@<ip>`.
2.  **Run Main Playbook**:
    ```bash
    # Main Provisioning a single server
    ansible-playbook site.yml -i inventory/bootstrap.ini --limit <server_ip>

    # Run the entire site (updates everything)
    ansible-playbook site.yml

    # Or limit to specific groups
    ansible-playbook site.yml --limit prod_cluster
    ansible-playbook site.yml --limit edge_nodes
    ```

## 🛡 Security Strategy

- **Tailscale Authentication**: Uses Auth Keys stored in `group_vars`. No interactive login required.
- **Firewall (UFW/Iptables)**:
  - **Control**: Allows only Tailscale and Cluster Peers (Strict).
  - **Worker**: Allows Public Web (80/443), NodePorts (30000+), and Cluster Peers.
  - **Edge**: Allows Public Web (80/443).
- **GitOps Ready**: Cilium Hubble UI/Relay are disabled by default so Flux can manage them.
