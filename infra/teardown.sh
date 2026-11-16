#!/usr/bin/env bash
# Delete everything deploy.sh created (the whole resource group).
set -euo pipefail
RG="${RG:-rg-podsim}"
read -r -p "Delete resource group $RG and everything in it? [y/N] " ok
[[ "$ok" == "y" ]] && az group delete -n "$RG" --yes --no-wait && echo "Deletion started."
