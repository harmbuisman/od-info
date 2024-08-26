"""
python -m pip install -e .["dev"]
"""

from setuptools import find_packages, setup

test_packages = [
    "pytest>=5.4.3",
    "black==23.12.1",
    "flake8==7.0.0",
    "isort==5.12.0",
]

base_packages = [
    "flask",
    "jinja2",
    "PyYAML",
    "bs4",
    "pillow",
    "matplotlib",
    "requests",
    "wtforms",
    "flask-login",
]

setup(
    name="od-info",
    packages=find_packages(exclude=["notebooks", "docs", "vantage6"]),
    install_requires=base_packages,
    python_requires=">=3.11",
)
