import json
import sys
import urllib.request
import urllib.error

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


API_URL = "http://127.0.0.1:8000"

def post_query(question: str):
    data = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL}/query",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_endpoint(path: str):
    with urllib.request.urlopen(f"{API_URL}{path}") as resp:
        return json.loads(resp.read().decode("utf-8"))

print("=" * 60)
print("1. HEALTH CHECK")
print("=" * 60)
health = get_endpoint("/health")
print(json.dumps(health, indent=2))

print("\n" + "=" * 60)
print("2. GET /files")
print("=" * 60)
files = get_endpoint("/files")
print(f"Total files returned: {len(files)}")
for f in files[:3]:
    print(f" - {f['file_name']}: {f['chunk_count']} chunks, size={f['file_size']}, status={f['status']}")

print("\n" + "=" * 60)
print("3. REAL QUESTION 1 (Compiler phases)")
print("=" * 60)
r1 = post_query("Explain how a modern compiler processes the statement through all compilation phases in CAT-1.")
print(f"Answer: {r1['answer']}\n")
print(f"Sources ({len(r1['sources'])}):")
for s in r1['sources']:
    print(f" - File: {s['file']} | Chunk #{s['chunk_index']} | Score: {s['score']:.4f}")

print("\n" + "=" * 60)
print("4. REAL QUESTION 2 (Mesh Topology)")
print("=" * 60)
r2 = post_query("How many ports at end devices and total cables are needed for 5 devices in a Full Mesh Topology?")
print(f"Answer: {r2['answer']}\n")
print(f"Sources ({len(r2['sources'])}):")
for s in r2['sources']:
    print(f" - File: {s['file']} | Chunk #{s['chunk_index']} | Score: {s['score']:.4f}")

print("\n" + "=" * 60)
print("5. REAL QUESTION 3 (ChromaDB Architecture)")
print("=" * 60)
r3 = post_query("What is the architecture of ChromaDB?")
print(f"Answer: {r3['answer']}\n")
print(f"Sources ({len(r3['sources'])}):")
for s in r3['sources']:
    print(f" - File: {s['file']} | Chunk #{s['chunk_index']} | Score: {s['score']:.4f}")

print("\n" + "=" * 60)
print("6. OUT-OF-SCOPE QUESTION (No Context / Fallback)")
print("=" * 60)
r4 = post_query("What is the recipe for baking chocolate chip cookies?")
print(f"Answer: {r4['answer']}")
print(f"Sources count: {len(r4['sources'])}")
