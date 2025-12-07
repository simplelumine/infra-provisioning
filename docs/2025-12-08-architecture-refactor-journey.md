# Architecture Refactor Journey: From Complexity to Clarity

**Date**: 2025-12-08
**Topic**: Consolidation, Determinism, and Zero-Trust Security

## 1. Context: "The Complexity Fatigue"
We started with a highly granular architecture:
- **Inventory**: Split into `control.ini`, `worker.ini`, `gateway.ini` to enforce separation.
- **Roles**: Distinct roles for every function.
- **Variables**: Carefully scoped to avoid "pollution".

**The Friction Point**: The user felt a growing sense of "weirdness" and cognitive load. "Too many files to check just to find a key." "Is the logic really robust?"
This prompted a step back to re-evaluate the core philosophy: **Is strict separation helping us, or getting in the way?**

## 2. The Great Consolidation (Back to Basics)
**The Debate**: Should inventory be physically split to prevent mistakes?
**The Insight**: Physical separation creates mental friction. Logical separation (groups) is sufficient.
**The Decision**:
- Reverted to a unified `inventory/hosts.ini`.
- Restored the familiar `[edge_nodes]` naming (from "Gateways").
- **Result**: The infrastructure is now visible at a glance in a single file.

## 3. The Quest for Determinism (K3s Logic)
**The Old Way ("Magic")**:
The logic relied on `groups['control'][0]` to dynamically identify the Primary Node.
- **User's Critique**: "If I change the order in hosts.ini, does the leader change? This feels unsafe."
- **The Risk**: Implicit, order-dependent logic is the root of Split-Brain issues (e.g., node 2 thinks it's now the leader).
- **The New Way ("Explicit")**: `k3s-control.yml` was rewritten to ignore group order.
- **The Mechanism**: A single source of truth variable `k3s_leader_host` defined in `group_vars`.
- **Result**: Robustness. No matter how you run Ansible, the leader is **always** the specific host you defined.

## 4. Security Evolution: IP Trust vs. Identity Trust
**The Dilemma**: Should Worker nodes run Tailscale?
- **Initial Fear**: "If Workers run Tailscale, they open a tunnel to my Control Plane. If a Worker is hacked, the attacker gets a tunnel."
- **Variable Hell**: We tried to mitigate this by stripping `tailscale_auth_key` from global vars, leading to complex firewall templates (`if key is defined...`).
- **The Breakthrough**: The user realized that **Network Access != Permission**.
  - **Old Model**: Rely on IP whitelist (脆弱, if attacker gets the IP, they are trusted).
  - **New Model (Zero Trust)**: Install Tailscale **everywhere**. Use **Tailscale ACLs** to restrict traffic.
  - **The Logic**: "Put them all in the cage (Tailscale), then lock the cage doors (ACLs)."
**The Decision**:
- Moved `tailscale_auth_key` back to Global Scope (`prod_cluster.yml`).
- Simplified Firewall: "If you have a key, `tailscale0` is open." Security is delegated to the Identity Layer (Tailscale), not the Packet Layer (iptables).

## 5. Naming & Structure Philosophy
**The Ambiguity**: We had a file named `networking.yml`.
- **User's Reaction**: "This name feels off."
- **Analysis**: The file actually contained Sysctl, Kernel Modules, and BPF mounts. It wasn't general networking.
- **Fix**: Renamed to `k8s-prereqs.yml` (Kubernetes Prerequisites). Clear intent.

**The Role Name Debate**: Should `roles/control` be renamed to `roles/k3s_control`?
- **Decision**: **No.**
- **Philosophy**: Use generic names for Roles (Identity/Machine Function) and specific names for Tasks (Implementation).
- **Structure**: `roles/control/tasks/k3s-control.yml`. This allows future expansion without breaking the folder structure.

## 6. Conclusion
We moved from a "defensive, fragmented" architecture to a "consolidated, identity-based" architecture.
The code is now:
1.  **Cleaner**: Fewer files, less logic branching.
2.  **Safer**: Deterministic leader logic.
3.  **Modern**: Identity-based security (Tailscale) replacing IP-based security.
