# Infrastructure Provisioning (Ansible)

This repository contains the **Ansible Playbooks** used to bootstrap and manage the multi-cloud Kubernetes infrastructure for **Simple Lumine**. It handles the initialization of bare-metal servers, security hardening, Kubernetes (k3s) installation, and Edge Proxy configuration.

## 🏗 Architecture

- **Orchestration**: Ansible
- **Kubernetes Distro**: [k3s](https://k3s.io/) (Lightweight, Single Binary)
- **CNI & Network Security**: [Cilium](https://cilium.io/)
  - **Encryption**: WireGuard (Transparent Node-to-Node encryption)
  - **Overlay**: VXLAN
  - **KubeProxy**: Replaced by Cilium (eBPF)
- **Operating System**: Debian 11/12 (Bullseye/Bookworm)
- **Topology**: Multi-Cloud / Multi-Region (connected via Public IP + WireGuard)
- **Edge/Transit**: Standalone Xray (VLESS-Reality) proxies.

## 📂 Repository Structure

```text
infra-provisioning/
├── inventory/
│   ├── bootstrap.ini       # (Private) Initial Root Passwords
│   ├── hosts.ini           # (Private) Real Inventory (Keys)
│   └── group_vars/all/
│       ├── secrets.yml     # (Private) Xray/API Secrets
│       └── vars.yml        # Global Config (Admin User)
├── roles/
│   ├── common/             # Hardening (SSHD, Fail2Ban, Swap, UDP)
│   ├── k3s_server/         # Control Plane
│   ├── k3s_agent/          # Worker Node
│   ├── cilium/             # CNI Setup
│   └── edge/               # Xray Proxy
├── bootstrap.yml           # Phase 1: Root Initialization
└── site.yml                # Phase 2: Main Provisioning
```

## 🚀 Getting Started (WSL Recommended)

### Phase 1: Bootstrap (The "Root" Phase)

**Goal**: Take a fresh server, update it, create the admin user, and install keys.
**User**: `root` (Password Auth).

1.  Edit `inventory/bootstrap.ini` with your server IPs and Root passwords.
    > **Note**: For internal nodes behind a bastion, ensure you add `ansible_ssh_common_args='-o ProxyJump=simplelumine@<bastion_ip>'` so the bootstrapper can reach them.
2.  Run the bootstrap playbook:
    ```bash
    ansible-playbook bootstrap.yml -i inventory/bootstrap.ini
    ```
3.  **Result**:
    - System Updated (Force Config).
    - System Updated (Force Config).
    - Admin User created (defined in `vars.yml`).
    - SSH Key injected.
    - Server Rebooted.

### Phase 2: Main Provisioning (The "User" Phase)

**Goal**: Deploy applications and Security Hardening.
**User**: `{{ admin_user }}` (Key Auth).

1.  **Verify Access**: Try `ssh <admin_user>@<ip>`.
2.  **Run Main Playbook**:

    > **Tip**: It is recommended to configure the Bastion/Jump Host first to ensure connectivity for other nodes.

    ```bash
    # 1. Run Bastion first
    ansible-playbook site.yml --limit prod-lax-eg1

    # 2. Run everything else
    ansible-playbook site.yml
    ```

3.  **What Happens**:
    - **Common Role**: Disables Root Login, Disables Password Auth, Removes Vendor SSH Includes, Enables Swap.
    - **Apps**: Installs K3s, Cilium, etc.

## 🛡 Security Strategy

- **Bootstrap Separation**: Root password is used ONLY once (Phase 1).
- **SSHD Hardening**: Applied in Phase 2. If Phase 1 fails, you are not locked out.
- **Vendor Override**: We explicitly comment out `Include /etc/ssh/sshd_config.d/*.conf` to prevent cloud providers from weakening security.
