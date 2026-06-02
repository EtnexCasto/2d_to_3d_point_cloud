import pytest
import sys
import os

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    
def pytest_addoption(parser):
    parser.addoption(
        "--skip-slow", action="store_true", default=False, help="Пропустить медленные тесты"
    )

def pytest_collection_modifyitems(config, items):
    if config.getoption("--skip-slow"):
        skip_slow = pytest.mark.skip(reason="опция --skip-slow")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)