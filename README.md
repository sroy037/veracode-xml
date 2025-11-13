# 🧩 XML CLI

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Veracode API](https://img.shields.io/badge/veracode-xml--api-orange)](https://docs.veracode.com/r/c_api_main)
[![Veracode API](https://img.shields.io/badge/veracode-rest--api-purple)](https://docs.veracode.com/r/c_rest_intro)

A unified and modular **CLI tool** for interacting with the [Veracode XML APIs](https://docs.veracode.com/r/c_api_main) and [Veracode REST APIs](https://docs.veracode.com/r/c_rest_intro) —  
fetch applications, reports, builds, and more — all secured with **HMAC authentication**.

---
## 🚀 Features
- 🧱 Modular task-based design (e.g. `api_check`, `app_list`, `summary_report` etc.)
- 🔄 Supports both **Static (SS)** and **Dynamic (DS)** scan types
- 📥 Auto-detects latest build for selected app
- 📂 Download reports in **XML** or **PDF**
- 🌍 Supports US, EU, and Gov regions
- 🧩 Clean structure and reusable modules

---
## ⚙️ Installation
```bash
git clone https://github.com/sroy037/xml_api_cli.git
cd xml_api_cli
pip install -r requirements.txt
pip install .
```

---
## 🧠 CLI Usage
```
# General pattern
veracli <task> [task-specific parameters]
```

---
## 📘 Examples
```
# Example: Fetch detailed report for latest dynamic scan
veracli detailed_report -n "Customer Portal" -f PDF -s ds

# Example: List all applications
veracli app_list -t REST

# Example: Get info for a specific app
veracli app_info -i 1922487

# Example: Get info for a specific build (latest if build_id omitted)
veracli build_info -n "Customer Portal" -s ds
```
⚠️ Use -h or --help with any task to see all available parameters and defaults:
```
veracli detailed_report -h
```

---
## 🧩 Supported Tasks
```
| Task                         | Description                                                  |
| ---------------------------- | ------------------------------------------------------------ |
| 🔐 `api_check`               | Validating API ID and Fetching User Information              |
| 🧰 `app_list`                | Listing all applications accessible to API ID                |
| 🧾 `app_info`                | Fetch application info by app_id or app_name                 |
| 📜 `build_list`              | List all builds under a specific application                 |
| 🧩 `build_info`              | Fetch info for a specific or latest build                    |
| 🧮 `detailed_report`         | Fetch detailed report (XML/PDF) for a specific app/build     |
| 💬 `summary_report`          | Fetch summary report (XML/PDF) for a specific app/build      |
| 🧠 `review_mitigation`       | Fetch mitigation information for issues                      |
| ⚙️ `generate_flaw_report`    | Generate Flaw report for application list ⚠️ coming soon ⚠️   |
```

---
## 🔐 Authentication
```
Store your Veracode HMAC credentials securely in:

~/.veracode/credentials

[default]
veracode_api_key_id = YOUR_KEY_ID
veracode_api_key_secret = YOUR_KEY_SECRET
```
Your credentials are automatically loaded using the Veracode Python HMAC library.

---
## 🧩 Adding New Tasks
```
Each task lives inside the tasks/ folder and exposes a run(args) function.

Example (tasks/my_new_task.py):

def run(args):
    print(f"Running new task: {args.task}")
Then invoke:

veracli my_new_task
```

---
## 🧪 Development Setup
```
# From project root
python -m veracli.cli detailed_report -n "My App" -f XML -s ds

Or install in editable mode:

pip install -e .
```

---
## 🪪 License

MIT License © 2025 Samab2024

```
Note:
This tool is not affiliated with Veracode and is intended for automation and reporting purposes using their public APIs.
