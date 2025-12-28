# Flux Bootstrap Guide

Since Flux bootstrap is a sensitive, one-time operation often requiring interactive authentication or specific tokens, we recommend running it manually from your local machine (Ansible Controller) rather than automating it via Ansible.

## Prerequisites

1.  **Flux CLI**: Install `flux` on your local machine.
    ```bash
    curl -s https://fluxcd.io/install.sh | sudo bash
    ```
2.  **Kubeconfig**: Ensure you have a valid `KUBECONFIG` pointing to the target cluster (e.g., `~/.kube/config`).
3.  **GitHub Token**: You need a GitHub Personal Access Token (classic) with `repo` permissions.

## Bootstrap Command

Run the following command to bootstrap Flux on your cluster and connect it to your infrastructure repository:

```bash
export GITHUB_TOKEN=<your-github-token>

flux bootstrap github \
  --owner=<github-user-or-org> \
  --repository=<repo-name> \
  --branch=main \
  --path=clusters/production \
  --personal \
  --private=false
```

_Adjust variables (`owner`, `repository`, `path`) as needed for your environment._

## Verification

After the command completes, verify that Flux is running:

```bash
flux check
kubectl get pods -n flux-system
```
