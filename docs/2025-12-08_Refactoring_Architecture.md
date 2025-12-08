# Architecture Refactoring Journey (2025-12-08)

## 1. The Monolith Problem (Initial State)

At the start of this session, the infrastructure faced several scalability concepts:

*   **Tightly Coupled Logic**: The `common` role was doing too much. It handled basic OS setup, firewalling (via a complex `rules.v4.j2`), and generic networking.
*   **Group-Based "Magic"**: Firewall rules relied heavily on inventory group names (e.g., `{% if 'prod_cluster' in group_names %}`). This meant that adding a new type of server (e.g., "staging_cluster") required modifying the *code* of the firewall role, rather than just configuration.
*   **Hidden Dependencies**: Xray was buried inside the `edge` role. Deploying Xray on a Kubernetes node would have required duplicating code or awkwardly importing the whole edge role.

## 2. The Solution: Composable Architecture

We decided to shift to a **Composable Architecture**. In this model, "Roles" are independent building blocks (Capabilities) that do one thing well. The logic of *combining* them moves to the Playbook (`site.yml`).

### Core Design Principles
1.  **Capabilities over Identity**: Don't ask "Is this a Prod Server?". Ask "Does this server need Ingress?".
2.  **Explicit Orchestration**: `site.yml` should list exactly what a server consists of.
3.  **Data-Driven Config**: Use variables (`group_vars`) to drive logic, not hardcoded conditionals.

## 3. Key Technical Decisions & Refactoring Steps

### A. The Firewall Revolution: "Capability Flags"

**The Debate**: We initially had generic rules and a "Custom Rules" loop. The user pointed out that manual rule management is tedious and prone to error.

**The Fix**: We introduced **Capability Flags**.
Instead of writing raw `iptables` rules, we defined high-level intent in `group_vars`:

*   `firewall_enable_ingress: true` -> **Outcome**: Automatically opens TCP 80 & 443.
*   `firewall_enable_xray: true` -> **Outcome**: Automatically opens TCP 10000.
*   `firewall_enable_nodeports: true` -> **Outcome**: Automatically opens K8s NodePorts (30000-32767).
*   `firewall_enable_tailscale_trust: true` -> **Outcome**: Trusts traffic from `tailscale0` interface (Admin access).

**Impact**: The `roles/firewall` template (`rules.v4.j2`) became generic. It no longer contains any project-specific IP addresses or group names.

### B. Xray Standardization

**The Challenge**: Xray configuration was split between global defaults and edge-specific overrides. There was confusion about whether `edge_nodes.yml` config was redundant.

**The Decision**:
1.  **Global Port**: We standardized the Xray port to **10000** in `all/vars.yml`. This removed the need to redefine it in every group.
2.  **Identity Retention**: We kept the `xray_clients` and `xray_private_key` overrides in `edge_nodes.yml`. This ensures that Edge Nodes have a *distinct identity* from the default admin user.
3.  **Universal Deployment**: By enabling `firewall_enable_xray` on *all* clusters (Prod & Lab), we transformed Xray from an "Edge-only" feature to a pervasive infrastructure layer.

### C. Component Splitting (Micro-Roles)

We extracted logic from monolithic roles into dedicated components:

1.  **`roles/tailscale`**:
    *   **Feature**: Added `tailscale_advertise_exit_node` variable.
    *   **Why**: Exit Node routing is dangerous on K8s Control Planes (can break CNI). By making it a variable, we safely enabled it *only* on Edge Nodes.

2.  **`roles/k8s_prereqs`**:
    *   **Feature**: Kernel modules (`overlay`, `br_netfilter`) and `sysctl` params.
    *   **Why**: Both Control Plane and Workers need this. A shared role ensures consistency and DRY (Don't Repeat Yourself).

3.  **`roles/cilium`**:
    *   **Feature**: CNI Installation via Helm.
    *   **Why**: Cilium must run *after* K3s is up. Separating it allows us to control the execution order in `site.yml`.

## 4. Final Architecture Overview

Your `site.yml` now tells the story of your infrastructure:

```yaml
- hosts: prod_control_plane
  roles:
    - tailscale      # Connectivity Layer
    - firewall       # Security Layer (Capability Driven)
    - k8s_prereqs    # Kernel Layer
    - k3s_control    # Orchestration Layer
    - cilium         # Network Layer
```

## 5. What's Next? (Validation)

Since we focused on Code Structure today, the next session needs to focus on **Runtime Verification**:
1.  **Syntax Check**: `ansible-playbook --syntax-check site.yml`
2.  **Dry Run**: `ansible-playbook --check site.yml`
3.  **Secret Vault**: Encrypting the keys in `group_vars`.
