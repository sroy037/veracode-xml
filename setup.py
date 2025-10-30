from setuptools import setup, find_packages

setup(
    name="xml-api-cli",
    version="1.0.0",
    description="Unified CLI for Veracode XML API tasks.",
    author="Soumik Roy",
    packages=find_packages(),
    install_requires=[
        "requests",
        "veracode-api-signing",
    ],
    entry_points={
        "console_scripts": [
            "xml_api_cli=xml_api_cli.cli:main",
        ],
    },
    python_requires=">=3.8",
)
