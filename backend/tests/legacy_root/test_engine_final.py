import os
from backend.ai_engine import engine

def run_tests():
    print("--- 1. Testing Tactical Chat (8B model) ---")
    res1 = engine.tactical_chat([{"role": "user", "content": "放下武器"}])
    print("Result:", res1)
    
    print("\n--- 2. Testing Legal Parsing (nemotron-parse) ---")
    res2 = engine.legal_document_parsing("警情通报：嫌疑人拒绝配合。")
    print("Result:", res2)
    
    print("\n--- 3. Testing Combat Scoring (70b-reward) ---")
    res3 = engine.combat_quality_scoring(b"dummy_image_data")
    print("Result:", res3)
    
    print("\n--- 4. Testing Vision (90b-vision with Desktop target image) ---")
    target_img_path = "C:\\Users\\xxzx-admin\\Desktop\\img_v3_0210f_8c427f1f-68a7-43ba-9106-c2b8db3be4ag.jpg"
    if os.path.exists(target_img_path):
        with open(target_img_path, "rb") as f:
            data = f.read()
        res4 = engine.analyze_vision(data, "SHOOTING_TARGET")
        if res4["success"]:
            print("Vision Success! Partial result:", res4["data"][:100], "...")
        else:
            print("Vision failed:", res4)
    else:
        print("Target image not found.")

if __name__ == "__main__":
    run_tests()
