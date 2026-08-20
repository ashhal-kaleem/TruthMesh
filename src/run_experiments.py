import os
import json
from tqdm import tqdm
from src.main_agent import FactAgent
from src.experiments import cot, direct, folk, sase

def sanitize_model_name(model):
    return model.replace("/", "__").replace(":", "-")
def main_experiment(model, data_folder, output_folder, method):
    for data_type in os.listdir(data_folder):
        data_type_path = os.path.join(data_folder, data_type)
        if not os.path.isdir(data_type_path):
            continue

        for filename in os.listdir(data_type_path):
            if not filename.endswith(".json"):
                continue

            file_path = os.path.join(data_type_path, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            output_data = []
            for item in tqdm(data, desc=f"Processing {filename}"):
                result = method(model, item["claim"])
                item["predicted_label"] = result["label"]
                item["predicted_explanation"] = result["explanation"]
                output_data.append(item)

            # Output directory: method/{model}/{data_type}/
            model_name = sanitize_model_name(model)
            output_dir = os.path.join(output_folder, model_name, data_type)
            os.makedirs(output_dir, exist_ok=True)

            # Save result
            output_path = os.path.join(output_dir, filename)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)


def main_factagent(model, data_folder, output_folder):
    for data_type in os.listdir(data_folder):
        data_type_path = os.path.join(data_folder, data_type)
        if not os.path.isdir(data_type_path):
            continue
        if "fever" in data_type.lower():
            dataset = "fever"
        elif "scifact" in data_type.lower():
            dataset = "scifact"
        else:
            dataset = "hover"
        for filename in os.listdir(data_type_path):
            if not filename.endswith(".json"):
                continue

            file_path = os.path.join(data_type_path, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            agent = FactAgent(dataset=dataset)
            output_data = []
            for item in tqdm(data, desc=f"Processing {filename}"):
                result = agent.process_claim(item, verbose=True)
                item["predicted_label"] = result["label"]
                item["predicted_explanation"] = result["explanation"]
                output_data.append(item)

            # Output directory: method/{model}/{data_type}/{filename.json}
            model_name = sanitize_model_name(model)
            output_dir = os.path.join(output_folder, model_name, data_type)
            os.makedirs(output_dir, exist_ok=True)

            # Save result
            output_path = os.path.join(output_dir, filename)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    for model in ["gpt-4o-mini", "ollama/llama3.2:1b", "ollama/qwen2.5:3b"]:
        main_experiment(model, "data", "result/cot", cot)
        main_experiment(model, "data", "result/direct", direct)
        main_experiment(model, "data", "result/folk", folk)
        main_experiment(model, "data", "result/sase", sase)
        main_factagent(model, "data", "result/factagent")
