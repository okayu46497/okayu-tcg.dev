import json
from pathlib import Path

def find_key():
    logs_dir = Path("C:/Users/keita/.gemini/antigravity/brain/f885d2c1-9908-49b7-a3b9-5221f6261382/.system_generated/logs")
    transcript_path = logs_dir / "transcript.jsonl"
    
    if not transcript_path.exists():
        print(f"Transcript not found at {transcript_path}")
        return
        
    print(f"Searching {transcript_path}...")
    
    supabase_key = None
    with open(transcript_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if "SUPABASE_KEY" in line:
                # Let's inspect this line
                try:
                    obj = json.loads(line)
                    # Look inside tool_calls or content
                    content = obj.get("content", "")
                    if "SUPABASE_KEY" in content and len(content) < 500:
                        print(f"Line {idx} content: {content}")
                        
                    tool_calls = obj.get("tool_calls", [])
                    for tc in tool_calls:
                        args = tc.get("argumentsJson", "")
                        if "SUPABASE_KEY" in args and len(args) < 500:
                            print(f"Line {idx} tool call {tc.get('name')}: {args}")
                except Exception:
                    pass

if __name__ == "__main__":
    find_key()
