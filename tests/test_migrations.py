import os
import pytest
from alembic.config import Config
from alembic import command

def test_alembic_config_loadable():
    """Verify that alembic.ini is present and loadable by Alembic."""
    alembic_cfg_path = os.path.join("backend", "alembic.ini")
    assert os.path.exists(alembic_cfg_path)
    cfg = Config(alembic_cfg_path)
    assert cfg.get_main_option("script_location") == "alembic"
