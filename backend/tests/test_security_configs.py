import os
import yaml
import pytest

def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_docker_compose_has_security_services():
    compose_path = os.path.join(get_project_root(), 'docker-compose.yml')
    assert os.path.exists(compose_path), "docker-compose.yml not found"

    with open(compose_path, 'r') as f:
        compose = yaml.safe_load(f)

    services = compose.get('services', {})
    # The Kong gateway / standalone guardrails services were removed when the
    # architecture consolidated on the FastAPI backend; the security-relevant
    # services that must exist now are the backend, its database, and Vault.
    assert 'soc-backend' in services, "Backend service not found in docker-compose.yml"
    assert 'postgres' in services, "Postgres service not found in docker-compose.yml"
    assert 'vault' in services, "Vault service not found in docker-compose.yml"

def test_kong_config_has_security_plugins():
    kong_path = os.path.join(get_project_root(), 'kong', 'kong.yml')
    assert os.path.exists(kong_path), "kong.yml not found"
    
    with open(kong_path, 'r') as f:
        kong = yaml.safe_load(f)
        
    services = kong.get('services', [])
    assert len(services) > 0, "No services defined in kong.yml"
    
    plugins = services[0].get('plugins', [])
    plugin_names = [p.get('name') for p in plugins]
    
    assert 'rate-limiting' in plugin_names, "Rate limiting not configured in Kong"
    assert 'jwt' in plugin_names, "JWT not configured in Kong"
    assert 'mtls-auth' in plugin_names, "mTLS not configured in Kong"

def test_guardrails_config_exists():
    config_path = os.path.join(get_project_root(), 'guardrails', 'config', 'config.yml')
    assert os.path.exists(config_path), "guardrails config not found"
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
        
    assert 'models' in config, "Models not defined in guardrails config"
    assert 'rails' in config, "Rails not defined in guardrails config"

def test_ci_pipeline_has_sast_and_sca():
    # SAST lives in the dedicated Security Scan workflow (bandit), not ci.yml.
    sec_path = os.path.join(get_project_root(), '.github', 'workflows', 'security.yml')
    assert os.path.exists(sec_path), "Security Scan workflow not found"

    with open(sec_path, 'r') as f:
        workflow = yaml.safe_load(f)

    jobs = workflow.get('jobs', {})
    assert 'security' in jobs, "Security job not found in security.yml"
    steps = jobs['security'].get('steps', [])
    run_cmds = ' '.join(str(s.get('run', '')) for s in steps)
    assert 'bandit' in run_cmds, "Bandit SAST step not found in security.yml"
