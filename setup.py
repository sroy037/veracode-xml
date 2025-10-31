from setuptools import setup, find_packages
from setuptools.command.install import install

class PostInstallMessage(install):
    def run(self):
        install.run(self)
        print("""
✅ Installation successful!

Try these example commands:
  xml_api_cli app_list
  xml_api_cli app_info --app_name 12345
  xml_api_cli detailed_report --app_id 12345 --formmat PDF

Run `xml_api_cli -h` for full help.

ℹ️  Note: This is not an official Veracode tool.
For issues, contact the tool owner.
""")

setup(
    name="xml_api_cli",
    version="1.0.0",
    description="Unified CLI for Veracode XML API tasks.",
    author="Soumik Roy",
    packages=find_packages(),
    cmdclass={"install": PostInstallMessage},
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
