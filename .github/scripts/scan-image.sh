#!/usr/bin/env bash
# Scan a local image with Trivy: OS packages and Python packages.
#
#   scan-image.sh <image>
#
# 1. trivy-image.sarif: every vulnerability, any severity, fixed or not,
#    for the GitHub Security tab.
# 2. Gate: fail on HIGH/CRITICAL vulnerabilities that have a fix available.
#    Unfixed ones (mostly Debian base packages with no patch yet) can't be
#    fixed here, so they are reported but don't block. See SECURITY.md.
set -euo pipefail
image="$1"

trivy image "$image" --quiet --scanners vuln --ignorefile .trivyignore.yaml \
    --format sarif --output trivy-image.sarif

trivy image "$image" --quiet --scanners vuln --ignorefile .trivyignore.yaml \
    --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1
