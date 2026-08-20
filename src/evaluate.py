import json
from typing import Dict, List
from sklearn.metrics import classification_report
from src.utils import use_gpt
import os
from collections import defaultdict

# Label normalization map
LABEL_MAP = {
    "SUPPORTS": "supported",
    "SUPPORTED": "supported",
    "SUPPORT": "supported",
    "REFUTES": "not_supported",
    "NOT_SUPPORTED": "not_supported",
    "CONTRADICT": "not_supported"
}
METHODS = ["cot", "folk", "sase", "factagent"]

def normalize_label(label: str) -> str:
    return LABEL_MAP.get(label.upper(), label.lower())

def evaluate_classification(data_folder: str, output_folder: str):
    for method in os.listdir(data_folder):
        method_path = os.path.join(data_folder, method)
        if not os.path.isdir(method_path):
            continue

        for model in os.listdir(method_path):
            model_path = os.path.join(method_path, model)
            if not os.path.isdir(model_path):
                continue

            for data_type in os.listdir(model_path):
                data_type_path = os.path.join(model_path, data_type)
                if not os.path.isdir(data_type_path):
                    continue

                for filename in os.listdir(data_type_path):
                    if not filename.endswith(".json"):
                        continue

                    file_path = os.path.join(data_type_path, filename)
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    y_true, y_pred = [], []
                    for item in data:
                        if "label" in item and "predicted_label" in item:
                            true_label = normalize_label(item["label"])
                            pred_label = normalize_label(item["predicted_label"])
                            y_true.append(true_label)
                            y_pred.append(pred_label)

                    if not y_true or not y_pred:
                        print(f"⚠️ Skipped empty or malformed file: {file_path}")
                        continue

                    report = classification_report(y_true, y_pred, digits=4)

                    # Build mirrored output folder structure
                    relative_dir = os.path.join(method, model, data_type)
                    os.makedirs(os.path.join(output_folder, relative_dir), exist_ok=True)
                    output_filename = filename.replace(".json", ".txt")
                    output_path = os.path.join(output_folder, relative_dir, output_filename)

                    with open(output_path, "w", encoding="utf-8") as out_file:
                        out_file.write(f"Classification Report for {filename}\n\n")
                        out_file.write(report)

                    print(f"✅ Saved report: {output_path}")

def evaluate_gpt(data_folder: str, output_file: str, model="gpt-4o-mini") -> Dict:
    # Collect all explanations by uid
    explanation_map = defaultdict(lambda: {"explanations": {}, "claim": None, "label": None})

    for method in METHODS:
        method_path = os.path.join(data_folder, method, model)
        if not os.path.isdir(method_path):
            continue

        for data_type in os.listdir(method_path):
            data_type_path = os.path.join(method_path, data_type)
            if not os.path.isdir(data_type_path):
                continue

            for filename in os.listdir(data_type_path):
                if not filename.endswith(".json"):
                    continue

                file_path = os.path.join(data_type_path, filename)
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for item in data:
                    uid = item.get("uid")
                    if not uid:
                        continue

                    label = normalize_label(item.get("label", ""))
                    explanation = item.get("predicted_explanation", "")
                    claim = item.get("claim", "")

                    explanation_map[(data_type, uid)]["claim"] = claim
                    explanation_map[(data_type, uid)]["label"] = label
                    explanation_map[(data_type, uid)]["explanations"][method] = explanation

    # Evaluate with GPT and write results
    results_by_type = defaultdict(list)

    for (data_type, uid), entry in explanation_map.items():
        if len(entry["explanations"]) < 4:
            print(f"⚠️ Skipping uid={uid} in {data_type} — missing one or more methods")
            continue

        original_claim = entry["claim"]
        label = entry["label"]
        explanations = entry["explanations"]

        # Compose prompt
        prompt = f"""
        You are an expert evaluator for automated fact-check explanations. Your task is to:

        - Review the original claim, its label, and the explanations produced by 4 methods. Each method may produce a different label; consider this when evaluating Soundness.  
        - Evaluate each explanation according to 3 criteria:

        1. Coverage: To what extent the explanation includes all the salient and relevant information necessary to verify the claim.  
        2. Soundness: The logical consistency of the explanation; whether it supports or contradicts its own label and the original claim.  
        3. Readability: The clarity and coherence of the explanation; how easily a human can follow and understand it.

        - Provide a **ranking (1 for best, 4 for worst)** for each criterion.  
        Here is the input:
        {{
        "original_claim": "{original_claim}",
        "label": "{label}",
        "explanations": {json.dumps(explanations, indent=2)}
        }}

        The output should be in the format:  
        {{
        "ranking": {{
            "Coverage": {{ "1": "<method>", "2": "<method>", "3": "<method>", "4": "<method>" }},
            "Soundness": {{ "1": "<method>", "2": "<method>", "3": "<method>", "4": "<method>" }},
            "Readability": {{ "1": "<method>", "2": "<method>", "3": "<method>", "4": "<method>" }}
        }}
        }}
        """

        try:
            gpt_response = use_gpt(prompt, model=model)
            results_by_type[data_type].append({
                "uid": uid,
                "ranking": gpt_response.get("ranking", {})
            })
        except Exception as e:
            print(f"❌ GPT eval failed for uid={uid}: {e}")

    # Write output per data_type
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    for data_type, evaluations in results_by_type.items():
        path = output_file.replace(".txt", f"_{data_type}.txt")
        with open(path, "w", encoding="utf-8") as f:
            for item in evaluations:
                f.write(f"UID: {item['uid']}\n")
                f.write(json.dumps(item["ranking"], indent=2))
                f.write("\n\n")
        print(f"✅ Saved GPT evaluation for {data_type} → {path}")

if __name__ == "__main__":
    evaluate_classification("result/cot", "eval/cot")
    evaluate_classification("result/direct", "eval/direct")
    evaluate_classification("result/folk", "eval/folk")
    evaluate_classification("result/sase", "eval/sase")
    evaluate_classification("result/factagent", "eval/factagent")
    evaluate_gpt("result", "eval/gpt-eval.txt")
   