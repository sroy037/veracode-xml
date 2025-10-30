# 🧩 XML CLI

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Veracode API](https://img.shields.io/badge/veracode-xml--api-orange)](https://docs.veracode.com/r/c_api_main)

A unified and modular **CLI tool** for interacting with the [Veracode XML APIs](https://docs.veracode.com/r/c_api_main) —  
fetch detailed reports, builds, and more — all secured with **HMAC authentication**.

---

## 🚀 Features
- 🧱 Modular task-based design (e.g. `detailed_report`, `summary`, etc.)
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
xml_api_cli <task> [task-specific parameters]

# Example: Fetch detailed report for latest dynamic scan
xml_api_cli detailed_report -n "Customer Portal" -f PDF -s ds

# Example: List all applications
xml_api_cli app_list

# Example: Get info for a specific app
xml_api_cli app_info -i 1922487

# Example: Get info for a specific build (latest if build_id omitted)
xml_api_cli build_info -n "Customer Portal" -s ds
```
⚠️ Use -h or --help with any task to see all available parameters and defaults:
```
xml_api_cli detailed_report -h
```
---
## 🧩 Supported Tasks
```
| Task                         | Meaning                                         |
| ---------------------------- | ----------------------------------------------- |
| 🧾 `detailed_report`         | Represents a generated detailed report/document |
| 📋 `app_list`                | Listing all applications accessible to API ID   |
| 🌍 `app_info`                | Represent application info for specific app     |
| 📘 `build_list`              | Represents builds under application             |
| 🧱 `build_info`              | Represents build info for specific build        |
| ⚙️ `summary` *(coming soon)* | Scan summary/report                             |
```
---

## 📘 Examples
```
🔹 Get Static Scan Report (XML)

xml_api_cli detailed_report -n "Core Banking App" -f XML -s ss

🔸 Get Dynamic Scan Report (PDF)

xml_api_cli detailed_report -n "Customer Portal" -f PDF -s ds \
  -o ~/Downloads -p dyn_
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

xml_api_cli my_new_task
```

---

## 🧪 Development Setup
```
# From project root
python -m xml_api_cli.cli detailed_report -n "My App" -f XML -s ds

Or install in editable mode:

pip install -e .
```

---

## 🪪 License

MIT License © 2025 Samab2024

```
Note:
This tool is not affiliated with Veracode and is intended for automation and reporting purposes using their public APIs.
