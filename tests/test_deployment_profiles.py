"""JARVIS OS - Deployment Profiles and Templates Verification.

Validates that deployment templates (Docker Compose, NGINX configurations) have valid structures.
"""

import os

import yaml


def test_docker_compose_dev_yaml_parsing() -> None:
    """Verify docker-compose.dev.yml is valid YAML and defines correct services."""
    path = "deploy/docker-compose.dev.yml"
    assert os.path.exists(path), f"File {path} does not exist"

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "services" in config
    assert "api" in config["services"]
    assert "db" in config["services"]
    assert "redis" in config["services"]

    api_service = config["services"]["api"]
    assert "environment" in api_service
    # Verify reloading is active in dev mode
    assert "--reload" in api_service["command"]


def test_docker_compose_prod_yaml_parsing() -> None:
    """Verify docker-compose.prod.yml matches production constraints."""
    path = "deploy/docker-compose.prod.yml"
    assert os.path.exists(path), f"File {path} does not exist"

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "services" in config
    assert "api" in config["services"]
    assert "db" in config["services"]
    assert "redis" in config["services"]

    api_service = config["services"]["api"]
    # Production resource limits
    assert "deploy" in api_service
    assert "limits" in api_service["deploy"]["resources"]
    assert "cpus" in api_service["deploy"]["resources"]["limits"]
    assert "memory" in api_service["deploy"]["resources"]["limits"]

    # Production health check liveness check
    assert "healthcheck" in api_service
    assert "test" in api_service["healthcheck"]
    assert "/api/v1/platform/liveness" in "".join(api_service["healthcheck"]["test"])


def test_nginx_config_file_exists() -> None:
    """Verify nginx proxy configuration template exists and is readable."""
    path = "deploy/nginx/nginx.conf"
    assert os.path.exists(path), f"File {path} does not exist"

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "upstream jarvis_api" in content
    assert "location /ws/" in content
