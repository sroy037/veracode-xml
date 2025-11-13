from setuptools import setup, find_packages

setup(
    name="veracli",
    version="1.0.0",
    description="Unified CLI for Veracode API tasks.",
    author="Soumik Roy",
    packages=find_packages(),
    install_requires=[
        "requests",
        "veracode-api-signing",
    ],
    entry_points={
        "console_scripts": [
            "veracli=xml_api_cli.cli:main",
        ],
    },
    python_requires=">=3.8",
)
