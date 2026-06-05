import json
from pathlib import Path

def find_key():
    logs_dir = Path("C:/Users/keita/.gemini/antigravity/brain/f885d2c1-9908-49b7-a3b9-5221f6261382/.system_generated/logs")
    transcript_path = logs_dir / "transcript.jsonl"
    
    if not transcript_path.exists():
        print(f"Transcript not found at {transcript_path}")
        return
        
    print(f"Searching {transcript_path}...")
    
    with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f):
            if "migrate_to_supabase.py" in line:
                try:
                    obj = json.loads(line)
                    tool_calls = obj.get("tool_calls", [])
                    for tc in tool_calls:
                        print(f"Line {idx} Tool call {tc.get('name')}: {tc.get('argumentsJson')}")
                except Exception as e:
                    pass

if __name__ == "__main__":
    find_key()





