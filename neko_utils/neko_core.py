import json
import datetime
import os
import subprocess
import webbrowser
import math
import re

class NekoAssistant:
    def __init__(self, data_dir="."):
        self.data_dir = data_dir
        self.automations_path = os.path.join(data_dir, "automations.json")
        self.history_path = os.path.join(data_dir, "history.json")
        self.calc_history_path = os.path.join(data_dir, "calc_history.json")
        
        self.automations = self._load_json(self.automations_path, [])
        self.history = self._load_json(self.history_path, [])
        self.calc_history = self._load_json(self.calc_history_path, [])
        
    def _load_json(self, path, default):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                try:
                    return json.load(f)
                except:
                    return default
        return default

    def _save_json(self, path, data):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def log_history(self, name, trigger):
        entry = {
            "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "name": name,
            "trigger": trigger
        }
        self.history.append(entry)
        self._save_json(self.history_path, self.history)

    def run_automation(self, name, trigger="manual"):
        for auto in self.automations:
            if auto['name'] == name:
                print(f"Meow! Running automation: {name}")
                for action in auto['actions']:
                    if action['type'] == 'open_url':
                        webbrowser.open(action['value'])
                    elif action['type'] == 'run_cmd':
                        subprocess.Popen(action['value'], shell=True)
                self.log_history(name, trigger)
                return True
        print(f"Meow? Automation '{name}' not found.")
        return False

    def calculate(self, expression):
        # Support unit conversion like "200 cm to in"
        conversion_patterns = {
            r'(\d+(\.\d+)?)\s*cm\s*to\s*in': lambda x: float(x) / 2.54,
            r'(\d+(\.\d+)?)\s*in\s*to\s*cm': lambda x: float(x) * 2.54,
            r'(\d+(\.\d+)?)\s*kg\s*to\s*lb': lambda x: float(x) * 2.20462,
            r'(\d+(\.\d+)?)\s*lb\s*to\s*kg': lambda x: float(x) / 2.20462,
        }
        
        for pattern, func in conversion_patterns.items():
            match = re.search(pattern, expression.lower())
            if match:
                val = match.group(1)
                result = func(val)
                unit_to = expression.split("to")[1].strip()
                unit_from = expression.split("to")[0].strip().split()[-1]
                res_str = f"{unit_from} → {unit_to}: {val} → {result:.4f} {unit_to}"
                self.calc_history.append(res_str)
                self._save_json(self.calc_history_path, self.calc_history)
                return res_str

        # Standard math
        try:
            # Dangerous if not careful, but for personal utility it's ok with limited globals
            safe_dict = {"math": math, "abs": abs, "round": round}
            result = eval(expression, {"__builtins__": {}}, safe_dict)
            res_str = f"{expression} = {result}"
            self.calc_history.append(res_str)
            self._save_json(self.calc_history_path, self.calc_history)
            return res_str
        except Exception as e:
            return f"Error meow: {str(e)}"

if __name__ == "__main__":
    neko = NekoAssistant()
    print("Neko Core Ready!")
    # Example usage:
    # print(neko.calculate("200 cm to in"))
    # print(neko.calculate("57+35"))
